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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .config import OpenAIConfig

logger = logging.getLogger(__name__)

# Canonical implementations live in utils so every player/reviewer shares them.
from .utils import (  # noqa: E402
    failing_test_primitives as _failing_test_primitives,
    failing_test_scenarios,
    format_failing_scenarios,
)


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
    # ``lessons`` is the **contract-safe** summary that crosses the epoch boundary
    # (symptom + diagnosis + disputed primitives) — it must NOT embed either
    # player's source/diffs/justifications (no-shared-access). The full diagnostic
    # (diffs, suspect code, justifications) is written to ``lessons_full.txt`` for
    # audit and for the future real Architect, never fed back to the players.
    lessons: str
    rtl_player_changed: bool
    tb_player_changed: bool
    # Named scenarios still in dispute after the committed-pair sim (per-primitive
    # granularity for freeze-settled / shrinking-dispute at Step 4).
    disputed_primitives: tuple[str, ...] = ()


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
        disputed = tuple(_failing_test_primitives(sim_log))
        safe_lessons, full_lessons = self._make_lessons(
            rtl_changed=rtl_changed,
            tb_changed=tb_changed,
            outcome="consensus" if sim_pass else "no_consensus",
            sim_log=sim_log,
            disputed_primitives=disputed,
            rtl_player_dir=rtl_player_dir,
            frozen_rtl=frozen_rtl,
            committed_rtl=committed_rtl,
            frozen_tb=frozen_tb,
            committed_tb=committed_tb,
            rtl_player_justification=rtl_justification,
            tb_player_justification=tb_justification,
        )
        # Full diagnostic (diffs/justifications/suspect-code) is audit-only — it must
        # NOT cross the epoch boundary to the players (no-shared-access).
        try:
            (output_dir / "lessons_full.txt").write_text(full_lessons, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

        logger.info(
            "ConsensusGame: module=%s reached=%s rtl_changed=%s tb_changed=%s disputed=%s",
            module_name, sim_pass, rtl_changed, tb_changed, list(disputed),
        )

        return ConsensusVerdict(
            reached=sim_pass,
            committed_rtl=committed_rtl,
            committed_tb=committed_tb,
            blame=None if sim_pass else "contract_ambiguous",
            lessons=safe_lessons,
            rtl_player_changed=rtl_changed,
            tb_player_changed=tb_changed,
            disputed_primitives=disputed,
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
    def _read_check_log(check_dir: Path, *, max_chars: int = 8000) -> str:
        """Return the *runtime* portion of the consensus-check sim log.

        Verilator ``--binary`` echoes the entire C++ build (``c++ -Os ...``,
        ``verilator_includer``, ``- Verilator: ...``) to stdout **before** the
        simulation runs, so the runtime markers we care about
        (``[TEST ...]``/``SIMULATION``/``Mismatches:``/``Hint:``) sit thousands of
        chars in. Clipping the *head* would capture only build noise (the bug that
        made ``disputed_primitives`` always empty). Strip build lines and keep the
        *tail*, where the runtime output lives.
        """
        p = check_dir / "sim_output.json"
        if not p.exists():
            return ""
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return ""

        # The runtime markers can sit anywhere in a long, noisy log (build spam
        # before, %Warning blocks after), so positional clipping (head OR tail)
        # is unreliable. Filter to the signal lines directly — position-independent.
        _SIGNAL = (
            "[TEST", "SIMULATION", "Mismatches:", "Hint:", "Cycle ", "Last ",
            "%Error", "syntax error", "mismatch",
        )
        combined = str(obj.get("stdout") or "") + "\n" + str(obj.get("stderr") or "")
        signal_lines = [
            ln for ln in combined.splitlines()
            if any(tok in ln for tok in _SIGNAL)
        ]
        if signal_lines:
            return "\n".join(signal_lines)[-max_chars:]
        # No recognizable runtime signal (e.g. compile failed) — return a clipped
        # tail of the raw log so the caller still sees the error.
        return combined.strip()[-max_chars:]

    @staticmethod
    def _make_lessons(
        *,
        rtl_changed: bool,
        tb_changed: bool,
        outcome: str,
        sim_log: str,
        disputed_primitives: tuple[str, ...] = (),
        # Optional richer context — all default to empty/None for backward compat.
        rtl_player_dir: "Path | None" = None,
        frozen_rtl: str = "",
        committed_rtl: str = "",
        frozen_tb: str = "",
        committed_tb: str = "",
        rtl_player_justification: str = "",
        tb_player_justification: str = "",
    ) -> tuple[str, str]:
        """Return ``(safe_lessons, full_lessons)``.

        ``safe`` is the contract-safe summary that crosses the epoch boundary to
        the players: outcome, diagnosis, disputed primitives, and symptom-level
        failing signals — **no** RTL/TB diffs, suspect-block source, or player
        justifications (those embed a player's private work and would violate
        no-shared-access if fed to the counterpart). ``full`` = safe + that rich
        detail, for audit / the future real Architect only.
        """
        # ---- contract-safe section (forwarded) ----
        safe = [f"Consensus game result: {outcome}"]
        safe.append(
            "  RTL player: "
            + ("revised RTL" if rtl_changed else "kept RTL unchanged (RTL considered correct)")
        )
        safe.append(
            "  TB player:  "
            + ("revised TB" if tb_changed else "kept TB unchanged (TB considered correct)")
        )

        if outcome == "no_consensus":
            if not rtl_changed and not tb_changed:
                safe.append(
                    "Diagnosis: Neither player modified their design. "
                    "Both believe the other is at fault. "
                    "The contract is likely ambiguous — clarify the expected behaviour."
                )
            elif rtl_changed and tb_changed:
                safe.append(
                    "Diagnosis: Both players revised toward different readings. "
                    "The contract has ambiguous behaviour — be more explicit about "
                    "the contested interface/timing."
                )
            elif rtl_changed and not tb_changed:
                safe.append(
                    "Diagnosis: RTL player revised RTL but committed designs still "
                    "disagree. TB reviewer confirmed TB is correct; clarify the contract "
                    "clause governing the disputed behaviour."
                )
            else:
                safe.append(
                    "Diagnosis: TB player revised TB but committed RTL does not pass it. "
                    "The original TB may encode the contract incorrectly — clarify the "
                    "timing / interface specification."
                )

            scenarios = failing_test_scenarios(sim_log)
            if scenarios:
                safe.append(f"Disputed test primitives ({len(scenarios)}), with timing:")
                safe.append(format_failing_scenarios(scenarios))
            elif disputed_primitives:
                safe.append(
                    f"Disputed test primitives ({len(disputed_primitives)}): "
                    + ", ".join(disputed_primitives)
                )

            # Symptom-level failing signals from the committed-pair sim (not source).
            hint_lines = [
                ln for ln in sim_log.splitlines()
                if "Hint:" in ln or "SIMULATION FAILED" in ln or "Mismatches:" in ln
            ]
            last_cycles = [
                ln for ln in sim_log.splitlines()
                if ln.startswith("Cycle ") or ln.startswith("Last ")
            ]
            if hint_lines:
                safe.append("Failing signals (consensus-check simulation):")
                safe.extend(f"  {ln.strip()}" for ln in hint_lines[:8])
            if last_cycles:
                safe.append("Last simulation cycles (consensus check):")
                safe.extend(f"  {ln.strip()}" for ln in last_cycles[-6:])

        # ---- full-only detail (audit; never forwarded to players) ----
        extra: list[str] = []
        if outcome == "no_consensus":
            if rtl_player_dir is not None:
                trace = _read_json_safe(Path(rtl_player_dir) / "trace_report.json") or {}
                blocks = trace.get("suspect_blocks") or []
                if blocks:
                    extra.append(
                        f"RTL suspect blocks ({len(blocks)} identified by RTL-player trace):"
                    )
                    for b in blocks[:5]:
                        writes = ", ".join(b.get("writes") or [])[:80]
                        extra.append(
                            f"  {b.get('id','?')} ({b.get('kind','?')}/{b.get('clocking','?')}) "
                            f"L{b.get('start_line','?')}-{b.get('end_line','?')} "
                            f"writes=[{writes}]"
                        )
                    snippet = (blocks[0].get("code_snippet") or "").strip()
                    if snippet:
                        extra.append(
                            f"  Primary suspect block ({blocks[0].get('id')}) code:\n"
                            + "\n".join("    " + ln for ln in snippet.splitlines()[:20])
                        )
            if rtl_changed and frozen_rtl and committed_rtl:
                diff = _compact_diff(frozen_rtl, committed_rtl, "rtl.sv", max_lines=35)
                if diff:
                    extra.append("RTL changes made by RTL player:")
                    extra.append(diff.rstrip())
            if tb_changed and frozen_tb and committed_tb:
                diff = _compact_diff(frozen_tb, committed_tb, "tb.sv", max_lines=25)
                if diff:
                    extra.append("TB changes made by TB player:")
                    extra.append(diff.rstrip())

        def _extract_justification(raw: str) -> str:
            if not raw:
                return ""
            for kw in ("RTL_FIXED:", "RTL_CORRECT:", "TB_FIXED:", "TB_CORRECT:"):
                idx = raw.find(kw)
                if idx != -1:
                    return raw[idx:].strip()
            paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
            return paras[-1] if paras else raw.strip()

        rtl_just = _extract_justification(rtl_player_justification)
        tb_just = _extract_justification(tb_player_justification)
        if rtl_just or tb_just:
            extra.append("Player conclusions (contract-grounded; audit-only):")
            if rtl_just:
                extra.append("  [RTL player]")
                extra.extend("    " + ln for ln in rtl_just.splitlines())
            if tb_just:
                extra.append("  [TB player]")
                extra.extend("    " + ln for ln in tb_just.splitlines())

        safe_text = "\n".join(safe)
        full_text = safe_text + ("\n\n" + "\n".join(extra) if extra else "")
        return safe_text, full_text
