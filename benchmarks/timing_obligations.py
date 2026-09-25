"""How many duration obligations does the corpus actually contain?

Phase 5 of the transactional-oracle plan is gated on this number. The canonical
example -- "`cmd_ack` is asserted for exactly one `clk` cycle" -- is the single
strongest timing sentence in the benchmark, not a representative one, and a
pipeline feature built from one example is a feature built from an anecdote.

So: extract, count, and validate every extracted obligation against the golden
RTL before believing any of it. The failure mode being guarded against is
concrete. `or1200_ic_fsm`'s specification calls `first_hit_ack` a "One-cycle
acknowledge", and the golden RTL implements it as a continuous `assign` with no
width guarantee whatsoever -- so a classifier keying on that phrasing generates
a check GOLDEN FAILS. An oracle that fails correct RTL is the exact defect this
whole line of work exists to remove; reintroducing it through a timing extractor
would be a poor trade.

The extractor here is as narrow as the evidence supports: a pulse-width claim,
about a declared output port, with a verb of assertion. Three distractors
dominate the naive lexicon and are rejected explicitly:

* `one-cycle delayed` / `one-cycle registered copy` -- a LATENCY claim about
  when a value appears, not a WIDTH claim about how long it stays;
* `<port>: One-cycle acknowledge for ...` -- a port-glossary label, a noun
  phrase with no assertion and no claim;
* a sentence with a cycle count that names no declared output port at all.

Run: python -m benchmarks.timing_obligations [--task NAME] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DES = Path(__file__).resolve().parent / "chipverilog" / "Des"

_NUMBER = {"one": 1, "a": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5}

#: `<n> [clock|clk|system|bus] cycle(s)`, the only duration unit that matters
#: for a boundary-observable obligation.
_DURATION = re.compile(
    r"\b(?:for\s+)?(?:exactly\s+|precisely\s+)?"
    r"(one|two|three|four|five|single|a|\d+)"
    r"[\s-]+(?:clock|clk|system|bus|`clk`)?[\s-]*cycles?\b",
    re.I,
)

#: The verb has to be about ASSERTING the signal. Without one, "one-cycle X" is
#: a noun phrase and says nothing about how long anything is held.
_ASSERTION = re.compile(
    r"\b(assert|asserts|asserted|pulse|pulses|pulsed|drive|drives|driven|"
    r"held|hold|holds|remain|remains|stay|stays|active|high|low)\b",
    re.I,
)

#: A latency claim wearing the same words. "one-cycle delayed" says WHEN, not
#: HOW LONG, and a design that delays by one and then holds for ten satisfies it.
_LATENCY_NOT_WIDTH = re.compile(
    r"\b(delay|delayed|delaying|registered|register|copy|version|latency|after)\b",
    re.I,
)

#: A sentence that DENIES the pulse. `or1200_except`'s specification says
#: "except_start is a combinational level signal, not a one-cycle pulse" -- and
#: the first version of this extractor read that as an obligation and generated
#: a check the golden design fails, which is precisely the failure this whole
#: measurement exists to catch. A fourth distractor, and the most dangerous kind:
#: the specification is not silent, it says the opposite.
_NEGATED = re.compile(
    r"\b(not|never|no longer|rather than|instead of|does not|doesn't|isn't|is not)\b",
    re.I,
)

#: `  - first_hit_ack: One-cycle acknowledge for a cache hit`. A glossary entry:
#: the port name, a colon, then a noun phrase. No claim is being made.
_GLOSSARY = r"^\s*(?:[-*]\s*)?(?:reg|wire|input|output)?\s*[\w\[\]:\s]*?\b%s\b\s*:"


def _clause_around(text: str, start: int, end: int) -> str:
    """The clause the duration phrase sits in, not the whole sentence.

    Scope matters in both directions. Sentence-wide, "If stop is NOT asserted,
    ... generates a one-cycle cmd_ack" is thrown away for a negation that
    belongs to a different clause -- a real obligation lost. Phrase-only,
    "except_start is a combinational level signal, not a one-cycle pulse" is
    accepted, and that one generates a check golden fails.
    """
    left = max(text.rfind(c, 0, start) for c in ",;:")
    right = min(
        (i for i in (text.find(c, end) for c in ",;:") if i != -1),
        default=len(text),
    )
    return text[left + 1:right]


@dataclass
class Obligation:
    task: str
    port: str
    cycles: int
    sentence: str
    verdict: str = ""          # holds / cannot-hold / inconclusive
    evidence: str = ""


@dataclass
class TaskReport:
    task: str
    family: str
    outputs: list[str] = field(default_factory=list)
    obligations: list[Obligation] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)


_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def _outputs(rtl: str) -> list[str]:
    """Declared output ports of the golden module, by name.

    Comments are stripped FIRST, and that is not tidiness. Scanning the raw text
    of `i2c_master_bit_ctrl` for `output` matched the word inside
    `// i2c clock line output enable (active low)` and yielded the ports
    `enable`, `end` and `yet` while LOSING `scl_oen` and `sda_oen` -- so the
    extractor then read "At the **end** of a command sequence" as a claim about
    a port named `end` and reported it as an obligation.
    """
    rtl = _COMMENT.sub(" ", rtl)
    names: list[str] = []
    for m in re.finditer(r"\boutput\s+(?:reg\s+|wire\s+)?(?:\[[^\]]*\]\s*)?([\w, ]+)", rtl):
        for name in m.group(1).split(","):
            name = name.strip()
            if name and name.isidentifier() and name not in names:
                names.append(name)
    return names


def _sentences(text: str) -> list[str]:
    # Bullet lines are their own sentence: the glossary lives in them and they
    # rarely end in a period.
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.extend(s.strip() for s in re.split(r"(?<=[.;])\s+", line) if s.strip())
    return out


def _extract(task: str, spec: str, outputs: list[str]) -> TaskReport:
    report = TaskReport(task=task, family="", outputs=outputs)
    for sentence in _sentences(spec):
        m = _DURATION.search(sentence)
        if not m:
            continue
        word = m.group(1).lower()
        cycles = _NUMBER.get(word) or (int(word) if word.isdigit() else 0)
        if not cycles:
            continue
        present = [p for p in outputs if re.search(rf"`?\b{re.escape(p)}\b`?", sentence)]
        if not present:
            report.rejected.append((sentence, "no declared output port in the sentence"))
            continue
        if _LATENCY_NOT_WIDTH.search(sentence):
            report.rejected.append((sentence, "a latency claim, not a width claim"))
            continue
        if _NEGATED.search(_clause_around(sentence, m.start(), m.end())):
            report.rejected.append((sentence, "the clause DENIES the duration"))
            continue
        if not _ASSERTION.search(sentence):
            report.rejected.append((sentence, "no verb of assertion; a noun phrase"))
            continue
        if any(re.match(_GLOSSARY % re.escape(p), sentence) for p in present):
            report.rejected.append((sentence, "a port-glossary label, not a claim"))
            continue
        for port in present:
            report.obligations.append(Obligation(task, port, cycles, sentence))
    return report


def _validate(ob: Obligation, rtl: str) -> None:
    """Does the GOLDEN design actually satisfy the extracted obligation?

    Static, and deliberately conservative about saying yes. What it can settle
    for certain is the counter-example: a continuous `assign` gives a signal
    whatever width its driving expression has, so it cannot guarantee a
    one-cycle pulse -- and that is exactly how `or1200_ic_fsm` implements the
    `first_hit_ack` its specification calls a "One-cycle acknowledge".
    """
    port = re.escape(ob.port)
    if re.search(rf"^\s*assign\s+{port}\s*=", rtl, re.M):
        ob.verdict = "cannot-hold"
        ob.evidence = f"golden drives {ob.port} with a continuous assign: no width guarantee"
        return
    # `#1` is not decoration -- every non-blocking assignment in the OpenCores
    # i2c core carries one, and a validator that did not allow it reported the
    # one obligation the corpus actually contains as "inconclusive".
    delay = r"(?:#\s*\d+\s+)?"
    default = re.search(rf"^\s*{port}\s*<=\s*{delay}(?:1'b0|1'h0|0)\s*;", rtl, re.M)
    setter = re.search(rf"^\s*{port}\s*<=\s*{delay}(?:1'b1|1'h1|1)\s*;", rtl, re.M)
    if ob.cycles == 1 and default and setter:
        ob.verdict = "holds"
        ob.evidence = (f"golden defaults {ob.port} low and sets it conditionally in a "
                       f"clocked block: the shape of a one-cycle pulse")
        return
    ob.verdict = "inconclusive"
    ob.evidence = "no default-low + conditional-set pair found; needs simulation to settle"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", help="restrict to one task directory name")
    ap.add_argument("--verbose", action="store_true", help="print rejected candidates too")
    ap.add_argument("--json", type=Path, help="write the full measurement here")
    args = ap.parse_args(argv)

    reports: list[TaskReport] = []
    for spec_path in sorted(DES.glob("*/*/description.txt")):
        task = spec_path.parent.name
        if args.task and task != args.task:
            continue
        rtl_path = spec_path.parent / f"{task}.v"
        rtl = rtl_path.read_text(errors="ignore") if rtl_path.exists() else ""
        report = _extract(task, spec_path.read_text(errors="ignore"), _outputs(rtl))
        report.family = spec_path.parent.parent.name
        for ob in report.obligations:
            _validate(ob, rtl)
        reports.append(report)

    obligations = [ob for r in reports for ob in r.obligations]
    with_any = [r for r in reports if r.obligations]
    print(f"{len(reports)} specs, {len(with_any)} with a boundary-observable duration "
          f"obligation, {len(obligations)} obligations total\n")
    for r in sorted(with_any, key=lambda r: r.task):
        print(f"  {r.family}/{r.task}: {len(r.obligations)}")
        for ob in r.obligations:
            print(f"      {ob.port} == {ob.cycles} cycle(s)  [{ob.verdict}] {ob.evidence}")
            print(f'        "{ob.sentence[:150]}"')
    bad = [ob for ob in obligations if ob.verdict == "cannot-hold"]
    unsure = [ob for ob in obligations if ob.verdict == "inconclusive"]
    print(f"\nvalidated against golden: {len(obligations) - len(bad) - len(unsure)} hold, "
          f"{len(unsure)} inconclusive, {len(bad)} GOLDEN WOULD FAIL")
    for ob in bad:
        print(f"  !! {ob.task}.{ob.port}: {ob.evidence}")

    if args.verbose:
        print("\nrejected candidates (the distractors, and why):")
        counts: dict[str, int] = {}
        for r in reports:
            for sentence, why in r.rejected:
                counts[why] = counts.get(why, 0) + 1
                print(f'  [{r.task}] {why}: "{sentence[:120]}"')
        print(f"\n  {counts}")

    if args.json:
        args.json.write_text(json.dumps(
            [{"task": r.task, "family": r.family,
              "obligations": [vars(o) for o in r.obligations],
              "rejected": r.rejected} for r in reports], indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
