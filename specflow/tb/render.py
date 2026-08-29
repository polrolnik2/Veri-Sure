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

import logging

import ast
import itertools
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import Issue
from ..ports import classify, idle_values, input_names, pinned_inputs

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

    # Corners first, then random fill. A uniform draw over a 32-bit input is
    # never small, so a decoder is never decoded: `or1200_cfgr` reads a
    # configuration register out of `spr_addr[3:0]` and gates the whole decode
    # on `~|spr_addr[31:4]`, so 64 uniform 32-bit draws left `spr_dat_o` at its
    # reset value for the entire run -- and the design then AGREED with a
    # reference model that declares every output zero forever. The suite passed
    # having exercised nothing, which is a stimulus failure wearing the costume
    # of a verdict.
    #
    # Not a substitute for the testcase agent's stimulus, which is what a real
    # run uses. This is the floor beneath it.
    rng = random.Random(1337)  # noqa: S311 -- reproducibility over entropy
    names = [n for n, _ in inputs]
    corners: list[dict] = []
    for value in (0, 1, 2, 3):
        corners.append({n: min(value, (1 << w) - 1) for n, w in inputs})
    corners.append({n: (1 << w) - 1 for n, w in inputs})
    # One input walked through the small values while the rest sit at zero: a
    # decode is usually a function of ONE field, and a vector that moves every
    # input at once never isolates it.
    for name, width in inputs:
        top = (1 << width) - 1
        for value in (1, 2, 3, top):
            corners.append({n: (min(value, top) if n == name else 0) for n in names})

    seen: set[tuple] = set()
    out: list[dict] = []
    for vector in corners:
        key = tuple(vector[n] for n in names)
        if key not in seen:
            seen.add(key)
            out.append(vector)
        if len(out) >= limit:
            return out
    while len(out) < limit:
        vector = {n: rng.getrandbits(w) for n, w in inputs}
        key = tuple(vector[n] for n in names)
        if key not in seen:
            seen.add(key)
            out.append(vector)
    return out


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


logger = logging.getLogger(__name__)

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
    idle: dict[str, int] | None = None,
    #: Written INTO the testcase rather than left to the environment. `Env` is
    #: constructed inside a cocotb subprocess the harness does not build, which
    #: is the real reason these were environment variables; emitting them here
    #: removes that reason, and a rendered suite then carries its own switches
    #: instead of depending on what happens to be exported when it runs.
    trace_internals: list[str] | None = None,
    compare: str = "",
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
        "# Every input's quiescent value, from the contract. The runtime drives",
        "# all of them to idle before releasing reset so the DUT and the model",
        "# start from the same state; 0 is not idle for an active-low or",
        "# open-drain input, and assuming it was is what let the harness score a",
        "# wrong design above golden.",
        f"IDLE_INPUTS = {dict(idle or {})!r}",
        "",
        "",
        "@cocotb.test()",
        f"async def {_fn_name(tp_uid, suffix)}(dut):",
        f'    env = await Env.start(dut, tp_uid="{tp_uid}", model=Model(),',
        "                          input_ports=INPUT_PORTS, pinned=PINNED_INPUTS,",
    ]
    # EMITTED ONLY WHEN SUPPLIED. `None` means "the caller said nothing", and
    # writing an explicit `[]` for it would OVERRIDE `Env.start`'s environment
    # fallback -- silently switching off internal recording for every existing
    # caller that still sets SPECFLOW_TRACE_INTERNALS. Caught by the harness
    # conformance fixture, which does exactly that.
    if trace_internals is not None:
        lines.append(f"                          trace_internals={list(trace_internals)!r},")
    if compare:
        lines.append(f"                          compare={compare!r},")
    lines += [
        "                          idle=IDLE_INPUTS)",
        "    for stim in STIMULUS:",
        "        await env.drive(stim)",
    ]
    for b in bins:
        lines.append(f'        env.cov.hit("{b["uid"]}")')
    lines += [
        "",
        "    # Registered once, AFTER the stimulus. Each check asks a question",
        "    # about the whole run -- did the DUT produce the same ordered",
        "    # sequence of output states as the reference model -- rather than",
        "    # about one sampled instant per vector. Sampling looked at 3 of 12",
        "    # cycles and a median of 4 of 8 outputs on i2c_master_bit_ctrl, so",
        "    # a faithful oracle scored 77 of 168 not because it was aligned but",
        "    # because most of the divergence was never examined.",
    ]
    for c in checks:
        for signal in c.get("signals") or []:
            lines.append(f'    env.check("{c["uid"]}", "{signal}")')
    lines += ["    await env.finish()", ""]
    return "\n".join(lines)


def _siblings_by_requirement(testplan: list[dict]) -> dict[str, list[str]]:
    """`requirement uid -> the testpoints that cover it`."""
    out: dict[str, list[str]] = {}
    for tp in testplan:
        uid = str(tp.get("uid") or "")
        for ref in tp.get("covers") or []:
            out.setdefault(str(ref).split("@")[0], []).append(uid)
    return out


def _checks_for(tp: dict, checks_by_tp: dict[str, list[dict]],
                by_req: dict[str, list[str]]) -> tuple[list[dict], bool]:
    """This testpoint's checks, falling back to its REQUIREMENT'S.

    A check covers a TESTPOINT and a testpoint covers a REQUIREMENT, so a
    testpoint minted after S3 ran has no check of its own and renders with no
    `env.check(...)` at all -- an empty scoreboard, which the runtime rightly
    calls vacuous, and one such testpoint aborts the whole suite.

    That is what the [O] stimulus loop mints: 78 of a2-i2c's 344 testpoints,
    TP-0266 onward, staged for a requirement whose scenario nothing reached.
    They were invisible until `_persist_grown` started writing them to disk.

    THE CHECK BELONGS TO THE REQUIREMENT, NOT TO THE VECTORS. A new stimulus for
    REQ-0098 is still judged by what REQ-0098 demands -- different vectors, same
    criterion -- so the fallback is the checks of the sibling testpoints that
    cover the same requirement. Nothing is invented, and no check enters the
    suite that S3 did not write.

    Own checks win outright: a testpoint S3 planned for is never second-guessed.
    """
    uid = str(tp.get("uid") or "")
    own = checks_by_tp.get(uid, [])
    if own:
        return own, False
    seen: set[str] = set()
    borrowed: list[dict] = []
    for ref in tp.get("covers") or []:
        for sibling in by_req.get(str(ref).split("@")[0], []):
            if sibling == uid:
                continue
            for check in checks_by_tp.get(sibling, []):
                key = str(check.get("uid") or "")
                if key not in seen:
                    seen.add(key)
                    borrowed.append(check)
    return borrowed, bool(borrowed)


def render_suite(
    *,
    testplan: list[dict],
    bins: list[dict],
    checks: list[dict],
    contract: dict,
    out_dir: Path,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    #: Threaded into every rendered testcase, so a suite carries its own
    #: switches instead of depending on what happens to be exported when it
    #: runs. See `render_testcase`.
    trace_internals: list[str] | None = None,
    compare: str = "",
) -> Manifest:
    out_dir = Path(out_dir)
    tests_dir = out_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    bins_by_tp, checks_by_tp = _by_tp(bins), _by_tp(checks)
    by_req = _siblings_by_requirement(testplan)
    inherited: list[str] = []
    default = default_stimulus(contract)
    ports, pinned = input_names(contract), pinned_inputs(contract)
    idle = idle_values(contract)
    manifest = Manifest()

    for tp in testplan:
        uid = tp["uid"]
        stim = (stimulus_by_tp or {}).get(uid) or default
        tp_checks, borrowed = _checks_for(tp, checks_by_tp, by_req)
        if borrowed:
            inherited.append(uid)
        source = render_testcase(
            tp=tp,
            bins=bins_by_tp.get(uid, []),
            checks=tp_checks,
            stimulus=stim,
            input_ports=ports,
            pinned=pinned,
            idle=idle,
            trace_internals=trace_internals,
            compare=compare,
        )
        name = module_name(uid)
        (tests_dir / f"{name}.py").write_text(source, encoding="utf-8")

        manifest.modules.append(name)
        manifest.testpoints.append(uid)
        manifest.bins += [b["uid"] for b in bins_by_tp.get(uid, [])]
        # DEDUPED, because a check that now runs under two testpoints is still
        # one check. Counting it twice would inflate the coverage denominator
        # with an entry nobody wrote.
        for c in tp_checks:
            if c["uid"] not in manifest.checks:
                manifest.checks.append(c["uid"])

    if inherited:
        logger.info(
            "render: %d testpoint(s) had no check of their own and inherited "
            "their requirement's: %s", len(inherited),
            ", ".join(inherited[:8]) + (" ..." if len(inherited) > 8 else ""))
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
