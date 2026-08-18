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
