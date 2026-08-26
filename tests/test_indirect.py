"""Every unobservable requirement is asked whether it is observed INDIRECTLY.

`UNOBSERVABLE` claims no port shows the behaviour, and this pipeline measured
that claim wrong at scale: normalisation called 27 of 77 requirements
unobservable by reading each one's MECHANISM rather than its effect, and 10 of
the 27 already had working checks against real output ports.

Two independent indirections. `observed_via` makes a requirement CHECKABLE --
it is observed at a port its own text does not name. `activated_via` makes it
STAGEABLE -- the state its activation needs has to be reached. They fail
differently: no route to observe is a specification finding, no route to reach
is a testplan one, and a requirement can be perfectly observable and unreachable.
"""

from __future__ import annotations

from specflow.normalize import (
    Activation,
    NormalizedRequirement,
    NormalizeOutput,
    REACH_DEPTH,
    Reach,
    Route,
    gate_indirect,
    reaching,
    resolve_indirect,
)

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "sda_i", "dir": "input", "width": 1},
    {"name": "busy", "dir": "output", "width": 1},
    {"name": "al", "dir": "output", "width": 1},
]}

DISCRIMINATING = ("busy stays low for a glitch narrower than the filter depth "
                  "and does not rise")


def _blind(uid="REQ-0031"):
    return NormalizedRequirement(
        req_uid=uid, activation=Activation(text="a glitch on sda_i"),
        observable=[], unobservable_reason="the filter is internal",
        expectation="no START is detected")


def _seer(uid="REQ-0007"):
    return NormalizedRequirement(
        req_uid=uid, activation=Activation(text="a START is detected"),
        observable=["busy"], expectation="busy rises")


def _out(**kw):
    return NormalizeOutput(normalized=[NormalizedRequirement(**kw)])


# ------------------------------------------------------------- the gate


def test_a_route_naming_one_case_is_rejected():
    """THE VACUITY FAILURE, ONE STAGE EARLY, and harder to see because the route
    looks like progress. A check over "the port shows X" passes any design that
    ever shows X -- including one with none of this behaviour."""
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="busy", through_req="REQ-0007", when="after a glitch",
        shows="busy is low")])
    issues = gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                           known={"REQ-0007", "REQ-0031"})
    assert issues and "HOLDS" in issues[0].message


def test_a_route_naming_both_cases_passes():
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="busy", through_req="REQ-0007", when="after a glitch",
        shows=DISCRIMINATING)])
    assert gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                         known={"REQ-0007", "REQ-0031"}) == []


def test_a_route_through_an_undeclared_port_is_rejected():
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="filter_cnt", through_req="REQ-0007", when="x",
        shows=DISCRIMINATING)])
    issues = gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                           known={"REQ-0007", "REQ-0031"})
    assert any("not a declared output port" in i.message for i in issues)


def test_a_requirement_cannot_be_observed_through_itself():
    """That is the direct case, and the first pass already said there is none."""
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="busy", through_req="REQ-0031", when="x", shows=DISCRIMINATING)])
    issues = gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                           known={"REQ-0031"})
    assert any("through itself" in i.message for i in issues)


def test_an_empty_answer_is_accepted_as_an_honest_no_route():
    """"Nothing observes this" is worth more than a route that does not
    discriminate."""
    assert gate_indirect(_out(req_uid="REQ-0031"), uid="REQ-0031",
                         contract=CONTRACT, known={"REQ-0031"}) == []


# ------------------------------------------------- the closure over hops


def _reachable(uid, via=()):
    return NormalizedRequirement(
        req_uid=uid, observable=["busy"],
        activated_via=[Reach(through_req=t,
                             activation=Activation(text=f"via {t}"))
                       for t in via])


def test_local_hops_are_followed_into_a_full_chain_deepest_first():
    """Normalisation emits ONE hop each; the walk is mechanical. Asking a model
    for the whole chain asks it to hold the state machine in its head, and one
    wrong link invalidates everything after it."""
    by = {r.req_uid: r for r in
          [_reachable("A", ["B"]), _reachable("B", ["C"]), _reachable("C")]}
    chain, why = reaching("A", by)
    assert [h.through_req for h in chain] == ["C", "B"], "drive order"
    assert why == ""


def test_a_cycle_is_a_specification_finding_not_a_hang():
    by = {r.req_uid: r for r in [_reachable("X", ["Y"]), _reachable("Y", ["X"])]}
    chain, why = reaching("X", by)
    assert chain == []
    assert "closes on itself" in why and "Y" in why and "X" in why


def test_a_chain_deeper_than_the_bound_is_reported_rather_than_followed():
    uids = [f"R{i}" for i in range(REACH_DEPTH + 3)]
    by = {u: _reachable(u, [n]) for u, n in zip(uids, uids[1:])}
    by[uids[-1]] = _reachable(uids[-1])
    chain, why = reaching(uids[0], by)
    assert chain == [] and "more likely a misreading" in why


def test_an_input_only_activation_needs_no_chain():
    by = {"A": _reachable("A")}
    assert reaching("A", by) == ([], "")


# ------------------------------------------------------------- the pass


class _Port:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.reply


def _resolve(reply, shapes):
    port = _Port(reply)
    merged, results = resolve_indirect(
        normalized=shapes,
        requirements=[{"uid": s.req_uid, "text": "t"} for s in shapes],
        contract_json="{}", contract=CONTRACT, port=port, fanout=False)
    return merged, results, port


ROUTED = ('{"normalized": [{"req_uid": "REQ-0031", "observed_via": [{"port": '
          '"busy", "through_req": "REQ-0007", "when": "after a glitch", '
          f'"shows": "{DISCRIMINATING}"}}]}}]}}')


def test_a_resolved_requirement_becomes_observable_at_the_route_s_port():
    """`observable` holds the ports it is decidable at BY ANY ROUTE, so every
    downstream stage keeps reading one field."""
    merged, _, _ = _resolve(ROUTED, [_blind(), _seer()])
    got = {n.req_uid: n for n in merged}["REQ-0031"]
    assert got.observable == ["busy"]
    assert got.unobservable_reason == "", "no longer true, so it goes"
    assert got.indirect and got.observed_via[0].through_req == "REQ-0007"


def test_the_other_requirements_are_the_evidence():
    _, _, port = _resolve(ROUTED, [_blind(), _seer()])
    assert "REQ-0007" in port.prompts[0]
    assert "busy" in port.prompts[0]


def test_a_directly_observable_requirement_is_never_asked():
    _, results, port = _resolve(ROUTED, [_seer()])
    assert port.prompts == [] and results == []


def test_an_honest_no_route_leaves_the_requirement_as_it_was():
    """It stays UNOBSERVABLE here; the oracle stage is what turns having been
    ASKED into ABANDONED."""
    merged, _, _ = _resolve('{"normalized": [{"req_uid": "REQ-0031"}]}',
                            [_blind(), _seer()])
    got = {n.req_uid: n for n in merged}["REQ-0031"]
    assert got.unobservable and got.unobservable_reason
    assert got.observed_via == []
