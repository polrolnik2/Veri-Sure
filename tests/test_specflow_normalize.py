

def test_the_prompt_lists_every_name_the_gate_admits_in_observable():
    """**THE LIST THE MODEL IS SHOWN AND THE LIST THE GATE CHECKS MUST BE ONE
    LIST.** `shared_prefix`'s own docstring says why it exists: "the gate
    validates against a list, and a model that was never shown the list guesses
    names out of prose that describes internal signals. On i2c that cost 12
    repair rounds in 41 testpoints."

    They drifted anyway. `gate_one` computes `observable_here = {**outputs,
    **probes}` and rejects with "not a declared output port OR PROBE"; the
    prompt filtered `dir == "output"` and told the model those were the ONLY
    names `observable` may contain. The model obeyed the prompt.

    Measured on a full run before this: 22 probes declared, 14
    cross-constraints, and 0 of 165 normalized forms naming a single probe
    anywhere -- so every probe was orphaned and the requirements that needed
    one took `observable: []` and were abandoned as having no observation
    route.
    """
    import json

    from specflow import normalize as N

    contract = {"io": [
        {"name": "q", "dir": "output", "width": 8},
        {"name": "a", "dir": "input", "width": 8},
        {"name": "in_idle", "dir": "probe", "width": 1},
        {"name": "cnt_expired", "dir": "probe", "width": 1},
    ]}
    prompt = N.shared_prefix(json.dumps(contract), contract)

    #: EVERY name the gate would accept in `observable` is shown to the model
    #: AS A LIST. Not merely present in the prompt: `contract_json` is included
    #: verbatim and already contains every port, and the docstring's whole
    #: point is that a model reading the contract still "guesses names out of
    #: prose". A first version of this test asserted `name in prompt` and
    #: passed with the probe block deleted.
    outputs = {p["name"] for p in contract["io"] if p["dir"] == "output"}
    probes = {p["name"] for p in contract["io"] if p["dir"] == "probe"}
    assert "DECLARED PROBES" in prompt, "the probe list is not offered at all"
    listed = prompt[prompt.index("DECLARED PROBES"):]
    for name in probes:
        assert name in listed, f"probe {name!r} is admissible but never listed"
    shown = prompt[prompt.index("output_ports"):]
    for name in outputs:
        assert name in shown, f"output {name!r} is admissible but never listed"

    #: And a probe is not an input, so the prompt must route a condition on one
    #: to `opens_on` rather than to `activation.inputs`, which is input-only
    #: because `check_static` decides it from the stimulus steps alone.
    assert "opens_on" in prompt
    for name in probes:
        i = prompt.index("input_ports")
        assert name not in prompt[i:], (
            f"{name!r} is offered as an activation input; a probe is not driven")

    #: A contract with no probes gets no probe block -- the note must not
    #: invite names that do not exist.
    bare = {"io": [p for p in contract["io"] if p["dir"] != "probe"]}
    assert "DECLARED PROBES" not in N.shared_prefix(json.dumps(bare), bare)
