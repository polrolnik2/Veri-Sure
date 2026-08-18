"""The seam between the specflow oracle and the RTL repair agent.

`run_specflow_node` reuses `RTLEditor`, which was written for the monolithic
SystemVerilog path. The reuse was believed to need no editor changes because the
editor is parameterised on a reviewer object -- but `chat()` also read
`<run>/tb.sv` off disk to fill its `generated_tb` prompt slot, and specflow never
writes that file. The first repair iteration died with `FileNotFoundError`, so
the specflow repair loop had never once run.

These cases pin both halves: the editor must not require the file, and what
specflow hands it instead must actually describe the oracle.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from specflow.integration import describe_oracle

REPO = Path(__file__).resolve().parents[1]


def _suite(tmp_path: Path, *, failing: list[str]) -> Path:
    suite = tmp_path / "suite"
    (suite / "results").mkdir(parents=True)
    for uid in ("TP-0001", "TP-0002", "TP-0003"):
        (suite / "results" / f"{uid}.json").write_text(
            json.dumps({
                "tp_uid": uid,
                "status": "FAIL" if uid in failing else "PASS",
                "checks_invoked": ["CHK-0001"],
                "checks_failed": ["CHK-0001"] if uid in failing else [],
                "bins_hit": ["BIN-0001"],
                "mismatches": ([{"check": "CHK-0001", "got": 0, "expected": 1, "ctx": {"a": 1}}]
                               if uid in failing else []),
            }),
            encoding="utf-8",
        )
    return suite


TESTPLAN = [
    {"uid": "TP-0001", "dimension": "D1", "stimulus": "drive a=1",
     "expected_response": "y goes high", "check_method": "compare y"},
    {"uid": "TP-0002", "dimension": "D2", "stimulus": "hold reset",
     "expected_response": "y stays low", "check_method": "compare y"},
    {"uid": "TP-0003", "dimension": "D3", "stimulus": "sweep a",
     "expected_response": "y tracks a", "check_method": "compare y"},
]


def test_editor_chat_does_not_require_a_systemverilog_testbench():
    """The signature change that unblocks the loop, asserted at the seam."""
    from eda_agent.rtl_editor import RTLEditor

    params = inspect.signature(RTLEditor.chat).parameters
    assert "tb_text" in params, "chat() cannot be driven without a tb.sv on disk"
    assert params["tb_text"].default is None, "the SV path must keep its behaviour"


def test_describe_oracle_leads_with_the_reference_model(tmp_path):
    """The model is the expected behaviour, so it comes first and comes whole."""
    suite = _suite(tmp_path, failing=["TP-0001"])
    model = tmp_path / "ref_model.py"
    model.write_text("class Model:\n    OUTPUT_PORTS = ['y']\n", encoding="utf-8")

    text = describe_oracle(suite_dir=suite, refmodel_path=model, testplan=TESTPLAN)

    assert "NOT a SystemVerilog testbench" in text
    assert "OUTPUT_PORTS = ['y']" in text
    # only the failing testpoint's plan is included -- the passing ones are noise
    assert "TP-0001" in text
    assert "TP-0002" not in text and "TP-0003" not in text
    assert "drive a=1" in text


def test_describe_oracle_never_truncates_the_model_to_fit_the_testplan(tmp_path):
    """Half a specification is worse than none: the agent would infer the rest
    from the RTL, which is the direction this pipeline exists to prevent."""
    suite = _suite(tmp_path, failing=["TP-0001", "TP-0002", "TP-0003"])
    model = tmp_path / "ref_model.py"
    body = "\n".join(f"    def _req_{i:04d}(self, i, o): o['y'] = {i}" for i in range(200))
    model.write_text("class Model:\n" + body + "\n", encoding="utf-8")

    text = describe_oracle(
        suite_dir=suite, refmodel_path=model, testplan=TESTPLAN,
        max_chars=len("class Model:\n" + body) + 400,
    )
    assert "_req_0199" in text, "the model was truncated to make room for the testplan"


def test_describe_oracle_survives_a_missing_model(tmp_path):
    suite = _suite(tmp_path, failing=[])
    text = describe_oracle(suite_dir=suite, refmodel_path=tmp_path / "nope.py")
    assert "unreadable" in text


@pytest.mark.parametrize("name", ["tb_text", "tb_clip_chars"])
def test_specflow_node_passes_the_oracle_through(name):
    """The call site, not just the signature: the node must actually supply it."""
    source = (REPO / "eda_agent" / "specflow_node.py").read_text(encoding="utf-8")
    call = source[source.index("await editor.chat("):]
    call = call[: call.index("\n        )")]
    assert f"{name}=" in call, f"specflow_node does not pass {name} to editor.chat"


# ------------------------------------- what actually reaches the repair agent


def _records(uids_and_rows):
    return [
        {
            "testpoint": uid,
            "failed_checks": [f"CHK-{uid[-4:]}"],
            "failed_signals": sorted({r["signal"] for r in rows}),
            "mismatches": rows,
        }
        for uid, rows in uids_and_rows
    ]


def _row(signal, step, got=0, expected=1, **ctx):
    return {"check": "CHK-0001", "signal": signal, "step": step,
            "got": got, "expected": expected, "ctx": ctx or {"a": 1}}


def test_every_failing_testpoint_carries_a_concrete_value():
    """The budget is per testpoint, not global.

    A single global cap of 40 spent all 40 rows on the first failing testpoint.
    On i2c_master_bit_ctrl that left 21 of 22 reduced to a header, so the agent
    knew which outputs diverged and had no value for any of them.
    """
    from eda_agent.specflow_node import format_failures

    payload = _records(
        (f"TP-{i:04d}", [_row("y", s, a=s) for s in range(30)]) for i in range(22)
    )
    text = format_failures(payload)
    carrying = 0
    current = None
    for line in text.splitlines():
        if line.startswith("["):
            current = line
        elif "expected=" in line and current is not None:
            carrying += 1
            current = None
    assert carrying == 22, f"only {carrying} of 22 testpoints carry a value"
    assert "omitted" in text, "a truncated list must say it was truncated"


def test_repeated_identical_mismatches_collapse_with_their_step_range():
    """A step held for several cycles must not cost several lines of budget."""
    from eda_agent.specflow_node import format_failures

    rows = [_row("y", s) for s in range(5)]          # identical but for step
    text = format_failures(_records([("TP-0001", rows)]))
    value_lines = [x for x in text.splitlines() if "expected=" in x]
    assert len(value_lines) == 1, value_lines
    assert "@steps0-4" in value_lines[0] and "(x5)" in value_lines[0]


def test_a_single_step_reports_its_index_not_a_range():
    from eda_agent.specflow_node import format_failures

    text = format_failures(_records([("TP-0001", [_row("y", 7)])]))
    assert "@step7" in text and "@steps" not in text


def test_the_structured_payload_is_not_run_through_the_systemverilog_filter():
    """The regression that emptied the excerpt.

    `_summarize_sim_log_json` recognises a value row only if the line contains
    the literal word "mismatch"; specflow rows read "expected=1 got=0". With
    nothing recognised it falls back to the *last 40 lines* -- a rule written
    for a build transcript, where the useful part is at the bottom. A structured
    report puts the first failing testpoints at the top, so on the real
    i2c_master_bit_ctrl payload the debugger received 22 headers and zero
    concrete values.

    Sized to reproduce that: more than 40 lines, values not only at the end.
    """
    import json as _json

    from eda_agent.rtl_editor import _summarize_sim_log_json
    from eda_agent.specflow_node import format_failures

    payload = _records(
        (f"TP-{i:04d}", [_row("y", s, a=s) for s in range(4)]) for i in range(22)
    )
    stdout = format_failures(payload)
    assert len(stdout.splitlines()) > 40 and stdout.count("expected=") >= 22

    filtered = _summarize_sim_log_json(_json.dumps({"stdout": stdout, "stderr": ""}))
    assert filtered.count("expected=") < stdout.count("expected="), (
        "the SV path no longer loses rows; this guard can be retired"
    )
    assert "TP-0000" not in filtered, "the tail-40 fallback no longer drops the head"

    passed = _summarize_sim_log_json(
        _json.dumps({"format": "specflow", "stdout": stdout, "stderr": ""})
    )
    assert passed.count("expected=") == stdout.count("expected=")
    assert "TP-0000" in passed and "TP-0021" in passed


def test_the_runtime_records_which_step_diverged():
    """Two identical context dicts at different points in a stimulus sequence
    are two different situations on a stateful design."""
    from specflow.tb.runtime import Scoreboard

    sb = Scoreboard()
    sb.check("CHK-0001", 0, 1, {"a": 1}, signal="y", step=4)
    assert sb.mismatches[0]["step"] == 4
    assert sb.mismatches[0]["signal"] == "y"
