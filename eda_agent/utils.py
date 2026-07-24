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


def format_failing_scenarios(scenarios: list[dict]) -> str:
    """Render :func:`failing_test_scenarios` output as agent-readable bullet lines."""
    lines: list[str] = []
    for s in scenarios:
        bits: list[str] = []
        if s.get("mismatches") is not None:
            bits.append(f"{s['mismatches']} mismatches")
        if s.get("first_fail_time") is not None:
            bits.append(f"first mismatch at time {s['first_fail_time']}")
        if s.get("window"):
            bits.append(f"ran in time window {s['window'][0]}..{s['window'][1]}")
        suffix = f" ({', '.join(bits)})" if bits else ""
        lines.append(f"  - {s['name']}{suffix}")
    return "\n".join(lines)


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
