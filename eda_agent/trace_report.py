from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .bash_tools import CommandResult
from .trace_slicer import RtlBlock, build_driver_map, dynamic_slice, parse_rtl_blocks

try:  # optional dependency
    from vcdvcd import VCDVCD  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    VCDVCD = None  # type: ignore[assignment]


_HINT_RE = re.compile(
    r"Hint:\s+Output\s+'(?P<sig>[^']+)'\s+has\s+(?P<cnt>\d+)\s+mismatches\.\s+First mismatch occurred at time\s+(?P<t>\d+)\.",
)
_FAILED_RE = re.compile(r"SIMULATION FAILED - (?P<cnt>\d+)\s+MISMATCHES DETECTED.*FIRST AT TIME\s+(?P<t>\d+)", re.IGNORECASE)
_MISMATCHES_RE = re.compile(r"^Mismatches:\s*(?P<cnt>\d+)\s*in\s*(?P<samples>\d+)\s*samples$", re.MULTILINE)

# The VALUES, which `Hint:` lines never carry. Testbenches print them right next
# to the signal name and the extractor used to drop them, so `fail_outputs`
# reached the debugger as `{"sig": "result_out", "expected": null, "actual": null}`
# -- a list of names with no data.
#
# That is why the debugger invented a timing theory on stage_roundpack: with no
# expected-vs-actual it cannot see "right value, one cycle late", only "wrong at
# t=30000", and a sampling guess is a reasonable inference from a name alone. It
# then rewrote `always_ff` to `always_comb` to fit the guess and broke the
# contract's 1-cycle latency (B21).
#
# Two emitted shapes are covered, both observed in this project:
#   Mismatch at time 30000: result_out
#     Expected: 3f800000, Actual: 00000000
#   MISMATCH [SMALL_EXP_DIFF] at time 60000: sig_b_out=0100000 exp=0800000
# `Expected:` does not always follow the header directly -- testbenches commonly
# print an `Inputs: ...` line between them, and requiring adjacency silently lost
# result_out (the signal that mattered) while recovering valid_out. Allow a few
# intervening lines, but never cross into the NEXT mismatch header, or one
# signal's values get attributed to another.
_PAIRED_RE = re.compile(
    r"[Mm]ismatch(?:\s*\[[^\]]*\])?\s+at\s+time\s+(?P<t>\d+)\s*:\s*(?P<sig>\w+)\s*\n"
    r"(?P<between>(?:(?![Mm]ismatch\b).*\n){0,4}?)"
    r"\s*Expected:\s*(?P<exp>\S+?),?\s+Actual:\s*(?P<act>\S+)",
)
_INLINE_RE = re.compile(
    r"[Mm]ismatch(?:\s*\[[^\]]*\])?\s+at\s+time\s+(?P<t>\d+)\s*:\s*"
    r"(?P<sig>\w+)\s*=\s*(?P<act>\S+)\s+exp(?:ected)?\s*=\s*(?P<exp>\S+)",
)


def _extract_values(stdout: str) -> dict[str, dict[str, str]]:
    """First observed expected/actual pair per signal.

    FIRST, not last: the earliest divergence is the one that explains the
    others, and a later sample is usually downstream corruption.
    """
    out: dict[str, dict[str, str]] = {}
    for rx in (_PAIRED_RE, _INLINE_RE):
        for m in rx.finditer(stdout):
            sig = m.group("sig")
            if sig in out:
                continue
            out[sig] = {
                "expected": m.group("exp").rstrip(","),
                "actual": m.group("act").rstrip(","),
                "at_time": m.group("t"),
            }
    return out


# `Cycle N: ... | got_res=<v> exp_res=<v> got_val=<v> exp_val=<v>` — the
# per-cycle history testbenches dump on first mismatch.
# A shift claim needs enough samples to be a measurement rather than an accident,
# and enough VARIETY that a shifted window is not just re-comparing constants.
_ALIGN_MIN_SAMPLES = 6
_ALIGN_MIN_DISTINCT = 2

_CYCLE_DUMP_RE = re.compile(r"^Cycle\s+(?P<n>\d+)\s*:(?P<body>.*)$", re.MULTILINE)
_GOT_EXP_RE = re.compile(r"\bgot_(?P<name>\w+)\s*=\s*(?P<got>\S+)")


def _alignment_from_cycle_dump(stdout: str) -> dict[str, Any]:
    """Alignment diagnosis WITHOUT a VCD, from the testbench's cycle dump.

    The VCD-based path below is the better one, but it needs a waveform and
    `trace_vcd_path` is frequently null — in which case `alignment_diagnosis`
    came back EMPTY while the debugger prompt's step 2 says, first thing:

        2) Check `trace_summary.alignment_diagnosis` first

    So the debugger's opening diagnostic move landed on a missing field, found
    nothing, and fell back to guessing. On stage_roundpack (job 7829273) it
    guessed a sampling theory and rewrote `always_ff` to `always_comb`, breaking
    the contract's 1-cycle latency (B21) — when the true answer, "the DUT leads
    expected by one cycle", is computable from data the testbench had already
    printed.

    Same match-rate comparison as the VCD path so the two agree: current vs
    dut_lag1 vs dut_lead1, best wins.
    """
    rows: list[dict[str, tuple[str, str]]] = []
    for m in _CYCLE_DUMP_RE.finditer(stdout):
        body = m.group("body")
        pairs: dict[str, tuple[str, str]] = {}
        for g in _GOT_EXP_RE.finditer(body):
            name = g.group("name")
            exp_m = re.search(rf"\bexp_{re.escape(name)}\s*=\s*(\S+)", body)
            if exp_m:
                pairs[name] = (exp_m.group(1), g.group("got"))
        if pairs:
            rows.append(pairs)
    if len(rows) < _ALIGN_MIN_SAMPLES:
        # Too few samples to distinguish a real shift from an accident of the
        # window. Reporting one would be worse than reporting nothing.
        return {}

    out: dict[str, Any] = {}
    names = set().union(*(set(r) for r in rows))
    for name in sorted(names):
        seq = [r.get(name) for r in rows]
        exp_seq = [s[0] if s else None for s in seq]
        act_seq = [s[1] if s else None for s in seq]

        def rate(pairs) -> float | None:
            tot = ok = 0
            for e, a in pairs:
                if e is None or a is None:
                    continue
                tot += 1
                ok += _wildcard_match(e, a)
            return (ok / tot) if tot else None

        # A window dominated by one repeated value (reset cycles are all zeros)
        # makes ANY shift score perfectly, because shifting simply drops the one
        # interesting sample out of the comparison. Measured live on
        # stage_roundpack parent_4: 3 rows, two of them all-zero reset cycles,
        # produced lag1=1.00 on both signals -- a phantom one-cycle shift, when
        # the real defect was a special-case PRIORITY disagreement
        # (result_out expected 00000000, actual 7fc00000 = quiet NaN, on an
        # input with nan/inf/zero/denorm all asserted at once). Handing that to
        # the debugger would send it chasing a timing bug that does not exist --
        # exactly the mistake B21's debugger made unaided.
        distinct_exp = {e for e in exp_seq if e is not None}
        if len(distinct_exp) < _ALIGN_MIN_DISTINCT:
            continue

        cur = rate(list(zip(exp_seq, act_seq)))
        lag = rate(list(zip(exp_seq[1:], act_seq[:-1])))
        lead = rate(list(zip(exp_seq[:-1], act_seq[1:])))
        choices = {"current": cur, "dut_lag1": lag, "dut_lead1": lead}
        best = max(choices.items(), key=lambda kv: (-1.0 if kv[1] is None else kv[1]))
        out[name] = {
            "samples_considered": len(rows),
            "source": "cycle_dump",
            "match_rate_current": cur,
            "match_rate_dut_lag1": lag,
            "match_rate_dut_lead1": lead,
            "best_alignment": best[0] if best[1] is not None else None,
        }
    return out


def _extract_fail_signals_and_time(stdout: str) -> tuple[int | None, list[dict[str, Any]]]:
    fail_outputs: list[dict[str, Any]] = []
    times: list[int] = []
    for m in _HINT_RE.finditer(stdout):
        cnt = int(m.group("cnt"))
        sig = m.group("sig")
        t = int(m.group("t"))
        if cnt > 0:
            fail_outputs.append({"sig": sig, "mismatches": cnt, "time": t})
            times.append(t)

    if times:
        return min(times), fail_outputs

    m2 = _FAILED_RE.search(stdout)
    if m2:
        t = int(m2.group("t"))
        return t, [{"sig": None, "mismatches": int(m2.group("cnt")), "time": t}]

    return None, []


def _extract_total_mismatches(stdout: str) -> int | None:
    m = _MISMATCHES_RE.search(stdout)
    if m:
        return int(m.group("cnt"))
    return None


def _extract_topmodule_ports(rtl_text: str) -> dict[str, list[str]]:
    # Very small parser: extract ports from the first "module ... ( ... );"
    m = re.search(r"\bmodule\b\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(", rtl_text)
    if not m:
        return {"inputs": [], "outputs": []}

    start = m.end()
    end = rtl_text.find(");", start)
    if end == -1:
        return {"inputs": [], "outputs": []}

    portlist = rtl_text[start:end]
    ports: list[tuple[str, str]] = []
    for seg in portlist.split(","):
        seg = seg.strip().strip("()").strip()
        if not seg:
            continue
        mdir = re.search(r"\b(input|output|inout)\b", seg)
        if not mdir:
            continue
        direction = mdir.group(1)
        names = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", seg)
        names = [
            n
            for n in names
            if n
            not in {
                "input",
                "output",
                "inout",
                "wire",
                "logic",
                "reg",
                "bit",
                "signed",
                "unsigned",
                "integer",
                "int",
            }
        ]
        if names:
            ports.append((direction, names[-1]))

    inputs = sorted({name for d, name in ports if d == "input"})
    outputs = sorted({name for d, name in ports if d == "output"})
    return {"inputs": inputs, "outputs": outputs}
_ATTR_PREFIX = r"(?:\(\*.*?\*\)\s*)*"


def _extract_module_name_from_rtl(rtl_text: str) -> str | None:
    m = re.search(rf"^\s*{_ATTR_PREFIX}module\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", rtl_text, re.MULTILINE)
    if not m:
        return None
    return m.group(1)


def _extract_module_name_from_contract(output_dir: Path) -> str | None:
    p = output_dir / "contract.json"
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("module_name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def _extract_child_facing_outputs(output_dir: Path, *, outputs: list[str]) -> list[str]:
    """Output ports that are child-facing exports (``<child>_<port>``).

    Composition-node contracts carry a ``child_assumes`` dict keyed by child
    module name. Child-facing exports on the glue module are pure outputs that
    the TB-checked fan-in never reaches, so they must seed the trace roots
    explicitly (see AGENTS.md: suspect-block blind spot).
    """
    p = output_dir / "contract.json"
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(obj, dict):
        return []
    child_assumes = obj.get("child_assumes")
    if not isinstance(child_assumes, dict) or not child_assumes:
        return []
    prefixes = tuple(f"{child}_" for child in child_assumes if isinstance(child, str) and child)
    if not prefixes:
        return []
    return [o for o in outputs if o.startswith(prefixes)]


def _extract_dut_instance_name(tb_text: str, *, module_name: str) -> str | None:
    # Best-effort: match `<module_name> <inst>(` in the testbench.
    m = re.search(rf"\b{re.escape(module_name)}\b\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", tb_text)
    if m:
        return m.group(1)

    # Fallback: in non-golden mode we usually instantiate as `<something> dut ( ... )`.
    if re.search(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b\s+dut\s*\(", tb_text):
        return "dut"
    return None


def _vcd_signal_names(vcd: Any) -> list[str]:
    """Every signal path in the dump, across vcdvcd API versions.

    This existed as a bare `getattr(vcd, "signals", [])`, and the installed
    vcdvcd exposes NO `signals` attribute -- only `get_signals()` and a private
    `_signals`. So the getattr returned `[]` on every call and
    `_vcd_find_signal` answered None for every signal in every session, which
    silently disabled ALL waveform analysis: fail_details values, the input
    window, and alignment_diagnosis alike.

    That is why 0 of 471 failing signals across 107 recorded reports carried a
    value, and why the debugger prompt's "check alignment_diagnosis first"
    always landed on an empty field -- for leaves exactly as much as for glue.
    A silent default hid a total failure behind a plausible-looking empty result.
    """
    got = getattr(vcd, "signals", None)
    if got:
        return list(got)
    getter = getattr(vcd, "get_signals", None)
    if callable(getter):
        try:
            return list(getter())
        except Exception:  # noqa: BLE001
            pass
    return list(getattr(vcd, "_signals", None) or [])


def _vcd_tv(vcd: Any, name: str) -> list[tuple[int, str]]:
    """Time/value series for a signal path, across vcdvcd API versions.

    The call sites used `vcd[name].tv`, and the installed vcdvcd is NOT
    subscriptable -- it exposes `get_data()` keyed by short id, each entry
    holding `references` (the full paths) and `tv`. That TypeError was never
    observed because `_vcd_find_signal` returned None first (see
    `_vcd_signal_names`), so execution never reached the subscript. Two
    independent API mismatches, the first masking the second, which is why the
    whole waveform path looked merely empty rather than broken.
    """
    try:
        return list(vcd[name].tv)  # newer vcdvcd
    except TypeError:
        pass
    except Exception:  # noqa: BLE001
        return []
    try:
        data = vcd.get_data()
    except Exception:  # noqa: BLE001
        return []
    for entry in (data or {}).values():
        if not hasattr(entry, "get"):
            continue
        if name in (entry.get("references") or []):
            return list(entry.get("tv") or [])
    return []


def _vcd_find_signal(vcd: Any, leaf: str, *, prefer_substrings: list[str] | None = None) -> str | None:
    leaf = leaf.strip()
    candidates: list[str] = []
    for s in _vcd_signal_names(vcd):
        last = s.split(".")[-1]
        if last == leaf or last.startswith(f"{leaf}["):
            candidates.append(s)
    if not candidates:
        return None
    # Prefer the closest-to-top match to reduce ambiguity (e.g., prefer tb.clk over tb.stim1.clk).
    def rank(sig: str) -> tuple[int, int, str]:
        return (sig.count("."), len(sig), sig)

    if prefer_substrings:
        preferred = [s for s in candidates if any(sub in s for sub in prefer_substrings)]
        if preferred:
            return sorted(preferred, key=rank)[0]
    return sorted(candidates, key=rank)[0]


def _vcd_value_at(tv: list[tuple[int, str]], t: int, *, inclusive: bool = True) -> str | None:
    last: str | None = None
    for tt, vv in tv:
        if tt < t or (inclusive and tt == t):
            last = vv
        else:
            break
    return last


def _normalize_vcd_value(val: str | None) -> str | None:
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    # vcdvcd may prefix vectors with 'b'
    if (val.startswith("b") or val.startswith("B")) and len(val) > 1:
        val = val[1:]
    return val.lower()


def _wildcard_match(expected: str | None, actual: str | None) -> bool:
    """Approximate VerilogEval tb_match semantics: X/Z in expected are wildcards."""
    exp = _normalize_vcd_value(expected)
    act = _normalize_vcd_value(actual)
    if exp is None or act is None:
        return False

    n = max(len(exp), len(act))
    exp = exp.rjust(n, "0")
    act = act.rjust(n, "0")

    for e, a in zip(exp, act):
        if e in {"x", "z"}:
            continue
        if a != e:
            return False
    return True


def _build_window_times(vcd: Any, *, t_star: int, k_edges: int = 10) -> list[int]:
    clk_sig = _vcd_find_signal(vcd, "clk")
    if clk_sig:
        tv = _vcd_tv(vcd, clk_sig)
        edges: list[int] = []
        prev = None
        for tt, vv in tv:
            if prev is not None and vv != prev:
                edges.append(tt)
            prev = vv
        edges = [t for t in edges if t <= t_star]
        if edges:
            keep = edges[-min(len(edges), k_edges) :]
            if t_star not in keep:
                keep.append(t_star)
            return keep

    # Fallback: pick latest change times in the window from all signals.
    times = {t_star}
    for s in getattr(vcd, "signals", [])[:200]:
        try:
            for tt, _vv in _vcd_tv(vcd, s):
                if tt <= t_star:
                    times.add(tt)
        except Exception:  # noqa: BLE001
            continue
    return sorted(times)[-min(len(times), k_edges + 2) :]


_GLUEPROBE_RE = re.compile(r"^GLUEPROBE\s+t=(\d+)\s+(.*)$", re.M)


def _glueprobe_values(stdout: str, fail_time: int | None) -> dict[str, str]:
    """Observed values of the glue's CHILD-FACING ports at the failing time.

    The testbench drives the WRAPPER, so it only ever prints expected-vs-actual
    for the wrapper's external outputs. Every port the glue drives into a child
    is an internal node, and on stage_roundpack that was 11 of the 13 failing
    signals -- reported to the debugger as `expected: null, actual: null`, a
    name with no evidence attached.

    There is no `expected` to report for these: the oracle models the
    composition's outputs, not its internal wiring. What the debugger gets is
    the value it is actually driving at the moment the composition fails, which
    is the difference between reasoning about a routing bug and guessing at one.
    """
    if fail_time is None:
        return {}
    best: dict[str, str] = {}
    best_t = None
    for m in _GLUEPROBE_RE.finditer(stdout):
        t = int(m.group(1))
        if t > fail_time:
            continue
        if best_t is None or t >= best_t:
            best_t = t
            best = dict(re.findall(r"(\w+)=([0-9a-fA-FxXzZ?]+)", m.group(2)))
    return best


def _fill_from_stdout(
    fail_outputs: list[dict[str, Any]], values: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """Restore the values the testbench PRINTED onto the list that ships.

    `fail_details` (VCD-derived) replaces `fail_outputs` wholesale, and it looks
    up `<sig>_ref` / `<sig>_dut` -- a self-checking scaffold convention that NO
    generated testbench actually uses. Measured: zero `_ref`/`_dut` wires in the
    glue TB and zero in the leaf TB, so that lookup returns None for every
    signal and `fail_details` is all-null by construction.

    The effect was that the weakest evidence silently displaced the strongest:
    stdout carried `result_out expected=00000000 actual=7fc00000` -- a full
    expected/actual PAIR -- and the recorded report still showed
    `expected: null, actual: null` for it, because 13 null VCD rows won the
    `or`. Merge instead of replace; a printed value is never overwritten.
    """
    for fo in fail_outputs:
        v = values.get(fo.get("sig") or "")
        if not v:
            continue
        # The testbench's own pair WINS over the waveform's actual, even though
        # the waveform is more precise. Both sides then share one radix.
        #
        # The VCD reports raw bits, the testbench reports whatever it formatted:
        # on stage_roundpack that yielded `expected=00000000` against
        # `actual=01111111110000000000000000000000`. Both name the same quiet
        # NaN (0x7FC00000) and no reader -- model or human -- can see that at a
        # glance. A debugger comparing those two strings concludes the output is
        # wrong in some spectacular way and starts rewriting arithmetic.
        #
        # The waveform keeps its monopoly where it is the only witness: internal
        # nodes the testbench never printed, which is most of what a glue drives.
        fo["expected"] = v["expected"] if v.get("expected") is not None else fo.get("expected")
        fo["actual"] = v["actual"] if v.get("actual") is not None else fo.get("actual")
    return fail_outputs


def _fill_from_probe(
    fail_outputs: list[dict[str, Any]], stdout: str, fail_time: int | None
) -> list[dict[str, Any]]:
    """Attach probe-observed values to signals the testbench could not print.

    Applied to the list that actually ships. The VCD-derived `fail_details`
    REPLACES `fail_outputs` wholesale, and it is precisely the branch carrying
    the child-facing ports -- so filling the other list would have looked
    correct on a log with no VCD and done nothing in the case this exists for.
    """
    probe = _glueprobe_values(stdout, fail_time)
    if not probe:
        return fail_outputs
    for fo in fail_outputs:
        sig = fo.get("sig") or ""
        if fo.get("actual") is None and sig in probe:
            fo["actual"] = probe[sig]
            fo["observed_via"] = "hierarchical_probe"
    return fail_outputs


def build_trace_report(
    *,
    rtl_path: Path,
    sim_log_json: str,
    output_dir: Path,
    max_depth: int = 3,
    window_cycles: int = 10,
    diag_edges: int = 200,
) -> tuple[dict[str, Any], list[RtlBlock]]:
    """Build a structured bug report (waveform + coarse RTL slice)."""
    sim = CommandResult.model_validate_json(sim_log_json)
    stdout = sim.stdout or ""

    rtl_text = rtl_path.read_text(encoding="utf-8")
    ports = _extract_topmodule_ports(rtl_text)
    module_name = _extract_module_name_from_contract(output_dir) or _extract_module_name_from_rtl(rtl_text) or "TopModule"

    fail_time, fail_outputs = _extract_fail_signals_and_time(stdout)
    total_mismatches = _extract_total_mismatches(stdout)

    # Attach the values the testbench printed. Without these the debugger gets
    # signal NAMES and nothing else, which is what produced B21.
    values = _extract_values(stdout)
    for fo in fail_outputs:
        v = values.get(fo.get("sig") or "")
        if v:
            fo["expected"] = v["expected"]
            fo["actual"] = v["actual"]
    # Signals the TB reported values for but that produced no Hint line still
    # carry evidence; losing them would repeat the same mistake one level down.
    known = {fo.get("sig") for fo in fail_outputs}
    for sig, v in values.items():
        if sig not in known:
            fail_outputs.append({
                "sig": sig, "mismatches": None, "time": int(v["at_time"]),
                "expected": v["expected"], "actual": v["actual"],
            })

    blocks = parse_rtl_blocks(rtl_text)
    if not blocks:
        # Last-resort fallback: allow the debugger to edit something even if
        # the RTL parser fails (e.g., malformed output). This keeps the tool
        # contract stable: debug can always get at least one block_id.
        lines = rtl_text.splitlines()
        if lines:
            code = rtl_text if rtl_text.endswith("\n") else rtl_text + "\n"
            blocks = [
                RtlBlock(
                    id="A1",
                    kind="always",
                    start_line=1,
                    end_line=len(lines),
                    clocking="unknown",
                    code=code,
                    writes=tuple(ports["outputs"]),
                    reads=tuple(ports["inputs"]),
                )
            ]

    drivers = build_driver_map(blocks)

    fail_signal_names: list[str] = [
        fo["sig"] for fo in fail_outputs if fo.get("sig")
    ]
    if not fail_signal_names:
        fail_signal_names = ports["outputs"]

    # Composition nodes: child-facing exports (<child>_<port>) are not in the
    # TB-checked fan-in, so seed the trace roots with them explicitly.
    for extra in _extract_child_facing_outputs(output_dir, outputs=ports["outputs"]):
        if extra not in fail_signal_names:
            fail_signal_names.append(extra)

    suspect_blocks = dynamic_slice(
        fail_signals=fail_signal_names,
        drivers=drivers,
        max_depth=max_depth,
    )
    if not suspect_blocks and blocks:
        suspect_blocks = blocks

    vcd_path = output_dir / "wave.vcd"
    vcd_available = vcd_path.exists() and VCDVCD is not None
    dut_instance: str | None = None
    tb_path = output_dir / "tb.sv"
    if tb_path.exists():
        try:
            dut_instance = _extract_dut_instance_name(tb_path.read_text(encoding="utf-8"), module_name=module_name)
        except Exception:  # noqa: BLE001
            dut_instance = None

    fail_time_star = fail_time
    fail_details: list[dict[str, Any]] = []
    input_window: list[dict[str, Any]] = []
    timing_hints: dict[str, Any] = {}
    alignment_diagnosis: dict[str, Any] = {}

    if vcd_available and fail_time_star is not None:
        vcd = VCDVCD(str(vcd_path), store_tvs=True)  # type: ignore[operator]
        times = _build_window_times(vcd, t_star=fail_time_star, k_edges=window_cycles)

        # Classify clock edges for the window (if clk is available).
        edge_at_time: dict[int, str] = {}
        edge_idx_at_time: dict[int, int] = {}
        edges_in_order: list[tuple[int, str]] = []
        clk_full = _vcd_find_signal(vcd, "clk")
        if clk_full:
            prev = None
            for tt, vv in _vcd_tv(vcd, clk_full):
                if prev is not None and vv != prev:
                    if prev != "1" and vv == "1":
                        edge_at_time[tt] = "posedge"
                    elif prev == "1" and vv != "1":
                        edge_at_time[tt] = "negedge"
                    else:
                        edge_at_time[tt] = "edge"
                    edge_idx_at_time[tt] = len(edges_in_order)
                    edges_in_order.append((tt, edge_at_time[tt]))
                prev = vv

        key_signals: list[str] = []
        # include top-level inputs
        key_signals.extend(ports["inputs"])
        # include ref/dut for failing outputs if present
        for sig in fail_signal_names:
            key_signals.append(f"{sig}_ref")
            key_signals.append(f"{sig}_dut")

        # Include likely internal signals (best-effort, only if present in VCD).
        internal_candidates: list[str] = []
        for b in suspect_blocks:
            internal_candidates.extend(list(b.writes))
            internal_candidates.extend(list(b.reads))
        internal_candidates = [
            s
            for s in sorted(set(internal_candidates))
            if s and s not in ports["inputs"] and s not in ports["outputs"]
        ]
        key_signals.extend(internal_candidates[:20])
        internal_candidate_set = set(internal_candidates[:20])

        key_signals = sorted({s for s in key_signals if s})

        def sample_signal(*, leaf: str, t: int, in_dut: bool = False) -> str | None:
            prefer_substrings = None
            if dut_instance and (in_dut or leaf in internal_candidate_set):
                prefer_substrings = [f".{dut_instance}."]
            full = _vcd_find_signal(vcd, leaf, prefer_substrings=prefer_substrings)
            if not full:
                return None
            inclusive = (leaf == "clk") or (t == 0)
            try:
                return _vcd_value_at(_vcd_tv(vcd, full), t, inclusive=inclusive)
            except Exception:  # noqa: BLE001
                return None

        # fail output expected/actual at t*
        #
        # `<sig>_ref` / `<sig>_dut` is a self-checking-harness convention that NO
        # generated testbench actually uses: measured across every recorded run,
        # zero such wires exist in 134 leaf TBs and zero in 26 glue TBs. The
        # generators emit a local reference model plus
        # `$display("Mismatch at time %0t: <sig>")` instead. So this lookup
        # returned None for every signal in every session, and `fail_details`
        # was all-null by construction -- 0 of 471 failing signals across 107
        # reports carried a value, for LEAVES as much as for glue.
        #
        # Fall back to the signal's own name, preferring the copy inside the DUT
        # hierarchy. That is what a waveform can actually answer: the VCD holds
        # what the design DID, at any depth, including internal nodes no
        # testbench prints. It cannot supply `expected` -- there is no reference
        # in the dump -- so that side stays with the stdout path.
        for sig in fail_signal_names:
            exp = sample_signal(leaf=f"{sig}_ref", t=fail_time_star)
            act = sample_signal(leaf=f"{sig}_dut", t=fail_time_star)
            if act is None:
                act = sample_signal(leaf=sig, t=fail_time_star, in_dut=True)
            fail_details.append({"sig": sig, "expected": exp, "actual": act})

        # input window values
        for window_idx, t in enumerate(times):
            edge = edge_at_time.get(t)
            row: Dict[str, Any] = {
                "t": t,
                "edge": edge,
                "event": f"@({edge} clk)" if edge in {"posedge", "negedge"} else None,
                "sample_idx": edge_idx_at_time.get(t),
                "window_idx": window_idx,
            }
            for s in key_signals:
                val = sample_signal(leaf=s, t=t)
                if val is not None:
                    row[s] = val
            input_window.append(row)

        # Simple timing hints: detect 1-edge latency between expected and actual.
        rows_by_t = {row["t"]: row for row in input_window if isinstance(row.get("t"), int)}
        if times and fail_time_star in rows_by_t:
            idx = times.index(fail_time_star) if fail_time_star in times else -1
            if idx > 0:
                prev_t = times[idx - 1]
                cur = rows_by_t.get(fail_time_star, {})
                prev = rows_by_t.get(prev_t, {})
                for sig in fail_signal_names:
                    exp_k = f"{sig}_ref"
                    act_k = f"{sig}_dut"
                    exp = cur.get(exp_k)
                    act = cur.get(act_k)
                    exp_prev = prev.get(exp_k)
                    act_prev = prev.get(act_k)
                    hint: dict[str, Any] = {}
                    if exp is not None and act is not None and exp_prev is not None and act_prev is not None:
                        if _wildcard_match(exp_prev, act) and not _wildcard_match(exp, act):
                            hint["actual_matches_prev_expected"] = True
                        if _wildcard_match(exp, act_prev) and not _wildcard_match(exp_prev, act_prev):
                            hint["prev_actual_matches_current_expected"] = True
                    if hint:
                        hint["prev_t"] = prev_t
                        hint["t"] = fail_time_star
                        timing_hints[sig] = hint

        # Alignment diagnosis over a wider (but bounded) window of edge samples.
        if edges_in_order:
            diag_candidates = [e for e in edges_in_order if e[0] <= fail_time_star]
            diag_candidates = diag_candidates[-min(len(diag_candidates), max(20, diag_edges)) :]

            for sig in fail_signal_names:
                exp_leaf = f"{sig}_ref"
                act_leaf = f"{sig}_dut"
                seq: list[dict[str, Any]] = []
                for tt, et in diag_candidates:
                    seq.append(
                        {
                            "t": tt,
                            "edge": et,
                            "exp": sample_signal(leaf=exp_leaf, t=tt),
                            "act": sample_signal(leaf=act_leaf, t=tt),
                        }
                    )

                def rate(pairs: list[tuple[str | None, str | None]]) -> float | None:
                    total = 0
                    ok = 0
                    for e, a in pairs:
                        if e is None or a is None:
                            continue
                        total += 1
                        if _wildcard_match(e, a):
                            ok += 1
                    return (ok / total) if total else None

                exp_seq = [r["exp"] for r in seq]
                act_seq = [r["act"] for r in seq]

                cur_rate = rate(list(zip(exp_seq, act_seq)))
                lag_rate = rate(list(zip(exp_seq[1:], act_seq[:-1])))
                lead_rate = rate(list(zip(exp_seq[:-1], act_seq[1:])))

                pos_rate = rate(
                    [(r["exp"], r["act"]) for r in seq if r.get("edge") == "posedge"]
                )
                neg_rate = rate(
                    [(r["exp"], r["act"]) for r in seq if r.get("edge") == "negedge"]
                )

                choices = {
                    "current": cur_rate,
                    "dut_lag1": lag_rate,
                    "dut_lead1": lead_rate,
                }
                best = max(choices.items(), key=lambda kv: (-1.0 if kv[1] is None else kv[1]))
                alignment_diagnosis[sig] = {
                    "samples_considered": len(seq),
                    "match_rate_current": cur_rate,
                    "match_rate_dut_lag1": lag_rate,
                    "match_rate_dut_lead1": lead_rate,
                    "match_rate_posedge": pos_rate,
                    "match_rate_negedge": neg_rate,
                    "best_alignment": best[0] if best[1] is not None else None,
                }

    report: dict[str, Any] = {
        "fail_time": fail_time_star,
        "total_mismatches": total_mismatches,
        "fail_outputs": _fill_from_probe(
            _fill_from_stdout(fail_details or fail_outputs, values), stdout, fail_time
        ),
        "input_window": input_window,
        # Fall back to the cycle dump when the VCD path produced nothing, so the
        # debugger's first diagnostic step is never handed an empty field.
        "alignment_diagnosis": alignment_diagnosis or _alignment_from_cycle_dump(stdout),
        "suspect_blocks": [
            {
                "id": b.id,
                "kind": b.kind,
                "clocking": b.clocking,
                "writes": list(b.writes),
                "reads": list(b.reads),
                "start_line": b.start_line,
                "end_line": b.end_line,
                "code_snippet": b.code[:1200],
            }
            for b in sorted(suspect_blocks, key=lambda x: (x.start_line, x.id))
        ],
        "notes": {
            "vcd_path": str(vcd_path) if vcd_path.exists() else None,
            "vcd_available": bool(vcd_available),
            "dut_instance": dut_instance,
            "sampling": {
                "non_clk": "value immediately before time t (to approximate values seen in always@(posedge/negedge) before NBAs)",
                "clk": "value at time t (edge value)",
            },
            "timing_hints": timing_hints,
            "ports": ports,
            "rtl_blocks": len(blocks),
        },
    }

    return report, suspect_blocks
