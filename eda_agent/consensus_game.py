"""Two-player simultaneous consensus game for a single contract node.

Lives in the Veri-Sure fork because it orchestrates Veri-Sure's own agents
(RTLEditor, TBReviewer) and is a fundamental capability of the Veri-Sure
pipeline — not a DAG-orchestration concern.

Protocol
--------
1. Start from a frozen compilable baseline: ``(initial_tb, initial_rtl)``.
2. Both players refine their own design for ``max_local_iterations`` steps,
   each holding the *other*'s design constant at the frozen initial version —
   no co-adaptation, no shared access between players.
3. Commit simultaneously (both submit their best design, possibly unchanged).
4. Consensus check: ``sim(committed_rtl, committed_tb)``?
   - Pass  → **consensus** — both designs are mutually consistent
             (convergence signal: the wrong side fixed itself against the
             correct frozen baseline; the correct side declined to change).
   - Fail  → **contract_ambiguous** — both repaired to their own reading of
             the contract yet still disagree (they read it differently).

Assumptions (from the plan)
----------------------------
- **Single-fault**: at most one of {TB, DUT} is wrong at a time.
- **No shared access**: players work in separate directories; neither sees
  the other's evolving work during local iterations.
- **Consensus is a convergence signal, not a correctness oracle.** Reaching
  consensus means the agents handled the complexity (converged on a
  self-consistent pair). False consensus (both wrong but self-consistent) is
  caught at root by the golden TB — the sole correctness authority.

Component mapping
-----------------
- RTL-player ≈ reframed RTLEditor: fixes RTL to pass the FROZEN initial TB.
  If RTL already passes, the player declines (RTL is fine — TB side may be
  at fault).
- TB-player  ≈ TBReviewer (tool-driven ReActAgent): reviews the TB with full
  tool access (read, replace lines, run simulation, inspect trace) against
  the FROZEN initial RTL. May conclude "TB is correct, RTL is wrong" without
  changing anything.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .config import OpenAIConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers (no I/O side-effects)
# ---------------------------------------------------------------------------

def _read_json_safe(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _compact_diff(a: str, b: str, filename: str, *, max_lines: int = 30) -> str:
    """Unified diff of two strings, truncated to ``max_lines`` diff lines."""
    lines = list(difflib.unified_diff(
        a.splitlines(keepends=True),
        b.splitlines(keepends=True),
        fromfile=f"before/{filename}",
        tofile=f"after/{filename}",
        n=2,
    ))
    if not lines:
        return ""
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines truncated)\n"]
    return "".join(lines)


@dataclass(frozen=True)
class ConsensusVerdict:
    """Outcome of one consensus-game round.

    ``reached=True`` means the two independently-revised designs are mutually
    consistent (sim passes). ``blame`` is None in that case.
    ``lessons`` is always populated; it feeds back into the next epoch when
    consensus was not reached.
    """

    reached: bool
    committed_rtl: str
    committed_tb: str
    blame: Literal["contract_ambiguous"] | None
    lessons: str
    rtl_player_changed: bool
    tb_player_changed: bool


class ConsensusGame:
    """Two-player simultaneous consensus game.  See module docstring."""

    def __init__(self, cfg: "OpenAIConfig") -> None:
        self.cfg = cfg

    async def run(
        self,
        *,
        frozen_rtl: str,
        frozen_tb: str,
        contract_json: str,
        module_name: str,
        output_dir: Path,
        max_local_iterations: int = 3,
    ) -> ConsensusVerdict:
        """Run one round of the two-player game and return a verdict."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "frozen_rtl.sv").write_text(frozen_rtl, encoding="utf-8")
        (output_dir / "frozen_tb.sv").write_text(frozen_tb, encoding="utf-8")

        if not frozen_rtl.strip() or not frozen_tb.strip():
            lessons = (
                "Consensus game aborted: one or both players had no compilable "
                "initial design. The contract may be too complex to draft in a "
                "single pass."
            )
            return ConsensusVerdict(
                reached=False,
                committed_rtl=frozen_rtl,
                committed_tb=frozen_tb,
                blame="contract_ambiguous",
                lessons=lessons,
                rtl_player_changed=False,
                tb_player_changed=False,
            )

        rtl_player_dir = output_dir / "rtl_player"
        tb_player_dir = output_dir / "tb_player"

        # Both players run in parallel — no shared state.
        (committed_rtl, rtl_justification), (committed_tb, tb_justification) = (
            await asyncio.gather(
                self._run_rtl_player(
                    frozen_rtl=frozen_rtl,
                    frozen_tb=frozen_tb,
                    contract_json=contract_json,
                    output_dir=rtl_player_dir,
                    max_local_iterations=max_local_iterations,
                ),
                self._run_tb_player(
                    frozen_tb=frozen_tb,
                    frozen_rtl=frozen_rtl,
                    contract_json=contract_json,
                    module_name=module_name,
                    output_dir=tb_player_dir,
                    max_local_iterations=max_local_iterations,
                ),
            )
        )

        (output_dir / "committed_rtl.sv").write_text(committed_rtl, encoding="utf-8")
        (output_dir / "committed_tb.sv").write_text(committed_tb, encoding="utf-8")

        check_dir = output_dir / "consensus_check"
        sim_pass = await self._consensus_sim_check(
            rtl=committed_rtl, tb=committed_tb, check_dir=check_dir
        )

        rtl_changed = committed_rtl.strip() != frozen_rtl.strip()
        tb_changed = committed_tb.strip() != frozen_tb.strip()
        sim_log = self._read_check_log(check_dir)
        lessons = self._make_lessons(
            rtl_changed=rtl_changed,
            tb_changed=tb_changed,
            outcome="consensus" if sim_pass else "no_consensus",
            sim_log=sim_log,
            rtl_player_dir=rtl_player_dir,
            frozen_rtl=frozen_rtl,
            committed_rtl=committed_rtl,
            frozen_tb=frozen_tb,
            committed_tb=committed_tb,
            rtl_player_justification=rtl_justification,
            tb_player_justification=tb_justification,
        )

        logger.info(
            "ConsensusGame: module=%s reached=%s rtl_changed=%s tb_changed=%s",
            module_name, sim_pass, rtl_changed, tb_changed,
        )

        return ConsensusVerdict(
            reached=sim_pass,
            committed_rtl=committed_rtl,
            committed_tb=committed_tb,
            blame=None if sim_pass else "contract_ambiguous",
            lessons=lessons,
            rtl_player_changed=rtl_changed,
            tb_player_changed=tb_changed,
        )

    # ------------------------------------------------------------------
    # RTL player — RTLEditor on (frozen_tb, initial_rtl)
    # ------------------------------------------------------------------

    async def _run_rtl_player(
        self,
        *,
        frozen_rtl: str,
        frozen_tb: str,
        contract_json: str,
        output_dir: Path,
        max_local_iterations: int,
    ) -> str:
        output_dir.mkdir(parents=True, exist_ok=True)
        tb_path = output_dir / "tb.sv"
        rtl_path = output_dir / "rtl.sv"
        tb_path.write_text(frozen_tb, encoding="utf-8")
        rtl_path.write_text(frozen_rtl, encoding="utf-8")

        from .sim_reviewer import SimReviewer, sim_review  # noqa: PLC0415
        from .rtl_editor import RTLEditor  # noqa: PLC0415

        try:
            is_pass, mismatch_cnt, sim_log = await asyncio.to_thread(
                sim_review, str(output_dir), None
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RTL player: initial sim failed: %s", exc)
            return frozen_rtl

        if is_pass:
            logger.debug("RTL player: RTL passes frozen TB — keeping unchanged")
            return frozen_rtl, ""

        if mismatch_cnt <= 0:
            logger.debug("RTL player: non-mismatch failure — keeping RTL unchanged")
            return frozen_rtl, ""

        justification = ""
        try:
            sim_reviewer = SimReviewer(str(output_dir), None)
            rtl_edit = RTLEditor(
                self.cfg, sim_reviewer=sim_reviewer, max_trials=max_local_iterations
            )
            _, _, _, justification = await rtl_edit.chat(
                spec=contract_json,
                output_dir_per_run=str(output_dir),
                sim_failed_log=sim_log,
                sim_mismatch_cnt=mismatch_cnt,
                contract_json=contract_json,
                max_trials=max_local_iterations,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RTL player: RTLEditor raised %s", exc)

        try:
            return rtl_path.read_text(encoding="utf-8"), justification
        except Exception:  # noqa: BLE001
            return frozen_rtl, justification

    # ------------------------------------------------------------------
    # TB player — TBReviewer on (frozen_rtl, initial_tb)
    # ------------------------------------------------------------------

    async def _run_tb_player(
        self,
        *,
        frozen_tb: str,
        frozen_rtl: str,
        contract_json: str,
        module_name: str,
        output_dir: Path,
        max_local_iterations: int,
    ) -> str:
        output_dir.mkdir(parents=True, exist_ok=True)
        tb_path = output_dir / "tb.sv"
        rtl_path = output_dir / "rtl.sv"
        tb_path.write_text(frozen_tb, encoding="utf-8")
        rtl_path.write_text(frozen_rtl, encoding="utf-8")

        from .sim_reviewer import SimReviewer, sim_review  # noqa: PLC0415
        from .tb_reviewer import TBReviewer  # noqa: PLC0415

        # Run initial simulation so TBReviewer has a failure to inspect
        try:
            is_pass, mismatch_cnt, sim_log = await asyncio.to_thread(
                sim_review, str(output_dir), None
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("TB player: initial sim failed: %s", exc)
            return frozen_tb

        if is_pass:
            # Frozen RTL already passes the frozen TB — no review needed.
            logger.debug("TB player: frozen RTL passes frozen TB — keeping TB unchanged")
            return frozen_tb, ""

        if mismatch_cnt <= 0:
            # Non-mismatch failure (compile error, timeout) — TBReviewer cannot engage.
            logger.debug("TB player: non-mismatch failure — keeping TB unchanged")
            return frozen_tb, ""

        justification = ""
        try:
            sim_reviewer_obj = SimReviewer(str(output_dir), None)
            tb_review = TBReviewer(
                self.cfg,
                sim_reviewer=sim_reviewer_obj,
                max_trials=max_local_iterations,
            )
            _is_pass, _tb_code, _used, justification = await tb_review.chat(
                contract_json=contract_json,
                output_dir_per_run=str(output_dir),
                sim_failed_log=sim_log,
                sim_mismatch_cnt=mismatch_cnt,
                max_trials=max_local_iterations,
            )
            # tb_review.chat() writes the committed TB to tb.sv; read it back.
            return tb_path.read_text(encoding="utf-8"), justification
        except Exception as exc:  # noqa: BLE001
            logger.warning("TB player: TBReviewer raised %s", exc)
            return frozen_tb, justification

    # ------------------------------------------------------------------
    # Consensus arbiter
    # ------------------------------------------------------------------

    async def _consensus_sim_check(
        self, *, rtl: str, tb: str, check_dir: Path
    ) -> bool:
        check_dir.mkdir(parents=True, exist_ok=True)
        (check_dir / "rtl.sv").write_text(rtl, encoding="utf-8")
        (check_dir / "tb.sv").write_text(tb, encoding="utf-8")

        from .sim_reviewer import sim_review  # noqa: PLC0415

        try:
            is_pass, _, sim_log = await asyncio.to_thread(
                sim_review, str(check_dir), None
            )
            try:
                (check_dir / "sim_output.json").write_text(sim_log, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            return bool(is_pass)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Consensus sim check raised: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_check_log(check_dir: Path) -> str:
        p = check_dir / "sim_output.json"
        if not p.exists():
            return ""
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            blob = (
                str(obj.get("stdout") or "") + "\n" + str(obj.get("stderr") or "")
            ).strip()
            return blob[:2000]
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _make_lessons(
        *,
        rtl_changed: bool,
        tb_changed: bool,
        outcome: str,
        sim_log: str,
        # Optional richer context — all default to empty/None for backward compat.
        rtl_player_dir: "Path | None" = None,
        frozen_rtl: str = "",
        committed_rtl: str = "",
        frozen_tb: str = "",
        committed_tb: str = "",
        rtl_player_justification: str = "",
        tb_player_justification: str = "",
    ) -> str:
        lines = [f"Consensus game result: {outcome}"]
        lines.append(
            "  RTL player: "
            + ("revised RTL" if rtl_changed else "kept RTL unchanged (RTL considered correct)")
        )
        lines.append(
            "  TB player:  "
            + ("revised TB" if tb_changed else "kept TB unchanged (TB considered correct)")
        )

        if outcome == "no_consensus":
            if not rtl_changed and not tb_changed:
                lines.append(
                    "Diagnosis: Neither player modified their design. "
                    "Both believe the other is at fault. "
                    "The contract is likely ambiguous — clarify the expected behaviour."
                )
            elif rtl_changed and tb_changed:
                lines.append(
                    "Diagnosis: Both players revised toward different readings. "
                    "The contract has ambiguous behaviour — be more explicit about "
                    "the contested interface/timing."
                )
            elif rtl_changed and not tb_changed:
                lines.append(
                    "Diagnosis: RTL player revised RTL but committed designs still "
                    "disagree. TB reviewer confirmed TB is correct; focus the next "
                    "attempt on the RTL logic identified below."
                )
            else:
                lines.append(
                    "Diagnosis: TB player revised TB but committed RTL does not pass it. "
                    "The original TB may encode the contract incorrectly — review the "
                    "timing / interface specification."
                )

            # --- Structured signal-level failure from the consensus sim check ---
            hint_lines = [
                ln for ln in sim_log.splitlines()
                if "Hint:" in ln or "SIMULATION FAILED" in ln or "Mismatches:" in ln
            ]
            last_cycles = [
                ln for ln in sim_log.splitlines()
                if ln.startswith("Cycle ") or ln.startswith("Last ")
            ]
            if hint_lines:
                lines.append("Failing signals (consensus-check simulation):")
                lines.extend(f"  {ln.strip()}" for ln in hint_lines[:8])
            if last_cycles:
                lines.append("Last simulation cycles (consensus check):")
                lines.extend(f"  {ln.strip()}" for ln in last_cycles[-6:])

            # --- RTL suspect blocks from the RTL player's trace report ---
            if rtl_player_dir is not None:
                trace = _read_json_safe(Path(rtl_player_dir) / "trace_report.json") or {}
                blocks = trace.get("suspect_blocks") or []
                if blocks:
                    lines.append(
                        f"RTL suspect blocks ({len(blocks)} identified by RTL-player trace):"
                    )
                    for b in blocks[:5]:
                        writes = ", ".join(b.get("writes") or [])[:80]
                        lines.append(
                            f"  {b.get('id','?')} ({b.get('kind','?')}/{b.get('clocking','?')}) "
                            f"L{b.get('start_line','?')}-{b.get('end_line','?')} "
                            f"writes=[{writes}]"
                        )
                    # Include the code snippet for the first (most-implicated) block only.
                    snippet = (blocks[0].get("code_snippet") or "").strip()
                    if snippet:
                        lines.append(
                            f"  Primary suspect block ({blocks[0].get('id')}) code:\n"
                            + "\n".join("    " + ln for ln in snippet.splitlines()[:20])
                        )

            # --- Compact diff of RTL changes ---
            if rtl_changed and frozen_rtl and committed_rtl:
                diff = _compact_diff(frozen_rtl, committed_rtl, "rtl.sv", max_lines=35)
                if diff:
                    lines.append("RTL changes made by RTL player:")
                    lines.append(diff.rstrip())

            if tb_changed and frozen_tb and committed_tb:
                diff = _compact_diff(frozen_tb, committed_tb, "tb.sv", max_lines=25)
                if diff:
                    lines.append("TB changes made by TB player:")
                    lines.append(diff.rstrip())

        # --- Player conclusions (contract-grounded justifications) ---
        # These are the most important input for the next epoch's architect:
        # each player states which contract clause it was working from and why
        # it believes its own design is correct.
        def _extract_justification(raw: str, label: str) -> str:
            """Strip any agent preamble; return the structured response content."""
            if not raw:
                return ""
            # The generate_response content is typically buried after tool-call XML.
            # Look for the verdict keyword and take everything from there.
            for kw in ("RTL_FIXED:", "RTL_CORRECT:", "TB_FIXED:", "TB_CORRECT:"):
                idx = raw.find(kw)
                if idx != -1:
                    return raw[idx:].strip()
            # Fallback: last non-empty paragraph
            paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
            return paras[-1] if paras else raw.strip()

        rtl_just = _extract_justification(rtl_player_justification, "RTL player")
        tb_just = _extract_justification(tb_player_justification, "TB player")

        if rtl_just or tb_just:
            lines.append("Player conclusions (contract-grounded):")
            if rtl_just:
                lines.append("  [RTL player]")
                lines.extend("    " + ln for ln in rtl_just.splitlines())
            if tb_just:
                lines.append("  [TB player]")
                lines.extend("    " + ln for ln in tb_just.splitlines())

        return "\n".join(lines)
