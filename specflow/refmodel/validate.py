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


def _hashable(value):
    """Outputs are ints, but a model may return a list or dict. The gate must
    not be the thing that crashes on a malformed model -- that is what the
    checks above are for."""
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


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

    # -- check 3d: the outputs must actually MOVE.
    #
    # Every check above is satisfied by a model that returns the same constant
    # forever: it imports, it instantiates, it is reproducible, and it writes
    # every declared port. It is also useless -- a constant oracle agrees with
    # whichever DUT is quietest and discriminates nothing.
    #
    # Not hypothetical. The i2c reference model was regenerated five times under
    # per-requirement judging, and round 4 emitted ONE distinct output state over
    # 60 edges of varied stimulus where round 0 emitted five. Scored against
    # golden RTL it went 34/181 to 18/181, and its separation from a known-WRONG
    # design inverted to -9: the vacuous model matched the wrong design better
    # than the right one. Nothing in the pipeline said so.
    #
    # This is the model-side counterpart of a rule the harness already applies to
    # the DUT side -- every conformance fixture must also REJECT a tied-off DUT,
    # which is the only check that caught `clock_named_clock` agreeing for the
    # wrong reason.
    #
    # A warning rather than an error, deliberately. A design can be legitimately
    # quiet under this vector set -- the null-oracle sweep across all 64
    # ChipVerilog designs found exactly one, `instruction_mem`, whose outputs
    # never move under the liveness probe either. One false positive in 64 is not
    # worth blocking a correct generation over, and a warning still puts the
    # finding in front of the next round.
    # It needs its own stimulus. The eight vectors above randomise every
    # functional input across its full width, and for a prescaled design that
    # means `clk_cnt` is a random 16-bit number, the divider never ticks, and
    # NOTHING moves in eight steps -- so the check would fire on a perfectly
    # good model. Measured: the i2c round-0 model, which is wrong but active
    # and discriminating (+23 separation), is constant across those eight and
    # emits five distinct states under a corner-first sweep.
    #
    # `default_stimulus` is the corner-first sweep the testbench renderer
    # already uses, and for the same reason -- "a uniform random sweep never
    # decodes a decoder".
    from ..tb.render import default_stimulus  # noqa: PLC0415 -- avoid a cycle

    pinned = dict(pinned_inputs(contract))
    walk = [{**pinned, **v} for v in default_stimulus(contract)]
    mover = model_cls()
    fn = getattr(mover, expected_base)
    states: set = set()
    for step_inputs in walk:
        try:
            result = fn(dict(step_inputs))
        except Exception:  # noqa: BLE001, S110 -- already reported above
            states = set()
            break
        if isinstance(result, dict):
            states.add(tuple(sorted((k, _hashable(v)) for k, v in result.items())))
    if declared and walk and len(states) == 1:
        issues.append(
            Issue("warning", f"ref_model.py.{expected_base}",
                  f"returns the same output state on all {len(walk)} vectors of a "
                  f"corner-first sweep; a reference model whose outputs never "
                  f"move cannot discriminate a correct design from a wrong one")
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
