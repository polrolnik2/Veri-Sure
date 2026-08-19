"""G4: the four checks that decide whether the reference model can be trusted.

All decidable without a simulator, so this runs under plain pytest. That is a
consequence of the model importing nothing from cocotb.

Check 4 -- no RTL contamination -- is the one that is never cut. It is the
structural version of the oracle-independence prompt rule, and the ISSTA-2026
misguidance result is that the implementation's *presence in context* is the
cause of a mirrored oracle, not the model's intent. Removing it is stronger than
forbidding its use. Here the removal is enforced twice: `compose.py` does not put
the RTL in the input bundle, and this AST walk rejects a model that reached for
it anyway.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path

from ..ports import classify, pinned_inputs
from ..schema import Issue

# Names a reference model has no business importing. `os`/`sys`/`pathlib` are
# how a model would reach the run directory; `random`/`time` break determinism.
_FORBIDDEN_IMPORTS = {"os", "sys", "pathlib", "random", "time", "subprocess", "io"}
_RTL_HINTS = ("rtl.sv", "rtl_", "/rtl", "dut.sv", "tb.sv")


def _static_checks(
    source: str, requirements: list[dict], coverage: dict[str, list[str]] | None = None
) -> list[Issue]:
    issues: list[Issue] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Issue("error", "ref_model.py", f"does not parse: {exc}")]

    # -- check 4: no import reaches outside, no RTL path literal appears
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORTS:
                    issues.append(
                        Issue("error", "ref_model.py",
                              f"imports {alias.name!r}; the model must be pure")
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _FORBIDDEN_IMPORTS:
                issues.append(
                    Issue("error", "ref_model.py",
                          f"imports from {node.module!r}; the model must be pure")
                )
            elif root and root not in {"specflow", "__future__"}:
                issues.append(
                    Issue("error", "ref_model.py",
                          f"imports from {node.module!r}; only specflow.refmodel.base "
                          f"is permitted")
                )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            if any(h in low for h in _RTL_HINTS):
                issues.append(
                    Issue("error", "ref_model.py",
                          f"contains the path-like literal {node.value!r}; the "
                          f"reference model must not read the design")
                )

    # -- check 2: every requirement is claimed by the coverage map, and every
    # method the map names exists.
    #
    # This replaces "every requirement has a `_req_NNNN` method". That check
    # bought traceability by forcing the model's *shape*, and the shape was the
    # problem: a model organised by the specification's sentence order has
    # nowhere to put execution order, reset priority, or state that several
    # requirements share. Measured on the artifact it produced -- one method held
    # 85% of the code, 23 of 24 were <=4 lines, three were literally `pass`.
    #
    # The map carries the link instead, so the model can be shaped by the design.
    # The script checks the map is complete and its names resolve; the judge
    # checks the named code actually does the thing.
    defined = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for req in requirements:
        uid = req.get("uid") or ""
        if not uid:
            continue
        methods = coverage.get(uid) if coverage else None
        if not methods:
            issues.append(
                Issue("error", f"ref_model.py.{uid}",
                      f"{uid} appears in no coverage map entry; the generator "
                      f"must say which methods implement each requirement",
                      "uncovered")
            )
            continue
        for name in methods:
            if name not in defined:
                issues.append(
                    Issue("error", f"ref_model.py.{uid}",
                          f"the coverage map names {name!r} for {uid}, and no "
                          f"such method exists in the model")
                )

    # Deliberately NOT checked here: whether the named methods actually satisfy
    # the requirement, and whether one method is claimed for everything. Those
    # are judgements about meaning, and the per-requirement judge makes them --
    # a script that tried would either be a naming convention (which is what
    # this replaced) or a guess.
    return issues


def _random_inputs(contract: dict, rng: random.Random) -> dict:
    """A complete input bundle: functional ports randomised, runtime-owned ports pinned.

    Clock and reset are not randomised -- a randomly-asserted reset makes every
    later output legitimately reset-valued and the determination check
    meaningless -- but they *are* present. Dropping them was the bug: the model
    is written against the contract, so a model that reads a declared reset used
    to raise `KeyError` on G4's first call and abort the node before any real
    defect could be reported.
    """
    values: dict[str, int] = dict(pinned_inputs(contract))
    _, _, functional = classify(contract)
    widths = {
        str(p.get("name")): p.get("width")
        for p in (contract.get("io") or [])
    }
    for name in functional:
        width = widths.get(name)
        width = int(width) if isinstance(width, int) and width > 0 else 1
        values[name] = rng.getrandbits(min(width, 32))
    return values


def _min_latency_checks(model_cls, contract: dict, expected_base: str) -> list[Issue]:
    """G4e: a model may not answer FASTER than its own contract says it can.

    Every other G4 check asks whether the model is well-formed. None asks
    whether it behaves like the design, and the per-requirement judge cannot
    either: it reads the code against one requirement at a time, and a
    requirement like "the FSM advances only when clk_en is asserted" is
    satisfiable by code that then advances through *every* FSM phase on a single
    clk_en. Each requirement passes in isolation; the composition is wrong.

    That is not hypothetical. On i2c_master_bit_ctrl the generated model
    collapsed the whole five-phase START sequence into ONE clk_en tick. The
    golden RTL takes five -- one phase per tick -- so at clk_cnt=4 golden
    asserts cmd_ack at clock edge 26 and the model asserted it at edge 5. The
    judge returned "met" on all 72 requirements over that model, and driven
    through the resulting suite the GOLDEN design failed 120 of 168 testpoints:
    a correct design scoring worse than the LLM-written candidate, because the
    oracle was the thing that was wrong.

    The check needs no golden RTL, which is the point -- production has none.
    It uses the contract, an independently derived reading of the same
    specification, and asks one question of it: `timing.<port>.latency_cycles`
    says an output answers a stimulus N cycles later, so from reset that output
    must not move before step N. A model that beats its own declared latency has
    collapsed pipeline stages, and collapsing stages is exactly the error above.
    At clk_cnt=0 the i2c model asserted cmd_ack at step 1 against a declared 3.

    Deliberately one-sided. LATER than declared is not flagged: a prescaler,
    a stall or a stretched bus clock all legitimately delay an output, and the
    contract's own note for this design says so ("wall-clock latency may be
    longer ... because clk_en is prescaled"). Only EARLIER is impossible, so
    only earlier blocks -- the same can-block-cannot-accept asymmetry the judge
    has.
    """
    timing = contract.get("timing") or {}
    watched = {
        str(name): int((spec or {}).get("latency_cycles") or 0)
        for name, spec in timing.items()
        if isinstance(spec, dict) and int((spec or {}).get("latency_cycles") or 0) >= 2
    }
    if not watched or expected_base != "step":
        # latency_cycles of 0 or 1 says nothing a step-count can contradict, and
        # a combinational model has no steps to count.
        return []

    # Two models from the same reset, differing ONLY in the trigger. Comparing
    # against an idle twin rather than against a remembered first output is what
    # makes this sound: an output that free-runs (a divider tick, a counter) is
    # identical in both and never flagged, while a response to the stimulus
    # shows up as a divergence at the exact step it appears. Remembering step
    # 1's value instead made a step-1 response INTO the baseline, so the first
    # version of this check silently found nothing on the very model that
    # motivated it.
    _, _, functional = classify(contract)
    triggers = [n for n in ("cmd", "cmd_i", "req", "start", "valid", "go", "load")
                if n in functional]
    if not triggers:
        # Nothing identifiable makes this a stimulus rather than idling, so
        # there is no response time to measure.
        return []

    # The contract's claim is that the output CANNOT answer before N cycles --
    # a claim about every input, not one convenient vector. So try more than
    # one rest state and take the earliest response any of them produces.
    #
    # Necessary, not belt-and-braces: holding the non-trigger inputs at 0 puts
    # this design's open-drain SDA and SCL LOW, which is a stuck bus, and the
    # model correctly does nothing at all. Judged on that vector alone the check
    # passed a model that answers at step 1. Zero is simply not "idle" for an
    # active-low or open-drain input, and nothing in the contract says which is
    # which.
    rest_values = (0, 1)
    first_move: dict[str, int] = {}
    horizon = max(watched.values())

    for rest in rest_values:
        quiet = dict(pinned_inputs(contract))
        for name in functional:
            quiet[name] = rest
        for name in ("ena", "en", "enable"):
            if name in quiet:
                quiet[name] = 1     # the design must be running in both twins
        for name in ("clk_cnt", "prescale", "divider"):
            if name in quiet:
                quiet[name] = 0     # fastest legal timebase: an eager model shows soonest
        # The trigger is LOW in the quiet twin whatever the rest state is. Left
        # at `rest`, the rest=1 candidate made the two twins identical and the
        # whole candidate was skipped -- which is how the sweep still missed a
        # model that answers at step 1.
        for name in triggers:
            quiet[name] = 0
        active = dict(quiet)
        for name in triggers:
            active[name] = 1

        try:
            m_active, m_quiet = model_cls(), model_cls()
            for m in (m_active, m_quiet):
                if hasattr(m, "reset"):
                    m.reset()
            for step in range(1, horizon + 1):
                a = m_active.step(dict(active))
                q = m_quiet.step(dict(quiet))
                if not isinstance(a, dict) or not isinstance(q, dict):
                    return []
                for port in watched:
                    if a.get(port) != q.get(port):
                        prev = first_move.get(port)
                        if prev is None or step < prev:
                            first_move[port] = step
        except Exception:  # noqa: BLE001
            return []  # a model that raises is the determination check's business

    issues: list[Issue] = []
    for port, declared in sorted(watched.items()):
        moved = first_move.get(port)
        if moved is not None and moved < declared:
            issues.append(
                Issue(
                    "error",
                    f"ref_model.py.{port}",
                    f"answers faster than the contract allows: {port} first "
                    f"changes at step {moved}, but timing.{port}.latency_cycles "
                    f"is {declared}, so it cannot respond before step {declared}. "
                    f"A model that beats its declared latency has collapsed "
                    f"stages that the design takes separately -- typically by "
                    f"advancing several FSM phases on one enable tick instead "
                    f"of one phase per tick. Either the model is too eager or "
                    f"the contract's latency is wrong; they disagree and one of "
                    f"them must change.",
                )
            )
    return issues


def _behavioural_checks(
    source: str, contract: dict, expected_base: str, workdir: Path
) -> list[Issue]:
    """Checks 1 and 3: it loads, it is deterministic, it determines every output."""
    issues: list[Issue] = []

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "ref_model.py"
    path.write_text(source, encoding="utf-8")

    namespace: dict = {}
    try:
        exec(compile(source, str(path), "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        return [Issue("error", "ref_model.py", f"does not import: {exc!r}")]

    model_cls = namespace.get("Model")
    if model_cls is None:
        return [Issue("error", "ref_model.py", "defines no class named Model")]

    try:
        model = model_cls()
    except Exception as exc:  # noqa: BLE001
        return [Issue("error", "ref_model.py", f"Model() does not instantiate: {exc!r}")]

    call = getattr(model, expected_base, None)
    if not callable(call):
        return [
            Issue("error", f"ref_model.py.{expected_base}",
                  f"the contract requires a `{expected_base}` dispatch and it is missing")
        ]

    declared = set(model_cls.OUTPUT_PORTS or [])
    issues.extend(_min_latency_checks(model_cls, contract, expected_base))
    rng = random.Random(1337)  # noqa: S311 -- fixed seed: G4 must be reproducible
    vectors = [_random_inputs(contract, rng) for _ in range(8)]

    def run_sequence() -> tuple[list[dict] | None, Issue | None]:
        """Drive a *fresh* model through the whole vector sequence."""
        m = model_cls()
        fn = getattr(m, expected_base)
        out: list[dict] = []
        for inputs in vectors:
            try:
                result = fn(dict(inputs))
            except Exception as exc:  # noqa: BLE001
                return None, Issue(
                    "error", f"ref_model.py.{expected_base}",
                    f"raised on inputs {inputs!r}: {exc!r}")
            if not isinstance(result, dict):
                return None, Issue(
                    "error", f"ref_model.py.{expected_base}",
                    f"returned {type(result).__name__}, expected a dict of outputs")
            out.append(result)
        return out, None

    first_run, err = run_sequence()
    if err is not None:
        return [*issues, err]

    # -- check 3a: output determination. A port the model leaves unwritten is a
    # port the model does not determine -- Bormann's criterion in miniature.
    for inputs, result in zip(vectors, first_run or []):
        missing = declared - {k for k, v in result.items() if v is not None}
        if missing:
            issues.append(
                Issue("error", f"ref_model.py.{expected_base}",
                      f"leaves {sorted(missing)} unwritten on inputs {inputs!r}; "
                      f"every declared output must be determined")
            )
            break

    # -- check 3b: determinism, stated as a property of the *sequence*.
    #
    # This compared call N of one long-lived instance against call 0 of a fresh
    # one. For a combinational model those agree, so the half-adder fixture never
    # noticed -- and for a sequential model they are *supposed* to differ, since
    # accumulated state is the entire point of `step`. Every correct sequential
    # model was therefore reported non-deterministic. Measured on
    # `i2c_master_bit_ctrl`: three consecutive generation rounds rejected for it,
    # each one re-asking a strong model to fix something that was not wrong.
    #
    # Determinism actually means: the same inputs from the same starting state
    # give the same outputs. So drive two fresh instances through the identical
    # sequence and compare the sequences.
    second_run, err = run_sequence()
    if err is not None:
        return [*issues, err]
    if second_run != first_run:
        for k, (a, b) in enumerate(zip(first_run or [], second_run or [])):
            if a != b:
                issues.append(
                    Issue("error", f"ref_model.py.{expected_base}",
                          f"is not deterministic: two fresh models driven through "
                          f"the same {len(vectors)}-step sequence diverged at step "
                          f"{k} on inputs {vectors[k]!r}: {a!r} then {b!r}")
                )
                break

    # -- check 3c: a COMBINATIONAL model must carry no state at all.
    #
    # The sequence check above cannot see this: a model that counts its own calls
    # is perfectly reproducible sequence-to-sequence. For `evaluate` that is
    # still a defect -- a combinational output depends on its inputs and nothing
    # else -- so repeat one vector on one instance and require the same answer.
    # For `step` the identical behaviour is correct and is not checked.
    if expected_base == "evaluate" and vectors:
        m = model_cls()
        fn = getattr(m, expected_base)
        try:
            a, b = fn(dict(vectors[0])), fn(dict(vectors[0]))
        except Exception:  # noqa: BLE001
            a = b = None
        if a != b:
            issues.append(
                Issue("error", "ref_model.py.evaluate",
                      f"carries state: the same inputs {vectors[0]!r} gave {a!r} "
                      f"then {b!r} on one instance, and a combinational model "
                      f"depends on its inputs and nothing else")
            )

    if not declared:
        issues.append(
            Issue("error", "ref_model.py",
                  "OUTPUT_PORTS is empty; output determination cannot be checked")
        )

    return issues


def validate(
    *,
    out,
    source: str,
    requirements: list[dict],
    contract: dict,
    expected_base: str,
    workdir: Path,
) -> list[Issue]:
    """G4. Order matters: a parse failure makes every later check meaningless."""
    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", "refmodel.response", out.reasoning)]

    if not out.source.strip():
        return [Issue("error", "refmodel.source", "no model source produced")]

    issues = _static_checks(source, requirements, out.covers)

    # check 8 (cheap, and it catches a real disagreement): the agent's own view
    # of the dispatch must match the one the contract dictates.
    if out.base and out.base != expected_base:
        issues.append(
            Issue("error", "refmodel.base",
                  f"answered {out.base!r} but the contract requires {expected_base!r}")
        )

    if any(i.severity == "error" for i in issues):
        # Executing a model that failed a static check risks running code that
        # was rejected for reaching outside the sandbox.
        return issues

    return issues + _behavioural_checks(source, contract, expected_base, workdir)


def validate_source(
    *,
    source: str,
    requirements: list[dict],
    contract: dict,
    expected_base: str,
    workdir: Path,
    coverage: dict[str, list[str]] | None = None,
) -> list[Issue]:
    """G4 over a `ref_model.py` already on disk, with no generation round.

    The same checks as `validate` minus the two that are statements about the
    agent's response rather than the artifact -- a parse failure and the
    agent's declared base. What remains is everything that can go stale:
    requirement coverage, the sandbox check, output determination, determinism.

    This is what makes reusing a certified model safe. The recorded verdict is
    never trusted; the model is re-executed, so a requirement set that changed
    underneath it, or a gate that has since been tightened, regenerates it.
    """
    issues = _static_checks(source, requirements, coverage)
    if any(i.severity == "error" for i in issues):
        return issues
    return issues + _behavioural_checks(source, contract, expected_base, workdir)
