"""Render the cocotb suite from the testplan and coverage model.

Deterministic: no model is consulted here. The renderer owns the module header,
the `@cocotb.test()` wrapper, every `Env.check(...)` call and every
`env.cov.hit(...)` call. A testcase supplies stimulus and nothing else.

That is what makes the vacuity guarantee structural rather than aspirational: a
generated testcase *cannot* contain a dead check, because it does not write
checks. It also means expected values always come from the frozen reference
model, so a testcase cannot smuggle in an oracle that mirrors the design.
"""

from __future__ import annotations

import ast
import itertools
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import Issue
from ..ports import classify, input_names, pinned_inputs

_SAFE = re.compile(r"[^A-Za-z0-9_]")


def module_name(tp_uid: str, suffix: str = "") -> str:
    base = "test_" + _SAFE.sub("", tp_uid.replace("-", ""))
    return f"{base}_{suffix}" if suffix else base


def _fn_name(tp_uid: str, suffix: str = "") -> str:
    base = _SAFE.sub("", tp_uid.replace("-", ""))
    return f"{base}_{suffix}" if suffix else base


def default_stimulus(contract: dict, limit: int = 64) -> list[dict]:
    """Exhaustive when the input space is small, deterministic-random otherwise.

    Exhaustive matters: a sampled sweep can miss exactly the corner the
    specification cared about, and for the small designs this pipeline targets
    the whole space is usually cheap.

    Clock and reset are excluded from the sweep because the runtime owns them:
    `Env.reset()` sequences the reset and calls the model's own `reset()`, so a
    testcase that toggled reset underneath would desynchronise the two. They are
    excluded from the *stimulus*, not from the model's input bundle -- `Env` fills
    them in from the DUT, which is why `tb/ports.py` exists rather than three
    local name sets that each drop a different port.
    """
    _, _, functional = classify(contract)
    widths = {
        str(p.get("name")): int(p.get("width") or 1)
        for p in (contract.get("io") or [])
    }
    inputs = [(name, widths.get(name) or 1) for name in functional]
    if not inputs:
        return [{}]

    total = 1
    for _, w in inputs:
        total *= 1 << w
        if total > limit:
            break

    if total <= limit:
        return [
            dict(zip([n for n, _ in inputs], combo))
            for combo in itertools.product(*[range(1 << w) for _, w in inputs])
        ]

    rng = random.Random(1337)  # noqa: S311 -- reproducibility over entropy
    return [{n: rng.getrandbits(w) for n, w in inputs} for _ in range(limit)]


@dataclass
class Manifest:
    modules: list[str] = field(default_factory=list)
    testpoints: list[str] = field(default_factory=list)
    bins: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "modules": self.modules,
                "testpoints": self.testpoints,
                "bins": sorted(self.bins),
                "checks": sorted(self.checks),
            },
            indent=2,
        ) + "\n"


def _by_tp(items: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for item in items:
        for ref in item.get("covers") or []:
            out.setdefault(ref.split("@")[0], []).append(item)
    return out


def render_testcase(
    *,
    tp: dict,
    bins: list[dict],
    checks: list[dict],
    stimulus: list[dict],
    suffix: str = "",
    input_ports: list[str] | None = None,
    pinned: dict[str, int] | None = None,
) -> str:
    tp_uid = tp["uid"]
    lines = [
        f'"""Generated testcase for {tp_uid}. Do not edit.',
        "",
        f"dimension: {tp.get('dimension', '?')}",
        f"stimulus:  {tp.get('stimulus', '')}",
        f"expected:  {tp.get('expected_response', '')}",
        "",
        "Checks and cover bins are emitted by specflow/tb/render.py from the",
        "coverage model; expected values come from the frozen reference model.",
        "Only the stimulus below is testcase-specific.",
        '"""',
        "",
        "import cocotb",
        "",
        "from ref_model import Model",
        "from specflow.tb.runtime import Env",
        "",
        f"STIMULUS = {stimulus!r}",
        "",
        "# Every declared input, not only the ones the stimulus drives. The runtime",
        "# completes the reference model's bundle from the DUT so a model that reads",
        "# a runtime-owned port sees it instead of raising KeyError.",
        f"INPUT_PORTS = {list(input_ports or [])!r}",
        f"PINNED_INPUTS = {dict(pinned or {})!r}",
        "",
        "",
        "@cocotb.test()",
        f"async def {_fn_name(tp_uid, suffix)}(dut):",
        f'    env = await Env.start(dut, tp_uid="{tp_uid}", model=Model(),',
        "                          input_ports=INPUT_PORTS, pinned=PINNED_INPUTS)",
        "    for stim in STIMULUS:",
        "        await env.drive(stim)",
    ]
    for b in bins:
        lines.append(f'        env.cov.hit("{b["uid"]}")')
    lines.append("        expected = env.expect(stim)")
    for c in checks:
        for signal in c.get("signals") or []:
            lines.append(
                f'        env.check("{c["uid"]}", "{signal}", expected, stim)'
            )
    lines += ["    await env.finish()", ""]
    return "\n".join(lines)


def render_suite(
    *,
    testplan: list[dict],
    bins: list[dict],
    checks: list[dict],
    contract: dict,
    out_dir: Path,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
) -> Manifest:
    out_dir = Path(out_dir)
    tests_dir = out_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    bins_by_tp, checks_by_tp = _by_tp(bins), _by_tp(checks)
    default = default_stimulus(contract)
    ports, pinned = input_names(contract), pinned_inputs(contract)
    manifest = Manifest()

    for tp in testplan:
        uid = tp["uid"]
        stim = (stimulus_by_tp or {}).get(uid) or default
        source = render_testcase(
            tp=tp,
            bins=bins_by_tp.get(uid, []),
            checks=checks_by_tp.get(uid, []),
            stimulus=stim,
            input_ports=ports,
            pinned=pinned,
        )
        name = module_name(uid)
        (tests_dir / f"{name}.py").write_text(source, encoding="utf-8")

        manifest.modules.append(name)
        manifest.testpoints.append(uid)
        manifest.bins += [b["uid"] for b in bins_by_tp.get(uid, [])]
        manifest.checks += [c["uid"] for c in checks_by_tp.get(uid, [])]

    (out_dir / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- GATE G5


def _emitted(source: str, method: str) -> set[str]:
    """UIDs passed as the first argument to `env.<method>(...)` calls."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None)
        if name != method or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(first.value)
    return found


def gate_g5(*, out_dir: Path, manifest: Manifest, bins: list[dict], checks: list[dict]) -> list[Issue]:
    """G5: the rendered suite is structurally sound, checked without a simulator.

    This is where the vacuity guarantee becomes mechanical. A check that exists
    in the coverage model but is never emitted as a call would be a check that
    can never fail -- caught here, before anything runs.
    """
    issues: list[Issue] = []
    tests_dir = Path(out_dir) / "tests"

    emitted_checks: set[str] = set()
    emitted_bins: set[str] = set()

    for name in manifest.modules:
        path = tests_dir / f"{name}.py"
        if not path.exists():
            issues.append(Issue("error", f"tests/{name}.py", "declared in the manifest but not written"))
            continue
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            issues.append(Issue("error", f"tests/{name}.py", f"does not parse: {exc}"))
            continue
        emitted_checks |= _emitted(source, "check")
        emitted_bins |= _emitted(source, "hit")

    for c in checks:
        if c["uid"] not in emitted_checks:
            issues.append(
                Issue("error", f"check.{c['uid']}",
                      "in the coverage model but never emitted as an Env.check call; "
                      "it could never fail", "uncovered")
            )
    for b in bins:
        if b["uid"] not in emitted_bins:
            issues.append(
                Issue("error", f"bin.{b['uid']}",
                      "in the coverage model but never emitted as a cov.hit call; "
                      "it could never be reached", "uncovered")
            )

    for uid in emitted_checks - {c["uid"] for c in checks}:
        issues.append(
            Issue("error", f"tests.{uid}", "emits a check that is not in the coverage model",
                  "orphaned")
        )

    return issues
