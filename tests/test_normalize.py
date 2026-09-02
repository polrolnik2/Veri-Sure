"""S1b normalization: the gate that separates a typo from a spec defect."""

from __future__ import annotations

from specflow.normalize import (
    Activation,
    NormalizedRequirement,
    NormalizeOutput,
    gate_one,
    parse_response,
    shared_prefix,
    unobservable,
)

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "nReset", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "cmd_ack", "dir": "output", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
    ]
}
REQ = {"uid": "REQ-0000", "text": "on START, cmd_ack pulses for one clock"}


def _route(port: str) -> dict:
    """A direct self-route. Every requirement carries one now, and the field
    that matters is `shows`: two cases, so nothing vacuous gets through."""
    return {"port": port, "through_req": "", "when": "when a START is issued",
            "shows": f"{port} takes the stated value when the requirement "
                     f"holds and does not when it does not"}


def _out(**kw) -> NormalizeOutput:
    kw.setdefault("activation", Activation(text="a START is issued"))
    kw.setdefault("expectation", "cmd_ack pulses high for exactly one clock")
    observable = kw.get("observable") or []
    kw.setdefault("observed_via",
                  [_route(observable[0])] if observable else [])
    return NormalizeOutput(normalized=[NormalizedRequirement(**kw)])


def test_a_well_formed_normalization_passes():
    assert gate_one(REQ, _out(observable=["cmd_ack", "busy"]), CONTRACT) == []


def test_naming_a_non_port_is_an_error_not_an_unobservable_finding():
    """The distinction the whole stage rests on. A wrong name buys a repair
    round; a spec defect does not, and conflating them means either every typo
    is reported as a spec defect or every spec defect is retried until the
    budget runs out."""
    issues = gate_one(REQ, _out(observable=["div_cnt"]), CONTRACT)
    assert [i.severity for i in issues] == ["error"]
    assert "not a declared output port" in issues[0].message


def test_an_input_port_is_not_an_observable():
    """An input is what a test drives, never what it observes."""
    issues = gate_one(REQ, _out(observable=["ena"]), CONTRACT)
    assert issues and "not a declared output port" in issues[0].message


def test_no_observable_with_a_reason_is_accepted():
    """UNOBSERVABLE is a conclusion, not a failure. Rejecting it would force
    the model to name a port it knows is wrong, which produces an oracle that
    fails correct designs."""
    out = _out(observable=[], unobservable_reason="div_cnt is an internal counter")
    assert gate_one(REQ, out, CONTRACT) == []
    norm = out.normalized[0].model_copy(update={"req_uid": "REQ-0000"})
    assert norm.unobservable
    assert unobservable([norm]) == {"REQ-0000": "div_cnt is an internal counter"}


def test_no_observable_and_no_reason_is_an_error():
    """Declining to commit is not the same as claiming there is none."""
    issues = gate_one(REQ, _out(observable=[]), CONTRACT)
    assert issues and "unobservable_reason" in issues[0].message


def test_claiming_both_an_observable_and_a_reason_is_a_contradiction():
    out = _out(observable=["busy"], unobservable_reason="also internal, somehow")
    issues = gate_one(REQ, out, CONTRACT)
    assert issues and "contradict" in issues[0].message


def test_activation_inputs_are_checked_against_the_contract():
    ok = _out(observable=["busy"], activation=Activation(text="x", inputs={"cmd": 1}))
    assert gate_one(REQ, ok, CONTRACT) == []

    unknown = _out(observable=["busy"],
                   activation=Activation(text="x", inputs={"nope": 1}))
    assert any("not a declared input" in i.message
               for i in gate_one(REQ, unknown, CONTRACT))

    too_wide = _out(observable=["busy"],
                    activation=Activation(text="x", inputs={"ena": 2}))
    assert any("does not fit" in i.message
               for i in gate_one(REQ, too_wide, CONTRACT))


def test_reset_may_appear_in_an_activation_even_though_it_is_not_drivable():
    """"While reset is asserted" is a real precondition, and the runtime has a
    reset step that reaches it. `_drivable` excludes reset from STIMULUS; that
    is a statement about who owns the pin, not about what a requirement may be
    conditioned on."""
    out = _out(observable=["busy"],
               activation=Activation(text="during reset", inputs={"nReset": 0}))
    # Asserted on the reset property specifically rather than on an empty issue
    # list: "during reset" also trips the windowed-text screen, which is a
    # separate (and advisory) finding about `until`. Pinning `== []` here would
    # make this test fail whenever any unrelated advisory is added.
    assert not [i for i in gate_one(REQ, out, CONTRACT)
                if "nReset" in i.message or "activation.inputs" in i.path]


def test_an_input_only_activation_is_distinguishable_from_a_stateful_one():
    """Not a quality judgement -- it decides WHERE the condition can be checked.
    An input-only activation is readable off a stimulus step list with no model
    at all; a stateful one needs something to run."""
    assert Activation(text="cmd is START", inputs={"cmd": 1}).input_only
    assert not Activation(text="while the FSM is idle").input_only


def test_two_normalizations_for_one_requirement_is_rejected():
    out = NormalizeOutput(normalized=[
        NormalizedRequirement(activation=Activation(text="a"), observable=["busy"],
                              expectation="x"),
        NormalizedRequirement(activation=Activation(text="b"), observable=["busy"],
                              expectation="y"),
    ])
    issues = gate_one(REQ, out, CONTRACT)
    assert issues and "two requirements" in issues[0].message


def test_a_parse_failure_is_reported_as_one_not_as_an_empty_answer():
    out = parse_response("this is not json")
    assert out.reasoning.startswith("Parse Error: ")
    issues = gate_one(REQ, out, CONTRACT)
    assert issues and issues[0].path.endswith(".response")


def test_the_prompt_shows_the_port_lists_the_gate_validates_against():
    """`suite_shared_prefix` learned this the hard way: a gate validating against
    a list the model was never shown cost 12 repair rounds in 41 testpoints."""
    prefix = shared_prefix("{}", CONTRACT)
    assert "cmd_ack" in prefix and "busy" in prefix
    assert "ONLY names `observable` may contain" in prefix
    # Inputs listed too, because `activation.inputs` is gated the same way.
    assert "activation.inputs" in prefix


def test_the_prompt_separates_the_mechanism_from_the_effect():
    """The measured failure mode, and the more expensive of the two mistakes.

    Most requirements describe internal machinery on the way to a result: "the
    filter suppresses a glitch so no START is detected", "the FSM leaves idle
    and runs the command". Reading the MECHANISM and calling the requirement
    unobservable writes off behaviour that is perfectly checkable.

    Measured on f-i2c: 27 of 77 requirements came back UNOBSERVABLE, and 10 of
    those had oracles that had already passed screening -- well-formedness alone
    requires naming a declared port, so something observable was plainly there.
    After this rule, 7 of those 10 flip to observable while 4 of 4 genuinely
    internal controls (div_cnt, clk_en, scl_sync, cnt) stay unobservable.
    """
    prefix = " ".join(shared_prefix("{}", CONTRACT).split())
    assert "ASK ABOUT THE EFFECT, NOT THE MECHANISM" in prefix
    # The completable-sentence test is what makes the rule applicable rather
    # than a sentiment.
    assert "no boundary effect AT ALL" in prefix
    # Both mistakes must stay named. Dropping either half is how this swings
    # back the other way into reaching for the nearest output port.
    assert "produces a check that fails correct designs" in prefix
    assert "writes off behaviour that is perfectly checkable" in prefix


# ------------------------------------------- activation inputs are NECESSARY


def test_the_prompt_asks_for_necessary_not_sufficient_inputs():
    """The bar `check_static` actually needs, pinned against reverting.

    The clause this replaces told the model to leave `inputs` empty whenever the
    precondition read as internal state. The model followed it, and 57 of 77
    requirements came back with no input activation -- 32 of them naming a
    command or reset in their own activation text, several with the literal
    encoding (`"A START (cmd = 0001) ... is issued"` normalized to `{}`).

    That capped `_attach` at 26% of the suite, which is why a run that added 48
    testpoints moved `NOT_EXERCISED` by zero.

    Necessary is the right bar because `inputs` gates ATTACHMENT, not truth: the
    oracle still runs afterwards and reports the scenario unexercised if it did
    not occur. Measured on the requirements that already had inputs, a static
    match predicts the oracle really fires with precision 0.81, against 0.40 for
    attaching everything -- and 0.40 is the regime the f-i2c result (one true
    finding for 27 false) came out of.
    """
    from specflow.normalize import SYSTEM

    assert "NECESSARY condition, not a sufficient one" in SYSTEM
    assert "must these values be driven" in SYSTEM
    # The state-phrased cases now get inputs rather than being excluded.
    assert "during the READ data-bit phase" in SYSTEM
    # And the genuine exclusion survives: nothing a test drives reaches it.
    assert "after arbitration has been lost" in SYSTEM

    stale = ('"while the state machine is idle" and "after arbitration has '
             'been lost"\ncannot')
    assert stale not in SYSTEM, (
        "the sufficiency reading is back; it empties `inputs` for any "
        "precondition phrased as internal state")


def test_reset_stays_a_legitimate_activation_input():
    """Unchanged by the rewrite, and easy to lose in it.

    Matched across collapsed whitespace: the rewrite reflowed the paragraph and
    put a newline inside "Reset ports", so the obvious assertion failed on text
    that was present and correct. That trap has cost this repo before.
    """
    import re

    from specflow.normalize import SYSTEM

    flat = re.sub(r"\s+", " ", SYSTEM)
    assert "Reset ports may appear in `inputs`" in flat


# ------------------------------------------- the route is the base case

def test_a_directly_observable_requirement_must_still_give_a_ROUTE():
    """The field that matters is `shows`, and only the exception was ever asked
    for it. REQ-0075 was directly observable, got `observed_via: []`, and was
    never made to say what distinguishes the requirement holding from it not
    holding -- so its check settled for "an output moved", which nothing can
    falsify."""
    out = NormalizeOutput(normalized=[NormalizedRequirement(
        req_uid="REQ-0000", activation=Activation(text="a START is issued"),
        expectation="e", observable=["cmd_ack"], observed_via=[])])
    issues = gate_one(REQ, out, CONTRACT)
    assert any("no route given" in i.message for i in issues), issues


def test_no_route_given_shows_the_SHAPE_not_just_prose():
    """Measured live, or1200_ctrl REQ-0001: told only this prose (no JSON), the
    author guessed a dict keyed by port name -- a defensible reading of a
    sentence that never shows what a route actually looks like. The message
    now carries the shape it is asking for."""
    out = NormalizeOutput(normalized=[NormalizedRequirement(
        req_uid="REQ-0000", activation=Activation(text="a START is issued"),
        expectation="e", observable=["cmd_ack"], observed_via=[])])
    issues = gate_one(REQ, out, CONTRACT)
    msg = next(i.message for i in issues if "no route given" in i.message)
    assert "LIST of objects" in msg
    assert '"port"' in msg and '"shows"' in msg


def test_a_shape_mistake_on_observed_via_does_not_lose_the_shape():
    """The failure mode the test above guards the FIRST round against: a
    round that guessed wrong and failed to PARSE used to fall through to the
    raw pydantic error alone, with the shape explanation gone -- so the next
    round had nothing to correct toward and emptied the field instead,
    reproducing the original error one round later. A parse failure naming
    `observed_via` now carries the same reminder.

    A dict-keyed-by-port guess (the shape actually measured live) is no
    longer a parse failure at all -- `_accept_the_shapes_the_model_actually_
    returns` coerces it losslessly, landed independently the same day. This
    uses a shape that coercion cannot recover (a bare string), so it still
    exercises the path this test is for."""
    bad = ('{"reasoning": "x", "normalized": [{"req_uid": "REQ-0000", '
           '"observed_via": "not a route at all"}]}')
    out = parse_response(bad)
    assert out.reasoning.startswith("Parse Error: ")
    assert "LIST of objects" in out.reasoning

    # And a parse failure unrelated to this field stays exactly as terse as
    # before -- the reminder is not owed to every malformed response.
    unrelated = "not json at all"
    out2 = parse_response(unrelated)
    assert "LIST of objects" not in out2.reasoning


def test_a_one_sided_shows_is_rejected():
    out = _out(observable=["cmd_ack"])
    out.normalized[0].observed_via[0].shows = "cmd_ack is observable"
    issues = gate_one(REQ, out, CONTRACT)
    assert any("when it does NOT" in i.message for i in issues)


def test_a_TAUTOLOGY_may_decline_and_is_not_forced_to_invent_one():
    """The escape hatch, and it has to exist.

    REQ-0005 is "releasing scl_oen high causes the module to release the line":
    its port is its own antecedent, so there is no second case. A gate that
    DEMANDS a discrimination from every requirement gets a fabricated one --
    a model asked for something impossible complies rather than refuses -- and
    an invented discrimination is worse than an absent one, because it launders
    a check that cannot fail into one that looks checkable and vacuity only
    catches it three stages later.
    """
    from specflow.normalize import NO_DISCRIMINATION

    out = _out(observable=["cmd_ack"])
    out.normalized[0].observed_via[0].shows = (
        f"{NO_DISCRIMINATION}: the port is the requirement's own antecedent")
    assert gate_one(REQ, out, CONTRACT) == []


def test_SILENCE_is_still_rejected():
    """An absent answer cannot be told from "there is nothing to distinguish",
    and the difference decides whether this is a finding about the
    specification or a defect in the pass. Same shape as `observable` + an
    `unobservable_reason`: empty WITH a reason passes, empty without does not."""
    out = _out(observable=["cmd_ack"])
    out.normalized[0].observed_via[0].shows = ""
    assert gate_one(REQ, out, CONTRACT) != []


def test_the_first_pass_may_not_name_ANOTHER_requirement():
    """It sees one requirement and cannot know another's uid, so a borrowed port
    is a claim it has no basis for -- that is the second pass's answer."""
    out = _out(observable=["cmd_ack"])
    out.normalized[0].observed_via[0].through_req = "REQ-0099"
    issues = gate_one(REQ, out, CONTRACT)
    assert any("cannot know another's uid" in i.message for i in issues)


def test_declining_every_route_abandons_the_requirement():
    """And the disposition is earned: the pass ran, asked, and was told there is
    no second case. It leaves the system with a reason rather than becoming an
    assertion nothing can falsify."""
    from specflow.normalize import NO_DISCRIMINATION
    from specflow.oracles_stage import _declines

    assert _declines(f"{NO_DISCRIMINATION}: nothing contradicts it")
    assert not _declines("busy stays low for a narrow glitch and rises "
                         "for a wide one")


def test_the_activation_can_express_a_WINDOW_and_an_output_trigger():
    """The schema could only express a predicate over ONE ROW, and 63% of a
    real design's requirements name a span in their own text.

    Normalisation flattened each to the instant its activation began, so every
    check over one became a point check -- which fails every design or passes
    every design depending only on which way the port sat at that instant. The
    two populations that produces were measured at 79% and 83% windowed-text-
    with-one-row-activation, against 58% of the checks carrying neither flag.
    """
    from specflow.normalize import Activation

    windowed = Activation(text="during an accepted WRITE",
                          inputs={"cmd": 8}, until=[{"cmd_ack": 1}])
    assert windowed.windowed and windowed.input_only

    # Co-extensive: `after` with no `until` closes when the activation stops
    # holding, so "while ena is low" needs none and must not be forced to one.
    assert not Activation(text="while ena is low", inputs={"ena": 0}).windowed

    # `inputs` stays INPUT-ONLY -- `obligation.check_static` decides from the
    # steps alone, which only works if every name there is driven. An output in
    # the trigger goes to `opens_on`.
    out_trigger = Activation(text="an output-enable is driven low",
                             inputs={"nReset": 1},
                             opens_on=[{"scl_oen": 0}, {"sda_oen": 0}])
    assert out_trigger.opens_on == [{"scl_oen": 0}, {"sda_oen": 0}]
    assert "sda_oen" not in out_trigger.inputs

    # ANY-OF, NOT ALL-OF. Written first as a single dict -- mirroring `inputs`
    # -- `until` read as a conjunction, and a close condition is routinely a
    # disjunction. Six of 28 activations came back {al: 1, cmd_ack: 1}, which
    # is unsatisfiable: arbitration loss drives the FSM to idle and clears
    # cmd_ack. Those windows opened, ran off the end and decided nothing.
    # The example this test was first written with -- "until the WRITE completes
    # OR ARBITRATION IS LOST" -- is no longer a two-way close, and D9 in
    # docs/sva-divergence.md is why: an arbitration loss VOIDS the attempt, it
    # does not end it, so it belongs in `aborts_on`. The list shape is still
    # any-of; only the example moved.
    either = Activation(text="until the transfer completes or the bus goes idle",
                        inputs={"cmd": 8}, until=[{"cmd_ack": 1}, {"busy": 0}])
    assert either.until == [{"cmd_ack": 1}, {"busy": 0}]
    # A bare dict is the single-alternative case, accepted rather than rejected:
    # refusing the common shape would spend a repair round on punctuation.
    assert Activation(text="x", until={"cmd_ack": 1}).until == [{"cmd_ack": 1}]


def test_until_and_opens_on_may_name_OUTPUTS_but_inputs_may_not():
    """A window closes on what the DESIGN does, so `until` must reach outputs.
    `inputs` must not, for the reason above."""
    out = _out(observable=["busy"],
               activation=Activation(text="during a WRITE", inputs={"cmd": 8},
                                     until=[{"cmd_ack": 1}],
                                     opens_on=[{"busy": 1}]))
    bad = [i for i in gate_one(REQ, out, CONTRACT) if i.severity == "error"]
    assert not bad, f"outputs must be legal in until/opens_on: {bad}"

    rejected = _out(observable=["busy"],
                    activation=Activation(text="x", inputs={"cmd": 8},
                                          until=[{"nope": 1}]))
    assert any("not a declared port" in i.message
               for i in gate_one(REQ, rejected, CONTRACT))


def test_a_span_in_the_text_with_no_close_condition_is_REPORTED_not_rejected():
    """Advisory, deliberately. This repo has twice paid for a screen that
    blocked before its false-positive rate was known -- gate 1's blanket "met"
    discarded 30 requirements, and correspondence rejected 56 of 70 on a
    miscalibration. Measured on a2-i2c the broad screen fires on 73 of 105 at
    45% precision and 80% recall against the 41 known-bad checks."""
    out = _out(observable=["busy"],
               activation=Activation(text="at the start of the STOP sequence",
                                     inputs={"cmd": 2}))
    issues = gate_one(REQ, out, CONTRACT)
    flagged = [i for i in issues if i.path.endswith("activation.until")]
    assert flagged and all(i.severity == "warning" for i in flagged)
    # And giving the window silences it.
    ok = _out(observable=["busy"],
              activation=Activation(text="at the start of the STOP sequence",
                                    inputs={"cmd": 2}, until=[{"cmd_ack": 1}]))
    assert not [i for i in gate_one(REQ, ok, CONTRACT)
                if i.path.endswith("activation.until")]


def test_a_condition_may_name_an_EDGE_and_it_maps_to_SVA():
    """A LEVEL IS NOT AN EDGE, and the schema could only say level.

    Measured on a2-i2c: 28 of 105 requirements name an edge or transition in
    their own text. REQ-0038's requirement says "a falling edge observed on the
    filtered SCL", its activation text says "a filtered SCL falling edge
    occurs", and its schema said `scl_i == 0`. Three checks reported the
    activation as never occurring for exactly that reason.

    `after` does not cover it: it opens on a rising activation, so a LONE
    `{scl_i: 0}` gives falling-edge windows -- but a MIXED condition makes it
    open on the edge of the CONJUNCTION, which also fires when `scl_oen` rises
    over an already-low `scl_i`. A different event.
    """
    from specflow.normalize import _EDGE_WORDS
    from specflow.refmodel.temporal import EDGES

    # The vocabulary is defined once, in the module that computes it.
    assert set(EDGES) == _EDGE_WORDS

    ok = _out(observable=["busy"],
              activation=Activation(text="ena falls while busy is high",
                                    inputs={"ena": 0},
                                    opens_on=[{"ena": "fall", "busy": 1}]))
    assert not [i for i in gate_one(REQ, ok, CONTRACT) if i.severity == "error"]

    bad = _out(observable=["busy"],
               activation=Activation(text="x", inputs={"ena": 0},
                                     opens_on=[{"ena": "wobble"}]))
    assert any("neither a value nor one of" in i.message
               for i in gate_one(REQ, bad, CONTRACT))


def test_rise_on_a_multibit_port_is_WARNED_because_SVA_reads_the_LSB():
    """SVA's `$rose`/`$fell` are defined on the LSB; `temporal.edges` reads
    them as increased/decreased. Identical on a 1-bit port -- which is every
    port these requirements name an edge of -- and different on a wider one.

    A warning, not an error: the wide case is unusual but not illegal, and this
    repo has twice paid for a screen that blocked before its false-positive
    rate was known."""
    wide = _out(observable=["busy"],
                activation=Activation(text="x", inputs={"cmd": 8},
                                      opens_on=[{"cmd": "rise"}]))
    flagged = [i for i in gate_one(REQ, wide, CONTRACT)
               if "increased or decreased" in i.message]
    assert flagged and all(i.severity == "warning" for i in flagged)


def test_edges_computes_the_transition_not_the_level():
    """The reason this lives in `temporal` rather than in the prompt: an author
    re-deriving it per check is the hand-rolled index arithmetic the operators
    exist to replace."""
    from specflow.refmodel.temporal import after, edges

    trace = [{"edge": 0, "inputs": {"scl_i": 1, "scl_oen": 0}, "outputs": {}},
             {"edge": 4, "inputs": {"scl_i": 1, "scl_oen": 1}, "outputs": {}},
             {"edge": 9, "inputs": {"scl_i": 0, "scl_oen": 1}, "outputs": {}}]
    # Port names here are the i2c ones the finding came from; `edges` reads the
    # trace, not the contract, so no declaration is needed.
    fell = edges(trace, "scl_i", "fall")
    assert fell == {9}
    assert edges(trace, "scl_i", "rise") == set()
    assert edges(trace, "scl_oen", "change") == {4}

    # The whole point: a level conjunction opens a window at edge 9 EITHER way,
    # but it ALSO opens one where scl_oen rose over an already-low scl_i --
    # which the edge form does not.
    edge_windows = after(trace, lambda r: r["edge"] in fell
                         and r["inputs"]["scl_oen"] == 1)
    assert [w.edge for w in edge_windows] == [9]

    already_low = [{"edge": 0, "inputs": {"scl_i": 0, "scl_oen": 0}, "outputs": {}},
                   {"edge": 5, "inputs": {"scl_i": 0, "scl_oen": 1}, "outputs": {}}]
    levels = after(already_low,
                   lambda r: r["inputs"]["scl_i"] == 0 and r["inputs"]["scl_oen"] == 1)
    assert [w.edge for w in levels] == [5], "the level form fires here"
    assert not edges(already_low, "scl_i", "fall"), "the edge form does not"


def test_effect_follows_is_DERIVED_and_serialises():
    """`after_activation` was offered to the check author in prose with the
    measured count behind it -- which is exactly the posture that got v1 of the
    temporal block 0 uptake in 306 responses. The schema already knows the
    answer, so it carries it.

    A window that closes on a CONDITION is one whose effect outlasts its
    trigger. A window with no close condition is an instant or co-extensive
    with a level, and there the expectation holds at the activation row too."""
    from specflow.normalize import Activation

    follows = Activation(text="during a WRITE", inputs={"cmd": 8},
                         until=[{"cmd_ack": 1}])
    at_instant = Activation(text="while ena is low", inputs={"ena": 0})
    assert follows.effect_follows is True
    assert at_instant.effect_follows is False

    # It must SERIALISE: the author reads the normalized block as JSON, and a
    # plain property would be invisible there.
    assert follows.model_dump()["effect_follows"] is True
    assert "effect_follows" in at_instant.model_dump()


def test_strong_is_NOT_derived_from_the_same_field():
    """The signal looks identical and is not. A non-empty `until` says the
    window closes on a condition; it does NOT say the requirement asserts that
    the closing happens. "During a WRITE, sda_oen follows din" with
    `until cmd_ack` is about sda_oen, not about the write completing --
    deriving `strong` from the same field would convict a design whose trace
    merely ended early."""
    import inspect

    from specflow.normalize import Activation

    assert not hasattr(Activation, "strong"), (
        "liveness is a claim in the requirement's own words, not a shape of "
        "the window")
    src = inspect.getsource(Activation)
    assert "WHY `strong` IS NOT DERIVED" in src, (
        "the reasoning must stay next to the thing it explains, or the next "
        "reader adds it")


def test_an_edge_on_the_CLOCK_is_rejected():
    """Every row of the trace is already a clock edge, so `{"clk": "rise"}`
    matches NO row and `{"clk": 1}` matches every one.

    Not hypothetical: the first time the edge vocabulary ran live, 3 of 40
    activations came back `opens_on [{"clk": "rise"}]`, and
    `edges(trace, "clk", "rise")` returns 0 of 105 rows -- those windows could
    never open. Giving the author a way to name an edge gave it a way to name
    the clock's, which reads natural and is empty.
    """
    clocked = {**CONTRACT, "clocking": {"clock": {"name": "clk", "edge": "posedge"}}}
    for field in ("opens_on", "until", "aborts_on"):
        out = _out(observable=["busy"],
                   activation=Activation(text="on the rising edge of clk",
                                         inputs={"ena": 1}, **{field: [{"clk": "rise"}]}))
        assert any("is the clock" in i.message and i.severity == "error"
                   for i in gate_one(REQ, out, clocked)), field
    # A level on it is just as empty.
    lvl = _out(observable=["busy"],
               activation=Activation(text="x", inputs={"clk": 1, "ena": 1}))
    assert any("is the clock" in i.message for i in gate_one(REQ, lvl, clocked))
    # And a non-clock edge is untouched.
    ok = _out(observable=["busy"],
              activation=Activation(text="ena falls", inputs={"ena": 0},
                                    opens_on=[{"ena": "fall"}]))
    assert not [i for i in gate_one(REQ, ok, clocked) if i.severity == "error"]


def test_an_observable_no_route_explains_is_reported_not_shipped_silently():
    """The gate already fires on this; nothing acted on it.

    REQ-0094's worked case: text about arbitration checking during WRITE
    operations, one named port, and four ports declared observable with no
    route saying what any of them shows. The check it got then invented a
    claim -- both lines released on arbitration loss -- that correct hardware
    does not satisfy.
    """
    from specflow.normalize import (NormalizedRequirement, Route,
                                    unsupported_observable)

    bare = NormalizedRequirement(
        req_uid="REQ-0094", observable=["al", "sda_oen"], observed_via=[])
    explained = NormalizedRequirement(
        req_uid="REQ-0007", observable=["busy"],
        observed_via=[Route(port="busy", shows="busy rises on a wide glitch "
                                               "and does not on a narrow one")])
    blind = NormalizedRequirement(
        req_uid="REQ-0000", observable=[], unobservable_reason="internal only")

    got = unsupported_observable([bare, explained, blind])
    assert set(got) == {"REQ-0094"}, got
    assert "no route explains" in got["REQ-0094"]
    # A requirement with NO observable is a different finding with a different
    # cause, and `unobservable` already reports it.
    assert "REQ-0000" not in got


# --------------------------------------------- `disable iff`: aborts_on


def test_an_abort_is_not_a_close_and_the_schema_keeps_them_apart():
    """The costliest confusion this field has made, and D9 in
    docs/sva-divergence.md holds the measurement: on c1-i2c 13 requirements
    closed on reset and 40 on `al`, every one of them written as `until`.

    Folded together the two are indistinguishable -- and a strong obligation
    over a cut-short attempt convicts a design for not doing what it was never
    asked. REQ-0055 convicted the KNOWN-GOOD RTL that way: an `al` pulse the
    design is right to emit ended its window at edge 7, and the START it checks
    does not drive sda_oen low until edge 28 or ack until edge 38.
    """
    a = Activation(text="during a WRITE, unless arbitration is lost",
                   inputs={"cmd": 8}, until=[{"cmd_ack": 1}],
                   aborts_on=[{"al": 1}, {"nReset": 0}])
    assert a.until == [{"cmd_ack": 1}]
    assert a.aborts_on == [{"al": 1}, {"nReset": 0}]

    # Same any-of list shape as `until`, same bare-dict tolerance -- refusing
    # the common single-alternative form would spend a repair round on
    # punctuation.
    assert Activation(text="x", aborts_on={"nReset": 0}).aborts_on == [{"nReset": 0}]

    # DEFAULTS EMPTY, and every frozen check predates the field. An oracle
    # written before it must decide exactly as it did.
    assert Activation(text="x").aborts_on == []

    # `windowed` still reads `until` ALONE. An abort is subtractive: it says
    # what makes the promise moot, never that there is a span to govern. A
    # requirement with aborts and no close is an instant that can be voided,
    # and calling it windowed would send it down the span path with no close
    # condition to run to.
    assert not Activation(text="x", inputs={"cmd": 8},
                          aborts_on=[{"nReset": 0}]).windowed


def test_aborts_on_ports_are_checked_like_until_ports():
    """An abort on an undeclared port is a window that can never be
    discarded -- exactly as silent as one that can never close, and it fails
    the same way: the check runs, decides, and nobody learns the guard was
    never armed."""
    ok = _out(observable=["busy"],
              activation=Activation(text="during a WRITE", inputs={"cmd": 8},
                                    until=[{"cmd_ack": 1}],
                                    aborts_on=[{"nReset": 0}]))
    assert not [i for i in gate_one(REQ, ok, CONTRACT) if i.severity == "error"]

    bad = _out(observable=["busy"],
               activation=Activation(text="x", inputs={"cmd": 8},
                                     aborts_on=[{"al": 1}]))
    issues = gate_one(REQ, bad, CONTRACT)
    assert any("not a declared port" in i.message for i in issues), issues
    assert any("aborts_on" in i.path for i in issues), issues

    # The clock is rejected here too -- pinned in the clock test above, which
    # now runs its loop over all three fields.


def test_the_prompt_tells_the_author_that_reset_is_an_abort():
    """The prompt used to carry the bug as a worked example -- `until
    [{"cmd_ack": 1}, {"al": 1}]`, the exact folded form -- so the field was
    being taught to make the error. What replaced it has to state the
    distinction, and it has to leave room for the counter-case: on 11 of the 40
    `al` requirements, `al` IS the declared observable, and rewriting those to
    aborts would delete the check.
    """
    from specflow.normalize import SYSTEM

    assert "aborts_on" in SYSTEM
    assert "disable iff" in SYSTEM
    for fragment in ("ENDING AND VOIDING ARE DIFFERENT",
                     "RESET IS ALWAYS AN ABORT",
                     "AN ABORT IS A READING, NOT A RULE"):
        assert fragment in SYSTEM, fragment
    # And the example that taught the defect is gone.
    assert '[{"cmd_ack": 1}, {"al": 1}]' not in SYSTEM


def test_a_scraped_fragment_is_a_parse_error_not_an_empty_answer():
    """Both `NormalizeOutput` fields carry defaults, so ANY object validates.

    That makes a fragment scraped out of a broken response indistinguishable
    from a model that answered nothing, and the next round is then handed a
    complaint about CONTENT -- "observable at [...] but no route given" -- for
    a response whose only defect was one unescaped quote. The model is asked to
    fix a field it did supply, which is the same short-circuit the
    `observed_via` shape gate exists to prevent, one layer up.

    Measured live: c1-i2c REQ-0048 round 1 wrote `until [{"busy":0}]` inside
    its `reasoning` STRING with the inner quotes unescaped. Recovery found the
    balanced `{"busy":0}`, validated it to an empty output, and all four
    rounds went on the wrong complaint. 3 of that run's 348 recorded responses
    took this path.
    """
    from specflow.normalize import PARSE_ERROR

    out = parse_response('{"reasoning": "I set until [{"busy":0}] here"}')
    assert not out.normalized
    assert out.reasoning.startswith(PARSE_ERROR), out.reasoning
    # It must name what was actually recovered, so the round can see that its
    # JSON broke rather than guessing at its content.
    assert "['busy']" in out.reasoning, out.reasoning
    assert "ESCAPE" in out.reasoning, out.reasoning


def test_an_empty_normalization_WITH_reasoning_is_still_a_real_answer():
    """The counter-case, and the reason the guard tests both fields.

    A model may legitimately return no normalized requirement and say why --
    that is an answer, and turning it into a parse error would destroy the one
    honest way to report that a requirement cannot be normalized.
    """
    from specflow.normalize import PARSE_ERROR

    out = parse_response('{"reasoning": "this span is a port-table gloss"}')
    assert not out.normalized
    assert not out.reasoning.startswith(PARSE_ERROR)
    assert out.reasoning == "this span is a port-table gloss"


def test_a_route_with_no_when_is_rejected():
    """`shows` says WHAT the port does; `when` says WHERE it may say it.

    The gate checked `port`, `through_req` and `shows` and never `when`, so
    76% of the frozen c1-i2c set's routes (180 of 238, across 76 of 122
    requirements) carry an empty one. An unscoped route cannot tell a response
    to this requirement apart from anything else happening in the same window:
    REQ-0046's re-authored check watched all three of its observables at every
    edge, because all three routes arrived with `when` empty, and it convicted
    the golden design on an unreset `dout`'s power-on capture.
    """
    bad = _out(observable=["busy"],
               observed_via=[{**_route("busy"), "when": "   "}])
    issues = [i for i in gate_one(REQ, bad, CONTRACT) if i.severity == "error"]
    assert any("`when` is empty" in i.message for i in issues), issues
    assert any("observed_via[0]" in i.path for i in issues), issues


def test_restating_the_activation_is_an_acceptable_when():
    """The bar is deliberately low, and this is the pin that keeps it low.

    A requirement whose effect is visible for exactly as long as its activation
    holds has nothing sharper to say, and rejecting that answer would push the
    author to invent a narrower window the specification never states -- which
    is the over-strictness this pipeline spends its budget preventing.
    """
    ok = _out(observable=["busy"],
              observed_via=[{**_route("busy"),
                             "when": "whenever the activation holds"}])
    assert not [i for i in gate_one(REQ, ok, CONTRACT) if i.severity == "error"]


def test_both_prompts_ask_for_when_now_that_the_gate_demands_it():
    """The gate must never demand a field the instruction does not ask for.

    That is the defect the `observed_via` SHAPE fix closed one layer up, and
    the empty-`when` check reintroduced it: the direct pass's task text named
    `shows` and never `when`, and `INDIRECT_SYSTEM` glossed `when` purely as
    telling THIS requirement's effect apart from the OTHER requirement's --
    vacuous on a direct route, where `through_req` is empty and there is no
    other requirement. 76% of the frozen set's routes came back empty.
    """
    from specflow.normalize import (
        INDIRECT_SYSTEM,
        _OBSERVED_VIA_SHAPE,
        _OBSERVED_VIA_TASK,
    )

    assert "`when`" in _OBSERVED_VIA_TASK
    assert "when" in _OBSERVED_VIA_SHAPE
    # And the low bar is stated where the author reads it, not only in the gate.
    assert "the activation" in _OBSERVED_VIA_TASK
    # The indirect gloss has to cover the direct route it also governs.
    assert "DIRECT route" in INDIRECT_SYSTEM


def test_the_prompt_teaches_sustains_now_that_the_schema_has_it():
    """A field the schema accepts and the prompt never names is a dark field.

    `sustains` was added so an activation could state a repetition the
    specification gives -- the majority-filter threshold that REQ-0046's check
    could not express, and without which it convicted every design. Measured on
    the first run after it landed: **0 of 127** normalized requirements
    populated it, and `SYSTEM` did not contain the word. That is the same
    defect as `observed_via`'s missing shape one layer over: the gate and the
    model disagree because only one of them was told.

    The rule it sits beside must survive: `until` is still a condition and
    never a count, and `sustains` is the narrow exception for a count the spec
    STATES rather than one the model invents -- which is what `stated_by` is
    for.
    """
    from specflow.normalize import SYSTEM

    assert "sustains" in SYSTEM
    for fragment in ("at_least", "at_most", "stated_by",
                     "A CONDITION, NEVER A COUNT",
                     "LEAVE IT EMPTY unless the specification supplies"):
        assert fragment in SYSTEM, fragment


# ------------------------------------- the cheap exit out of writing a route


CONCEDING = ("not visible on any output port directly; the effect is that the "
             "FSM timing counter is paused, which should be visible through "
             "the absence of state transitions (cmd_ack not pulsing)")


def test_an_UNOBSERVABLE_reason_that_says_WHERE_the_effect_shows_is_refused():
    """The concession, measured on h2-i2c: 18 of 41 unobservable requirements
    (44%) name the port and the mechanism inside the very sentence that
    declines to give a route.

    This is not the model failing to know the answer -- it writes the answer
    down. `observed_via`'s `shows` demands a two-case discrimination, and one
    free sentence in `unobservable_reason` buys an exit from that. The prompt
    has warned against exactly this since it was written, and the warning was
    not enough.
    """
    issues = gate_one(REQ, _out(observable=[], unobservable_reason=CONCEDING),
                      CONTRACT)
    bad = [i for i in issues
           if i.severity == "error" and "unobservable_reason" in i.path]
    assert bad, f"a conceded route must be refused; got {issues}"
    # It quotes the author's own sentence back -- an author reads its own words
    # faster than it reads a rule -- and names the field the route belongs in.
    assert "should be visible through" in bad[0].message
    assert "observed_via" in bad[0].message


def test_an_HONEST_unobservable_reason_is_NOT_refused():
    """The pin that keeps the gate from eating the answer it exists to protect.

    "cannot be directly observed at declared output ports" is the correct reply
    for a port declaration or a list marker, and it contains the word
    `observed` -- so a predicate keying on vocabulary alone would reject every
    honest answer, forcing the model to name a port it knows is wrong. That is
    the failure this whole stage exists to prevent, so a negation anywhere in
    the preceding clause disqualifies the match.
    """
    for reason in (
        "slave_wait is an internal signal whose assertion cannot be directly "
        "observed at declared output ports",
        "the synchronization pipeline itself is not directly observable at "
        "declared output ports",
        "this is scaffolding text containing only a list marker with no "
        "functional content to observe at any interface port",
        "the requirement specifies input port declarations which are "
        "compile-time structural properties of the interface",
        "This requirement lists module capabilities at an architectural level "
        "without specifying particular observable behaviors",
    ):
        issues = gate_one(REQ, _out(observable=[], unobservable_reason=reason),
                          CONTRACT)
        bad = [i for i in issues
               if i.severity == "error" and "unobservable_reason" in i.path]
        assert not bad, f"honest answer refused: {reason[:60]!r} -> {bad}"


def test_a_NAMED_port_gets_ONE_error_for_the_contradiction_not_two():
    """`observable` non-empty already contradicts any reason at all, and the
    older check owns that case. Firing both would hand the author two errors
    for one mistake and invite it to fix the wrong half -- delete the route it
    correctly gave, rather than delete the reason."""
    issues = gate_one(
        REQ, _out(observable=["cmd_ack"], unobservable_reason=CONCEDING),
        CONTRACT)
    bad = [i for i in issues
           if i.severity == "error" and "unobservable_reason" in i.path]
    assert len(bad) == 1, f"expected one contradiction error, got {bad}"
    assert "these contradict" in bad[0].message


# ------------------------------------------ a value-set: ANY of these opens it


def test_a_VALUE_SET_in_inputs_passes_the_gate():
    """`inputs` maps port -> value, which makes it a CONJUNCTION, and until now
    that was the only shape it had. A requirement triggered by ANY OF several
    values -- "a START, STOP, READ or WRITE command is accepted" -- had nowhere
    to say so.

    Measured on h2-i2c: of 22 observable requirements whose activation carried
    no trigger at all, 8 had a disjunctive one, written into `text` where no
    gate and no oracle can reach it.
    """
    out = _out(observable=["cmd_ack"])
    # Numeric here because this fixture's contract declares no encoding
    # table; the symbolic form is exercised in test_encoding.py against a real
    # one. What is under test is the SHAPE, which is orthogonal to resolution.
    out.normalized[0].activation.inputs = {"cmd": [1, 2, 4, 8], "ena": 1}
    assert [i for i in gate_one(REQ, out, CONTRACT) if i.severity == "error"] == []


def test_a_value_set_is_rejected_WHOLE_when_one_alternative_is_bad():
    """Dropping the bad member would narrow the window without saying so, and a
    narrowed window is the silent failure this whole module exists to stop."""
    out = _out(observable=["cmd_ack"])
    out.normalized[0].activation.inputs = {"cmd": [1, "NOT_A_SYMBOL"]}
    errs = [i for i in gate_one(REQ, out, CONTRACT) if i.severity == "error"]
    assert errs and "NOT_A_SYMBOL" in errs[0].message


def test_an_EMPTY_value_set_is_refused():
    """No value satisfies it, so the window can never open -- which at decide
    time reads exactly like a design that never did it."""
    out = _out(observable=["cmd_ack"])
    out.normalized[0].activation.inputs = {"cmd": []}
    errs = [i for i in gate_one(REQ, out, CONTRACT) if i.severity == "error"]
    assert errs and "empty value-set" in errs[0].message


def test_every_alternative_gets_the_WIDTH_check_not_just_the_first():
    out = _out(observable=["cmd_ack"])
    out.normalized[0].activation.inputs = {"cmd": [0, 1, 999]}
    errs = [i for i in gate_one(REQ, out, CONTRACT) if i.severity == "error"]
    assert errs and "999" in errs[0].message
