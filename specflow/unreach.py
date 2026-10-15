"""Discharge uncovered coverage bins by proof, not by assertion.

Without this the hard gate can be mathematically unsatisfiable: a bin describing
a mode a parameter disables will never be hit, and a loop that requires every bin
covered would spin forever on it.

The distinction that makes this honest is *how* a bin leaves the denominator.
GoGoTB removes structurally unreachable bins with no stated criterion. Here a bin
leaves only with a recorded proof and the assumption set it was proved under --
which is the difference between an exclusion and an excuse. An exclusion proved
under a wrong constraint environment is indistinguishable from a real one, so the
assumptions are stored and re-checked when the contract changes.

`eda_agent/boolean_proofer.py:511-530` writes a hardcoded `.sby` -- fixed `mode
prove`, `depth 1`, `smtbmc z3`, a fixed three-file list and `prep -top Miter`.
This generalises that into a parameterised writer, and widens the status
vocabulary, which there collapses an sby `UNKNOWN` into `"error"`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # noqa: S404 -- invoking known local tools
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

#: Follows `benchmarks/chipverilog/tools/formal_equivalence.py` rather than
#: boolean_proofer's four-valued set. The distinction that matters is
#: unknown-vs-refuted: a timeout proves nothing, and treating it as a refutation
#: would silently keep a bin that might be genuinely unreachable, while treating
#: it as a proof would silently drop one that is reachable.
ProofStatus = Literal["unreachable", "reachable", "unknown", "timeout", "error", "skip"]


@dataclass(frozen=True)
class Discharge:
    bin_uid: str
    status: ProofStatus
    proof_type: str = ""
    depth: int | None = None
    assumptions: tuple[str, ...] = ()
    log_path: str = ""
    reason: str = ""

    @property
    def disposes(self) -> bool:
        """Only a real proof removes a bin from the accept criterion."""
        return self.status == "unreachable"


_STATUS_RE = re.compile(r"^\s*(\w+)")


def read_sby_status(status_file: Path) -> str:
    """First token of sby's status file, upper-cased. Absent means no verdict."""
    try:
        text = Path(status_file).read_text(encoding="utf-8")
    except OSError:
        return ""
    m = _STATUS_RE.match(text)
    return m.group(1).upper() if m else ""


def classify(status: str, *, timed_out: bool) -> ProofStatus:
    """Map an sby verdict onto the discharge vocabulary.

    `PASS` on the *negated* condition means the condition can never hold, i.e.
    the bin is unreachable. `FAIL` means sby produced a witness -- the bin is
    reachable and its counterexample is a stimulus that would cover it.
    """
    if timed_out:
        return "timeout"
    if status == "PASS":
        return "unreachable"
    if status == "FAIL":
        return "reachable"
    if status in {"UNKNOWN", ""}:
        return "unknown"
    return "error"


def write_sby(
    path: Path,
    *,
    sources: list[Path],
    top: str,
    mode: str = "prove",
    depth: int = 20,
    engine: str = "smtbmc z3",
) -> Path:
    """Parameterised .sby writer, replacing the fixed template."""
    path = Path(path)
    files = "\n".join(str(Path(s).name) for s in sources)
    reads = " ".join(str(Path(s).name) for s in sources)
    path.write_text(
        f"[options]\nmode {mode}\ndepth {depth}\n\n"
        f"[engines]\n{engine}\n\n"
        f"[script]\nread -formal -sv {reads}\nprep -top {top}\n\n"
        f"[files]\n{files}\n",
        encoding="utf-8",
    )
    return path


def render_cover_probe(
    *, dut_module: str, contract: dict, condition_sv: str, probe_top: str = "CoverProbe"
) -> str:
    """A wrapper asserting the bin condition never holds.

    If sby proves that assertion, no input sequence reaches the bin. If it
    refutes it, the counterexample is a stimulus that does.
    """
    ports = contract.get("io") or []
    decls, conns = [], []
    for p in ports:
        name = str(p["name"])
        width = int(p.get("width") or 1)
        rng = "" if width <= 1 else f"[{width - 1}:0] "
        decls.append(f"  {'input' if p.get('dir') == 'input' else 'output'} wire {rng}{name}")
        conns.append(f".{name}({name})")

    clocking = contract.get("clocking") or {}
    clk = ((clocking.get("clock") or {}).get("name")) or "clk"
    has_clk = any(str(p["name"]) == clk for p in ports)
    guard = f"always @(posedge {clk}) " if has_clk else "always @* "

    # THE DESIGN MUST START FROM RESET, or this proves nothing about it.
    #
    # `mode prove` is k-induction, which checks a base case and an inductive
    # step. The inductive step is what makes a PASS unbounded, and it is fine
    # without help. The BASE CASE is not: with nothing constraining the initial
    # state, the solver may start the design in any bit pattern its registers
    # can hold -- including the very state we are asking whether it can reach.
    #
    # Measured on a two-bit FSM whose state 3 is never assigned anywhere:
    # "Temporal induction successful" -- the design genuinely cannot ENTER the
    # state -- while the base case failed at step 0 because the solver started
    # there. The verdict came back `reachable`. Left unfixed, this instrument
    # could never prove ANY state of ANY design with registers unreachable, and
    # the one authority the plan gives for `UNREACHABLE` would be vacuous while
    # looking like it ran.
    #
    # So reset is assumed in the initial state and the property is asserted only
    # from the first clock edge after it, which is exactly "reachable from
    # reset". With no reset declared there is nothing to assume and the old
    # behaviour stands -- a design with no reset has no defined start state, so
    # "reachable from reset" is not a question it can be asked.
    reset = clocking.get("reset") or {}
    rname = str(reset.get("name") or "")
    has_reset = has_clk and any(str(p["name"]) == rname for p in ports)
    preamble, gate = "", ""
    if has_reset:
        active = "" if str(reset.get("active", "high")).lower() == "high" else "!"
        preamble = (
            f"  // Start from reset: without this the base case may begin in\n"
            f"  // the state under test, and no state is ever provably absent.\n"
            f"  initial assume ({active}{rname});\n"
            f"  reg _past_reset = 1'b0;\n"
            f"  always @(posedge {clk}) _past_reset <= 1'b1;\n\n")
        gate = "if (_past_reset) "

    # AND AN IDENTIFIER THE WRAPPER DOES NOT DECLARE MUST NOT BECOME A FREE
    # VARIABLE, which is a second and independent way this instrument can be
    # vacuous.
    #
    # The condition may legitimately name an internal signal -- that is most of
    # what a state is. But the wrapper declares only the contract's PORTS, so a
    # bare internal name is an implicit net: undriven, unconstrained, and free
    # for the solver to set. Measured on golden or1200_dc_fsm: the condition
    # `cache_inhibit && biu_read && biudata_valid` came back `reachable` with a
    # counterexample in which `cache_inhibit` is a floating wire the solver
    # simply chose. EVERY condition naming an internal signal would be
    # "reachable" for that reason alone, and the verdict looked exactly like a
    # real one.
    #
    # `default_nettype none` makes an undeclared identifier a COMPILE ERROR, so
    # the condition either names something real or the discharge fails loudly as
    # `error`. Reaching an internal signal is still available and is now
    # explicit: write it hierarchically, `dut.cache_inhibit`.
    return (
        "`default_nettype none\n"
        f"module {probe_top} (\n" + ",\n".join(decls) + "\n);\n\n"
        f"  {dut_module} dut (\n    " + ",\n    ".join(conns) + "\n  );\n\n"
        f"{preamble}"
        f"  {guard}{gate}assert (!({condition_sv}));\n\n"
        "endmodule\n"
        "`default_nettype wire\n"
    )


def discharge_bin(
    *,
    bin_uid: str,
    condition_sv: str,
    rtl_path: Path,
    dut_module: str,
    contract: dict,
    workdir: Path,
    depth: int = 20,
    timeout_s: int = 120,
) -> Discharge:
    """Attempt one proof. Any tool problem is `error`, never a silent pass."""
    if not condition_sv.strip():
        return Discharge(bin_uid, "skip", reason="no SystemVerilog condition supplied")
    for tool in ("sby", "yosys"):
        if not shutil.which(tool):
            return Discharge(bin_uid, "error", reason=f"{tool} not on PATH")

    workdir = Path(workdir) / bin_uid.replace("-", "_")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    shutil.copy(rtl_path, workdir / Path(rtl_path).name)
    probe = workdir / "cover_probe.sv"
    probe.write_text(
        render_cover_probe(
            dut_module=dut_module, contract=contract, condition_sv=condition_sv
        ),
        encoding="utf-8",
    )
    sby = write_sby(
        workdir / "probe.sby",
        sources=[workdir / Path(rtl_path).name, probe],
        top="CoverProbe",
        depth=depth,
    )

    timed_out = False
    try:
        subprocess.run(  # noqa: S603
            ["sby", "-f", sby.name], cwd=workdir, capture_output=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        timed_out = True

    # AN IMPLICITLY DECLARED IDENTIFIER MAKES THE VERDICT MEANINGLESS.
    #
    # The wrapper declares the contract's ports. A condition naming anything
    # else -- an internal signal, or a typo -- becomes an implicit net: no
    # driver, no constraint, and free for the solver to set to whatever
    # refutes the assertion. `default_nettype none` does not stop this; yosys
    # reports it as a WARNING and carries on.
    #
    # Measured on golden or1200_dc_fsm: `cache_inhibit && biu_read &&
    # biudata_valid` returned `reachable` with a counterexample in which
    # `cache_inhibit` is a floating wire. Every condition naming an internal
    # signal would be "reachable" for that reason alone, and nothing in the
    # result said so. Reaching an internal signal is still available and is now
    # explicit: write it hierarchically, `dut.cache_inhibit`.
    log = workdir / "probe" / "model" / "design.log"
    if log.exists():
        implicit = [
            ln.strip() for ln in log.read_text(errors="replace").splitlines()
            if "is implicitly declared" in ln
        ]
        if implicit:
            return Discharge(
                bin_uid=bin_uid, status="error", depth=depth,
                assumptions=(f"contract:{dut_module}", f"depth:{depth}"),
                log_path=str(log),
                reason=("condition names an identifier the wrapper does not "
                        "declare, so it is an undriven free wire and any "
                        "verdict is vacuous; use a hierarchical reference "
                        f"such as dut.<name>. {implicit[0]}"),
            )

    status = read_sby_status(workdir / "probe" / "status")
    resolved = classify(status, timed_out=timed_out)

    return Discharge(
        bin_uid=bin_uid,
        status=resolved,
        # `mode prove` is k-induction: unbounded when it passes, which is why a
        # PASS here is a real exclusion rather than "not found within depth".
        proof_type="k_induction" if resolved == "unreachable" else "",
        depth=depth,
        assumptions=(f"contract:{dut_module}", f"depth:{depth}"),
        log_path=str(workdir / "probe" / "status"),
        reason=f"sby status {status or 'absent'}",
    )


def discharge_all(
    *,
    uncovered: list[str],
    conditions: dict[str, str],
    rtl_path: Path,
    dut_module: str,
    contract: dict,
    workdir: Path,
    out_path: Path | None = None,
) -> dict[str, dict]:
    """Discharge every uncovered bin; return only the ones that were proved.

    Deliberately returns proofs alone: a `reachable` or `unknown` verdict must
    leave the bin blocking. Treating `unknown` as a disposition would shrink the
    denominator on the strength of a solver timeout.
    """
    results = [
        discharge_bin(
            bin_uid=uid, condition_sv=conditions.get(uid, ""), rtl_path=rtl_path,
            dut_module=dut_module, contract=contract, workdir=workdir,
        )
        for uid in uncovered
    ]

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(
            json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8"
        )

    return {r.bin_uid: asdict(r) for r in results if r.disposes}
