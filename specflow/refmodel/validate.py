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

from ..ids import method_name
from ..ports import classify, pinned_inputs
from ..schema import Issue

# Names a reference model has no business importing. `os`/`sys`/`pathlib` are
# how a model would reach the run directory; `random`/`time` break determinism.
_FORBIDDEN_IMPORTS = {"os", "sys", "pathlib", "random", "time", "subprocess", "io"}
_RTL_HINTS = ("rtl.sv", "rtl_", "/rtl", "dut.sv", "tb.sv")


def _static_checks(source: str, requirements: list[dict]) -> list[Issue]:
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

    # -- check 2: every requirement has its method
    defined = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    by_name = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for req in requirements:
        uid = req.get("uid") or ""
        if not uid:
            continue
        want = method_name(uid)
        if want not in defined:
            issues.append(
                Issue("error", f"ref_model.py.{want}",
                      f"no method for {uid}; every requirement is one element of code",
                      "uncovered")
            )
            continue
        # -- a fragment that writes no output port
        #
        # This is half of what keeps atomicity honest. G1' punishes
        # under-splitting; nothing punished over-splitting, so a requirement too
        # small to constrain anything could pass every gate by producing a method
        # that computes and discards. Measured on `or1200_ctrl`, 15 of 31
        # fragments wrote nothing at all -- a majority of the reference model was
        # inert and no gate said so.
        #
        # It is an error rather than a warning because the pair of opposing
        # pressures only works if both sides bite. A warning here would leave
        # "split until each requirement is a word" as a viable strategy.
        if not _writes_an_output(by_name[want]):
            issues.append(
                Issue("error", f"ref_model.py.{want}",
                      f"{uid}'s fragment writes no output port; a requirement "
                      f"whose method determines nothing is not a requirement")
            )

    return issues


def _writes_an_output(fn: ast.AST) -> bool:
    """True when the method assigns into the output dict at least once.

    Matches `o[...] = ...` and `out[...] = ...` under any binding name the
    renderer uses, plus augmented and annotated assignment, since a fragment
    that only does `o["q"] |= x` still determines `q`.
    """
    for node in ast.walk(fn):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                return True
            if isinstance(t, (ast.Tuple, ast.List)):
                if any(isinstance(e, ast.Subscript) for e in t.elts):
                    return True
    return False


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

    for trial in range(8):
        inputs = _random_inputs(contract, rng)
        try:
            first = call(dict(inputs))
        except Exception as exc:  # noqa: BLE001
            issues.append(
                Issue("error", f"ref_model.py.{expected_base}",
                      f"raised on inputs {inputs!r}: {exc!r}")
            )
            break

        if not isinstance(first, dict):
            issues.append(
                Issue("error", f"ref_model.py.{expected_base}",
                      f"returned {type(first).__name__}, expected a dict of outputs")
            )
            break

        # check 3a: output determination. A port the model leaves unwritten is a
        # port the model does not determine -- Bormann's criterion in miniature,
        # and free to check here.
        missing = declared - {k for k, v in first.items() if v is not None}
        if missing:
            issues.append(
                Issue("error", f"ref_model.py.{expected_base}",
                      f"leaves {sorted(missing)} unwritten on inputs {inputs!r}; "
                      f"every declared output must be determined")
            )
            break

        # check 3b: determinism. Re-instantiate rather than reuse, so hidden
        # state shows up rather than being carried silently between calls.
        second = getattr(model_cls(), expected_base)(dict(inputs))
        if second != first:
            issues.append(
                Issue("error", f"ref_model.py.{expected_base}",
                      f"is not deterministic: inputs {inputs!r} gave {first!r} "
                      f"then {second!r}")
            )
            break

        if trial == 0 and not declared:
            issues.append(
                Issue("warning", "ref_model.py",
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

    if not out.fragments:
        return [Issue("error", "refmodel.fragments", "no fragments produced")]

    issues = _static_checks(source, requirements)

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
    issues = _static_checks(source, requirements)
    if any(i.severity == "error" for i in issues):
        return issues
    return issues + _behavioural_checks(source, contract, expected_base, workdir)
