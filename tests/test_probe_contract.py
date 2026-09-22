"""The contract linter admits `dir: "probe"`, and owns every rule about one.

A probe is a specification term made observable -- `in_lrefill3` is true exactly
when the FSM is in the state the spec calls LREFILL3 -- so that a check can NAME
the moment its requirement is about instead of proxying it through a combination
of outputs. The proxy is lossy, and every unlicensed path it admits is a check
that convicts a correct design.

What makes that safe is the licensing span. A probe must quote the specification
text that licenses it, verbatim, because the stage that proposes probes runs
before any design exists: anything it cannot quote, it is inventing.
"""
from __future__ import annotations

from pathlib import Path

import json

from eda_agent.contract_linter import (PORT_DIRECTIONS, lint_contract_json,
                                        probe_issues)

SPEC = (Path(__file__).parent / "fixtures/probes/spec.txt").read_text()


def _probe(**kw) -> dict:
    """A valid probe. Each test breaks exactly one thing about it."""
    entry = {
        "name": "in_lrefill3",
        "dir": "probe",
        "width": 1,
        "licensed_by": ["REQ-0017"],
        # Deliberately quoted ACROSS THE SPEC'S LINE WRAP. A span lifted from a
        # wrapped paragraph carries the wrap, so a byte-exact comparison would
        # refuse the honest quotation and teach the extractor to quote single
        # words instead of sentences.
        "spans": ["the FSM advances\nto LREFILL3"],
    }
    entry.update(kw)
    return entry


def test_a_valid_probe_is_accepted() -> None:
    assert probe_issues([_probe()], SPEC) == []


def test_b_a_probe_must_be_one_bit() -> None:
    """A wider probe would need an encoding the specification never states.

    That is the defect that broke ten checks through `cmd`, and it has a second
    edge here: the witness holds the state as a string and the RTL as an integer,
    so only a boolean means the same thing on both sides.
    """
    issues = probe_issues([_probe(width=2)], SPEC)
    assert [i.path for i in issues] == ["io[0].width"]


def test_c_a_probe_no_requirement_licenses_is_refused() -> None:
    issues = probe_issues([_probe(licensed_by=[])], SPEC)
    assert [i.path for i in issues] == ["io[0].licensed_by"]


def test_d_a_span_must_be_in_the_specification() -> None:
    """The load-bearing rule: quoted, never paraphrased."""
    issues = probe_issues([_probe(spans=["the FSM advances to CRESET"])], SPEC)
    assert [i.path for i in issues] == ["io[0].spans"]
    assert "not in the specification" in issues[0].message


def test_e_two_probes_quoting_one_sentence_WARNS_and_does_not_refuse() -> None:
    """Demoted from an error, on measurement rather than on caution.

    It was written to catch the collapse failing -- three phrasings of one state
    shipped as three probes. It CANNOT: three phrasings carry three different
    spans, so a same-span test never sees them. What it does catch is one
    sentence naming two distinct signals, which is ordinary English and ordinary
    hardware.

    Run against k1 it fired twice, and both tables were right: "either the store
    or load flag is set" licenses `store_flag` and `load_flag`, and a sentence
    about decrementing `cnt` inside the refill state licenses both `in_lrefill3`
    and `cnt_nonzero`. Two of two honest cases blocked, none of its target case
    caught.

    Kept as a warning: a reviewer reading the stage's report can still use it as
    weak evidence of a duplicate. What actually prevents two names for one thing
    is the merged single call, with the orphan report as its backstop.
    """
    issues = probe_issues([_probe(), _probe(name="in_refilling")], SPEC)
    assert [i.path for i in issues] == ["io[1].spans"]
    assert [i.severity for i in issues] == ["warning"]
    assert not any(i.severity == "error" for i in issues), (
        "a shared sentence must not block an otherwise valid table")


def test_f_a_config_hypothesis_needs_its_own_span() -> None:
    """A config key existing is not the specification stating a dependency.

    This is the one thing a probe may say about a design, and it is a hypothesis
    rather than a verdict: it exists so a later PROOF of unreachability reads as
    "legitimately absent" instead of "the design is missing a required state".
    Letting it be inferred from a key would be inferring a design fact from spec
    text before any design exists.
    """
    gated = {"key": "OR1200_DC_STORE_REFILL", "value": False}
    entry = _probe(name="in_srefill4",
                   spans=["the SREFILL4 state does not exist"],
                   config_gated=gated)
    assert [i.path for i in probe_issues([entry], SPEC)] == ["io[0].config_gated"]

    stated = dict(gated, span="Store-miss refill is present only when "
                              "OR1200_DC_STORE_REFILL is defined")
    assert probe_issues([_probe(name="in_srefill4",
                                spans=["the SREFILL4 state does not exist"],
                                config_gated=stated)], SPEC) == []


def _contract(*extra: dict) -> str:
    """The linter reads contract JSON TEXT, which is what a stage hands it."""
    return json.dumps({
        "source_of_truth": "spec",
        "module_name": "or1200_dc_fsm",
        "io": [
            {"name": "clk", "dir": "input", "width": 1},
            {"name": "burst", "dir": "output", "width": 1},
            *extra,
        ],
        "clocking": {"is_sequential": True,
                     "clock": {"name": "clk", "edge": "posedge"}},
    })


def test_g_the_linter_accepts_a_contract_carrying_a_probe() -> None:
    """The whole point of step 1: this is the one hard blocker.

    Before this, `lint_contract_json` emitted an `error` for any `dir` outside
    the three Verilog directions, so no stage downstream could be tried at all.
    """
    issues, _ = lint_contract_json(_contract(_probe()))
    assert [i.message for i in issues if i.severity == "error"] == []


def test_g_a_probe_does_not_join_the_outputs_set() -> None:
    """`outputs` feeds the spec-header cross-check, and headers have no probes.

    A specification's module header declares the ports the module was written
    with. A probe is a term its PROSE uses. Counting one as an output would
    report every probe as a port the contract has and the header lost.
    """
    with_probe, _ = lint_contract_json(_contract(_probe()), spec=SPEC)
    without, _ = lint_contract_json(_contract(), spec=SPEC)
    assert [i.message for i in with_probe] == [i.message for i in without]


def test_an_unknown_direction_is_still_refused() -> None:
    """Widening the set must not have opened it."""
    issues, _ = lint_contract_json(_contract({"name": "x", "dir": "wire", "width": 1}))
    assert any(i.path == "io[2].dir" for i in issues if i.severity == "error")
    assert PORT_DIRECTIONS == {"input", "output", "inout", "probe"}


def test_no_other_site_refuses_a_probe() -> None:
    """The linter is the ONLY hard blocker, which is what makes this cheap.

    Roughly fifteen sites re-derive a port list inline with a direction test, and
    a probe fails every one of them -- so it is excluded by DEFAULT and each
    inclusion is deliberate. The two that test the three-direction set outside
    this module (`asserter`, `boolean_proofer`) must SKIP a probe, never reject
    it: a shipped assertion and a boolean miter both compare against golden RTL,
    which has no probes at all.
    """
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted((root / "eda_agent").glob("*.py")) + \
            sorted((root / "specflow").rglob("*.py")):
        if path.name == "contract_linter.py":
            continue
        lines = path.read_text().splitlines()
        for n, line in enumerate(lines):
            if 'not in {"input", "output", "inout"}' not in line:
                continue
            # `continue` on the next line is a skip; anything else is a refusal.
            nxt = lines[n + 1].strip() if n + 1 < len(lines) else ""
            if nxt != "continue":
                offenders.append(f"{path.relative_to(root)}:{n + 1} -> {nxt}")
    assert offenders == []


def test_the_run_WRITES_DOWN_the_contract_it_is_working_to(tmp_path) -> None:
    """`probes.augmented` folds the probe table into `contract["io"]` and every
    stage below works to that object -- and the run used to throw it away. The
    only `contract.json` on disk was the INPUT one, which declares none of them.

    So the interface artifact a consumer reads disagreed with the interface the
    checks were written against, and everything that scored a finished run
    rebuilt the in-force contract by hand from `probes.json`. The tree has
    already recorded what that costs: a run scored against a contract that was
    not the one in force.
    """
    from specflow.probes import write_contract

    contract = {"module_name": "m", "io": [
        {"name": "q", "dir": "output", "width": 1},
        {"name": "in_lrefill3", "dir": "probe", "width": 1},
    ], "probes": ["in_lrefill3"]}
    path = write_contract(tmp_path, contract)

    assert path == tmp_path / "specflow" / "contract.json"
    back = json.loads(path.read_text(encoding="utf-8"))
    assert back["probes"] == ["in_lrefill3"]
    #: The probe is in `io`, as a port of the interface, not only in a sidecar
    #: list a reader has to know to go looking for.
    assert {"name": "in_lrefill3", "dir": "probe", "width": 1} in back["io"]


def test_a_probe_the_design_does_not_expose_is_a_CONFORMANCE_GAP() -> None:
    """A probe is a `dir: "probe"` entry in the contract, so a design is
    REQUIRED to expose it. A design that does not has not implemented its
    interface -- that is a verdict of its own, and it is not the same event as
    a design violating a requirement.

    Measured with a module declaring the contract's ports and tying every
    output to a constant: **14 pass, 0 FAIL, 108 abstain of 122**. A design
    that does nothing at all, passing, because 106 of the 122 checks name a
    probe it never declared and a check reading absent state abstains. Reported
    as abstentions, that reads as the checks being unable to judge; reported as
    conformance, it reads as the design not having an interface to judge.
    """
    from specflow.probes import declared_probes, not_exposed

    contract = {"io": [
        {"name": "q", "dir": "output", "width": 1},
        {"name": "idle", "dir": "probe", "width": 1},
        {"name": "cscl", "dir": "probe", "width": 1},
    ], "probes": ["idle", "cscl"]}

    assert declared_probes(contract) == ("idle", "cscl")
    assert not_exposed(contract, ["q", "idle", "cscl"]) == ()
    assert not_exposed(contract, ["q", "idle"]) == ("cscl",)
    #: A design exposing none of them is the stub, and the gap is the whole set
    #: rather than silence.
    assert not_exposed(contract, ["q"]) == ("idle", "cscl")


def test_declared_probes_reads_io_when_no_probes_list_is_carried() -> None:
    """`augmented` writes both, but a hand-written contract may carry only the
    `io` entries -- and the `io` entry is the one that makes it a port."""
    from specflow.probes import declared_probes

    assert declared_probes({"io": [
        {"name": "q", "dir": "output"},
        {"name": "idle", "dir": "probe"}]}) == ("idle",)


def test_build_artifacts_WRITES_the_contract_on_both_probe_paths() -> None:
    """A SOURCE-LEVEL PIN, and it is not belt-and-braces. A call site inside
    `build_artifacts` is unreachable from any unit test here, and deleting one
    has twice passed every behavioural test on this branch.

    Both paths owe the file. The fresh path folds the table in after
    `run_probes`; the REUSE path folds the same table in from `probes.json`
    without calling the stage at all, and a resumed run that skipped it would
    leave whichever contract was written last, or none.
    """
    import inspect

    from specflow import integration

    src = inspect.getsource(integration.build_artifacts)
    assert src.count("write_contract(run_dir, contract)") == 2, (
        "the contract is no longer written on both probe paths")
    #: And it is written where the probes are actually IN it -- after the fold,
    #: never before. A contract written before the table is folded in declares
    #: no probes, which is the state this whole change exists to end.
    fold = src.index("fold_in(contract, entries)")
    assert src.index("write_contract(run_dir, contract)") > fold


def test_folding_the_probe_table_in_TWICE_does_not_double_the_interface() -> None:
    """Appending was safe only while a contract could not already carry probes.

    It cannot be any more: `write_contract` writes the in-force contract back,
    so a resumed run reads one that already has them. Caught in the first run
    that did -- **48 `dir: "probe"` entries in `io` for 24 declared probes**.
    Nothing errors on that; it quietly doubles the interface.
    """
    from specflow.probes import declared_probes, fold_in

    base = {"io": [{"name": "q", "dir": "output", "width": 1}]}
    entries = [{"name": "idle", "dir": "probe", "width": 1},
               {"name": "cscl", "dir": "probe", "width": 1}]

    once = fold_in(base, entries)
    twice = fold_in(once, entries)
    assert once == twice, "the fold is not idempotent"
    assert len([p for p in twice["io"] if p.get("dir") == "probe"]) == 2
    assert declared_probes(twice) == ("idle", "cscl")
    #: The real port survives, and keeps its place ahead of the table.
    assert twice["io"][0]["name"] == "q"


def test_a_probe_the_new_table_drops_does_not_survive_in_the_interface() -> None:
    """The table SUPERSEDES. A probe the stage no longer nominates must not stay
    declared -- a design would still be obliged to expose it, and every check
    reading it would still be judged, against a name the run no longer knows."""
    from specflow.probes import declared_probes, fold_in

    had = fold_in({"io": [{"name": "q", "dir": "output"}]},
                  [{"name": "idle", "dir": "probe", "width": 1},
                   {"name": "gone", "dir": "probe", "width": 1}])
    assert declared_probes(had) == ("idle", "gone")
    now = fold_in(had, [{"name": "idle", "dir": "probe", "width": 1}])
    assert declared_probes(now) == ("idle",)
    assert all(p.get("name") != "gone" for p in now["io"])


def test_a_REJECTED_probe_table_is_still_written_down(tmp_path) -> None:
    """`run_probes` hands back the ORIGINAL contract when its gate cannot be
    satisfied, and the caller only wrote `probes.json` when the contract came
    back WITH probes -- so a gate failure left no artifact at all and the reason
    survived as one `logger.warning`.

    Measured on an end-to-end run: "probes: no usable probe table (1 issue(s))",
    and which issue could not be recovered from anything on disk. That run
    authored its whole check set with every state term unnameable -- a
    materially different configuration from the run before it, where 106 of 122
    checks read a probe -- and no artifact said so.
    """
    from specflow.probes import ProbeEntry, ProbeOutput, write_artifacts
    from specflow.schema import Issue
    from specflow.stage import StageResult

    out = ProbeOutput(probes=[ProbeEntry(name="idle", spans=["the idle state"],
                                    licensed_by=["REQ-1"],
                                    notes="the FSM is idle")])
    res = StageResult(out, [Issue("error", "probes[0].span",
                                  "the span is not in the specification")], 1)
    write_artifacts(tmp_path, {}, res, accepted=False)

    blob = json.loads((tmp_path / "specflow" / "probes.json").read_text())
    assert blob["accepted"] is False
    #: NOT under `probes`: the reuse path re-gates whatever it finds there, and
    #: a reader must not have to re-gate a file to learn its contents were
    #: refused.
    assert blob["probes"] == []
    assert [p["name"] for p in blob["rejected"]] == ["idle"]
    #: And the reason, which is the whole point.
    assert any("not in the specification" in i["message"]
               for i in blob["issues"])


def test_an_ACCEPTED_probe_table_still_lands_under_probes(tmp_path) -> None:
    """The rejection path must not change the normal one."""
    from specflow.probes import ProbeEntry, ProbeOutput, write_artifacts
    from specflow.stage import StageResult

    out = ProbeOutput(probes=[ProbeEntry(name="idle", spans=["the idle state"],
                                    licensed_by=["REQ-1"], notes="idle")])
    write_artifacts(tmp_path, {}, StageResult(out, [], 0))
    blob = json.loads((tmp_path / "specflow" / "probes.json").read_text())
    assert [p["name"] for p in blob["probes"]] == ["idle"]
    assert blob["accepted"] is True
    assert blob["rejected"] == []


def _entry(name, span, req="REQ-1", notes="a state"):
    from specflow.probes import ProbeEntry
    return ProbeEntry(name=name, notes=notes, licensed_by=[req], spans=[span])


def test_one_unlicensed_probe_does_not_discard_the_LICENSED_ones() -> None:
    """**THE LICENSING ARGUMENT IS PER PROBE, AND THE GATE WAS ALL-OR-NOTHING.**
    Each probe carries its own `spans` and `licensed_by`, and the reason a
    half-accepted table is refused -- "every stage below would be built on names
    that failed their licensing" -- is an argument about the names that FAILED,
    not the ones beside them.

    Measured: two of four end-to-end runs lost their entire table this way. The
    last nominated 27 probes and was refused after six repair rounds over one
    error -- `write_sequence` quoting a paraphrase rather than a verbatim span
    -- then authored its whole check set with no state term nameable, when 26 of
    the 27 were licensed. Replaying that exact table through `salvage` keeps 26
    and drops `write_sequence` alone.
    """
    from specflow.probes import ProbeOutput, gate, salvage

    spec = ("The controller enters the idle state after reset. "
            "During a WRITE command the controller releases SCL.")
    reqs = [{"uid": "REQ-1", "text": "idle after reset"}]
    contract = {"module_name": "m", "io": [{"name": "q", "dir": "output"}]}
    out = ProbeOutput(probes=[
        _entry("idle", "The controller enters the idle state after reset."),
        #: A PARAPHRASE, not a quote -- these words are not in the text.
        _entry("write_sequence",
               "During a WRITE the controller lets SCL float high"),
    ])
    issues = gate(out, contract=contract, spec=spec, requirements=reqs)
    assert [i for i in issues if i.severity == "error"], "the fixture no longer fails"

    kept, dropped = salvage(out, issues, contract=contract, spec=spec,
                            requirements=reqs)
    assert kept is not None, "the licensed probe was discarded with the other"
    assert [p.name for p in kept.probes] == ["idle"]
    assert dropped == ["write_sequence"]


def test_a_finding_that_names_no_probe_still_refuses_the_TABLE() -> None:
    """A row can only be salvaged by dropping a row. A finding about the table
    itself is attached to no index and cannot be repaired that way, so it must
    refuse everything -- otherwise salvage becomes a way to ignore exactly the
    errors it cannot fix.

    The remainder here gates CLEANLY on its own, so nothing but this guard
    stands between the table-level finding and a false accept. A fixture whose
    remainder fails for some other reason does not exercise it.
    """
    from specflow.probes import ProbeOutput, gate, salvage
    from specflow.schema import Issue

    spec = ("The controller enters the idle state after reset. "
            "During a WRITE command the controller releases SCL.")
    reqs = [{"uid": "REQ-1", "text": "idle after reset"}]
    contract = {"module_name": "m", "io": [{"name": "q", "dir": "output"}]}
    out = ProbeOutput(probes=[
        _entry("idle", "The controller enters the idle state after reset."),
        _entry("write_sequence",
               "During a WRITE the controller lets SCL float high"),
    ])
    #: The remainder after dropping index 1 is clean -- proven, not assumed.
    only_first = ProbeOutput(probes=[out.probes[0]])
    assert not [i for i in gate(only_first, contract=contract, spec=spec,
                                requirements=reqs) if i.severity == "error"]

    indexed = [i for i in gate(out, contract=contract, spec=spec,
                               requirements=reqs) if i.severity == "error"]
    assert indexed, "the fixture no longer produces a droppable finding"

    kept, _ = salvage(out, indexed + [Issue("error", "probes.response",
                                            "Parse Error: ...")],
                      contract=contract, spec=spec, requirements=reqs)
    assert kept is None, (
        "a table-level finding was salvaged away by dropping a row")


def test_salvaging_EVERY_probe_is_the_same_as_refusing_the_table() -> None:
    """Dropping the last row leaves no table, and an empty table is the state
    this whole path exists to avoid reporting as a success."""
    from specflow.probes import ProbeOutput, gate, salvage

    spec = "The controller enters the idle state after reset."
    reqs = [{"uid": "REQ-1", "text": "idle"}]
    contract = {"module_name": "m", "io": [{"name": "q", "dir": "output"}]}
    out = ProbeOutput(probes=[_entry("only", "a paraphrase that is not present")])
    issues = gate(out, contract=contract, spec=spec, requirements=reqs)
    kept, dropped = salvage(out, issues, contract=contract, spec=spec,
                            requirements=reqs)
    assert kept is None
    assert dropped == ["only"]
