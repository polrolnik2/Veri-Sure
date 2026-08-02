from __future__ import annotations

import json
import re
from typing import Any

# Per-scenario failure markers emitted by the structured TB (tb_generator
# NON_GOLDEN_TB_PROMPT item 9). The result line carries timing pointers, e.g.:
#   [TEST overflow] FAIL (3 mismatches, first at time 240, window 200..280)
_FAILED_TEST_LINE_RE = re.compile(
    r"\[TEST\s+([A-Za-z0-9_]+)\]\s+FAIL\b([^\n]*)", re.IGNORECASE
)


def failing_test_scenarios(sim_log: str) -> list[dict]:
    """Failing TB scenarios with their timing pointers, sorted by name, de-duped.

    Each entry: ``{name, mismatches, first_fail_time, window}`` where the latter
    three are best-effort (``None`` if the TB didn't print them). The timing lets a
    reviewer locate each failure in the waveform instead of only knowing *which*
    scenario failed.
    """
    text = sim_log or ""
    seen: dict[str, dict] = {}
    for m in _FAILED_TEST_LINE_RE.finditer(text):
        name, rest = m.group(1), (m.group(2) or "")
        if name in seen:
            continue

        def _first_int(pattern: str) -> int | None:
            mm = re.search(pattern, rest, re.IGNORECASE)
            return int(mm.group(1)) if mm else None

        win = re.search(r"window\s+(\d+)\s*\.\.\s*(\d+)", rest, re.IGNORECASE)
        seen[name] = {
            "name": name,
            "mismatches": _first_int(r"(\d+)\s*mismatch"),
            "first_fail_time": _first_int(r"first\s+at\s+time\s+(\d+)"),
            "window": [int(win.group(1)), int(win.group(2))] if win else None,
        }
    return [seen[k] for k in sorted(seen)]


def failing_test_primitives(sim_log: str) -> list[str]:
    """Names of failing TB scenarios — sorted, de-duplicated (timing dropped)."""
    return [s["name"] for s in failing_test_scenarios(sim_log)]


def _first_fail_time_is_per_scenario(s: dict) -> bool:
    """Is this scenario's ``first_fail_time`` actually about THIS scenario?

    Generated testbenches commonly track ONE global `first_mismatch_time`, set
    on the first mismatch of the whole run, and then copy that global into every
    per-scenario record:

        time first_mismatch_time;                              // global
        if (mismatch_count == 0) first_mismatch_time = $time;  // set once, ever
        current_scenario.first_mismatch = first_mismatch_time; // into EVERY scenario

    The result reaches the debugger as fifteen scenarios that all "first fail"
    at one instant, including scenarios whose own window starts long after it:

        reset_during_valid (1 mismatches, first mismatch at time 80000,
                            ran in time window 830000..860000)

    Under a prompt that says "these scenarios are ALL failing -- look for the
    common root cause that resolves them together", that reads as a near-perfect
    description of a global LATENCY defect. Measured on stage_roundpack (job
    7846415): the debugger acted on exactly that hypothesis, and 6 of its 7 edits
    removed pipeline registers the contract requires -- every one rolled back,
    zero improvements, the session ending where it began. It reasoned correctly
    from false evidence.

    A time outside the scenario's own window is not a fact about that scenario,
    so do not render it as one. The testbench defect is model-authored and will
    recur; the harness must not amplify it into a false root-cause signal.
    """
    t, win = s.get("first_fail_time"), s.get("window")
    if t is None:
        return False
    if not win or len(win) != 2:
        return True  # nothing to contradict it
    return win[0] <= t <= win[1]


def format_failing_scenarios(scenarios: list[dict]) -> str:
    """Render :func:`failing_test_scenarios` output as agent-readable bullet lines."""
    lines: list[str] = []
    suppressed = 0
    for s in scenarios:
        bits: list[str] = []
        if s.get("mismatches") is not None:
            bits.append(f"{s['mismatches']} mismatches")
        if _first_fail_time_is_per_scenario(s):
            bits.append(f"first mismatch at time {s['first_fail_time']}")
        elif s.get("first_fail_time") is not None:
            suppressed += 1
        if s.get("window"):
            bits.append(f"ran in time window {s['window'][0]}..{s['window'][1]}")
        suffix = f" ({', '.join(bits)})" if bits else ""
        lines.append(f"  - {s['name']}{suffix}")
    if suppressed:
        # Say WHY it is missing. Silence would read as "the TB didn't report it",
        # which is a different and equally misleading claim.
        lines.append(
            f"  (NOTE: {suppressed} scenario(s) reported a first-mismatch time outside "
            f"their own execution window -- the testbench is tracking one GLOBAL "
            f"first-mismatch time rather than a per-scenario one, so that time has been "
            f"omitted. Do NOT read a shared timestamp across scenarios as evidence of a "
            f"common timing or latency defect.)"
        )
    return "\n".join(lines)


_HINT_OUTPUT_RE = re.compile(
    r"Hint:\s+Output\s+'(?P<sig>[^']+)'\s+has\s+(?P<cnt>\d+)\s+mismatches", re.I
)


def latency_confirmed_note(sim_log: str) -> str:
    """State plainly when the oracle has already PROVEN the pipeline latency correct.

    A composition's latency-carrying output (`valid_out`, the contract's 1-cycle
    delay of `valid_in`) is checked by the same oracle as everything else. If it
    matches on every sample while a data output does not, the register structure
    is right and the defect is functional. That is a deduction from the oracle's
    own result -- no golden reference, nothing invented.

    It was already in the log on stage_roundpack (job 7846415), five lines above
    the scenario list:

        Hint: Output 'result_out' has 21 mismatches. First mismatch at time 80000.
        Hint: Output 'valid_out' has 0 mismatches.

    and the debugger spent 6 of 7 edits removing the very registers that clean
    `valid_out` proves are correct. The fact was present, unremarked, in a
    1,755-line prompt. Saying it out loud costs two lines and directly refutes
    the hypothesis the debugger keeps forming.
    """
    counts: dict[str, int] = {}
    for m in _HINT_OUTPUT_RE.finditer(sim_log or ""):
        counts[m.group("sig")] = int(m.group("cnt"))
    if not counts:
        return ""
    clean = sorted(s for s, c in counts.items() if c == 0 and re.search(r"valid|ready|ack|done", s, re.I))
    failing = sorted(s for s, c in counts.items() if c > 0)
    if not clean or not failing:
        return ""
    return (
        "LATENCY IS CONFIRMED CORRECT — do not change it.\n"
        f"  {', '.join(clean)} carries this module's pipeline latency and has ZERO "
        f"mismatches on every sample.\n"
        f"  If the registered latency were wrong, it would mismatch too. It does not, "
        f"so the register/pipeline structure is RIGHT and {', '.join(failing)} "
        f"differ(s) for a FUNCTIONAL reason (wrong value), not a timing one.\n"
        "  Converting always_ff to always_comb, or removing a pipeline stage, will "
        "make this strictly worse.\n"
    )


def add_lineno(file_content: str) -> str:
    lines = file_content.split("\n")
    ret = ""
    for i, line in enumerate(lines):
        ret += f"{i+1}: {line}\n"
    return ret


def clip_text(text: str, *, max_chars: int) -> str:
    if not isinstance(text, str):
        text = str(text)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n...<snip>...\n" + text[-half:]


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse: pull the first valid JSON object from text."""
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise json.JSONDecodeError("No JSON object found", text, 0)


def extract_xml_tag(text: str, tag: str, *, required: bool = True, which: str = "last") -> str:
    """Extract the text inside <tag>...</tag> (case-insensitive).

    Picks the last match by default to be resilient to echoed examples.
    """
    if which not in {"first", "last"}:
        raise ValueError("which must be 'first' or 'last'")

    pattern = re.compile(
        rf"<\s*{re.escape(tag)}\s*>(.*?)</\s*{re.escape(tag)}\s*>",
        re.IGNORECASE | re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        if required:
            raise ValueError(f"Missing <{tag}>...</{tag}> block")
        return ""
    m = matches[0] if which == "first" else matches[-1]
    return m.group(1)


def strip_markdown_code_fences(text: str) -> str:
    """Remove surrounding Markdown triple-backtick fences if present."""
    if not isinstance(text, str):
        text = str(text)
    s = text.strip()
    if not s.startswith("```"):
        return s

    lines = s.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
