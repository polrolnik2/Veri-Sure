"""Author a contract for a task, from its SPECIFICATION and nothing else.

    e7_contract.py <task-dir> <out.json>

`build_artifacts` takes `contract_json` as an input and specflow has no stage
that produces one; `eda_agent.ArchitectAgent` does, from `description.txt`.

**THE SPEC IS THE ONLY INPUT, AND `golden_tb_path` IS LEFT UNSET ON PURPOSE.**
`chat()` accepts a golden testbench to sharpen the interface. Passing one here
would put the reference design's own testbench into the contract every stage
below reads, and every span, blindness and audit figure taken afterwards would
be downstream of it.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from eda_agent.architect_agent import ArchitectAgent  # noqa: E402
from eda_agent.config import load_openai_config  # noqa: E402
from eda_agent.contract_linter import lint_contract_json, strip_unsourced  # noqa: E402
from specflow import encoding  # noqa: E402

TASK, OUT = Path(sys.argv[1]), Path(sys.argv[2])
spec = (TASK / "description.txt").read_text(encoding="utf-8")
print(f"{TASK.name}: {len(spec)} bytes of specification", flush=True)


async def _go() -> None:
    out = await ArchitectAgent(load_openai_config()).chat(input_spec=spec)
    blob = out.model_dump() if hasattr(out, "model_dump") else dict(out)
    #: NOTHING THE SPEC DOES NOT STATE, AND ONLY THE DEFINES BESIDES. The
    #: author is told not to generate encodings, constants or latencies; what
    #: it generates anyway is DELETED here, not re-asked. The one source of
    #: values beyond the spec is the design's shared defines header, imported
    #: verbatim for the symbols the spec itself names -- the same header the
    #: benchmark's harness prepends to every compile.
    for line in strip_unsourced(blob, spec):
        print(f"  deleted  {line}")
    for line in encoding.enrich_contract(blob, spec=spec,
                                         defines=encoding.find_defines(TASK)):
        print(f"  imported {line}")
    issues, _ = lint_contract_json(json.dumps(blob), spec)
    for i in issues:
        print(f"  lint {i.severity}: {i.path}: {i.message[:120]}")
    OUT.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    io = blob.get("io") or []
    print(f"  module {blob.get('module_name')!r}: {len(io)} port(s); "
          f"sequential={((blob.get('clocking') or {}).get('is_sequential'))}")
    kids = blob.get("child_assumes") or {}
    print(f"  child_assumes: {sorted(kids) if kids else 'NONE (flat)'}")
    print(f"  wrote {OUT}")


asyncio.run(_go())
