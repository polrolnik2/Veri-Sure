"""Targeted arbitration: a narrow judgment against the specification, for commits agreement cannot decide.

**WHY.** The consensus latch keeps a commit when its agreement with independently generated designs
rises (`consensus_gate.py`). When passing requirements rise but agreement moves by less than its
margin or falls a little, agreement does not separate real fixes from regressions: dc_fsm luna14's
fix and sb luna12's regression both cost ~0.85 points. Offline (`docs/evidence/e7/
ARBITRATION-OFFLINE.md`, variant 3), a judge shown only where the two designs' outputs diverge
decided 18 of 22 such commits as golden does, against 11 for the 0.5-point tolerance.

**WHAT.** `SpecArbiter.decide(before, after)` simulates both designs on the gate's own stimulus
(golden-free), takes the testpoints where their outputs diverge, draws `k` with probability
proportional to the output cells changed, and asks the model, once per label order, which
candidate's outputs the specification requires there. The judge sees the specification (and each
child module's), the macros it names as the design's include files set them, the ports, the
reset the bench applies, and the testpoint from reset, with long runs of identical rows collapsed.
It never sees the checks, the peers, or which candidate is the edit. The score is the cell-weighted
vote, +1 for the edit and -1 for the design before it; 0 when every answer abstains.

**A CHILD'S PORTS** (`child_sources`, variant 4 offline): a design that instantiates a given child
module -- byte_ctrl's reference bit controller -- has pins that come straight from that child, so
they differ only because this module drives the child differently. Each child port wired to an
internal net is probed in both candidates' simulations and shown as a column, and the judge is told
the child is the given reference: it judges this module's decisions, not the child's timing.
Offline this took byte_ctrl's five commits from 3 to 5 decided as golden does.

Prompts and replies are logged to `workdir/calls.jsonl` (model I/O: keep it out of public repos).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

SYSTEM = """You are a hardware verification judge. You are given a module's specification, its \
build configuration, its ports, and a simulation excerpt in which two candidate implementations of \
the module, X and Y, received exactly the same inputs. Their outputs differ on the rows marked <<. \
Decide which candidate's outputs on the marked rows are the ones the specification requires, for \
this configuration. Proceed in order: (1) quote the specification sentences that determine each \
differing output, including the internal registers and flags they depend on and when each is \
updated; (2) rebuild those registers and flags from reset, edge by edge, through the excerpt, as \
the specification defines their updates -- a registered flag takes its new value only after the \
clock edge, so do not substitute an input for a flag on the same row unless the specification \
makes it combinational; (3) compute the value the specification requires on each marked row; \
(4) compare with X and Y. If the specification does not determine the marked outputs, answer \
"undetermined"; if neither candidate matches it, answer "both wrong". End your reply with one JSON \
object: {"verdict": "X" | "Y" | "both wrong" | "undetermined", "reason": "<one sentence>"}"""

_TERMINAL = ("response.completed", "response.incomplete", "response.failed")


def configuration(spec_text: str, include_dirs: Iterable[str]) -> str:
    """Each macro the specification names, defined or not (with its value), per the include files."""
    defs = sorted({p for d in include_dirs for p in Path(d).glob("*define*.v")})
    known = set(re.findall(r"define\s+(\w+)", "".join(p.read_text(errors="replace") for p in defs)))
    names = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]*_[A-Z0-9_]+\b", spec_text)) & known)
    if not names:
        return ""
    probe = "".join(f'`include "{p.name}"\n' for p in defs) + "".join(
        f"`ifdef {n}\nDEFINED {n} = `{n}\n`else\nUNDEFINED {n} =\n`endif\n" for n in names)
    out = subprocess.run(["iverilog", "-E", *[f"-I{d}" for d in include_dirs], "-o", "/dev/stdout", "/dev/stdin"],
                         input=probe, capture_output=True, text=True).stdout
    state = {n: (d, v.strip()) for d, n, v in re.findall(r"^(DEFINED|UNDEFINED) (\w+) =(.*)$", out, re.M)}
    return "".join(f"- {n} is NOT defined\n" if state.get(n, ("UNDEFINED",))[0] == "UNDEFINED" else
                   f"- {n} is defined" + (f" as {state[n][1]}\n" if state[n][1] else "\n") for n in names)


class SpecArbiter:
    """Decide a commit by asking which behaviour the specification requires where the designs diverge."""

    #: Commits whose agreement falls by more than this are refused without asking (2 points: the
    #: range tested offline; a larger fall was a regression in every audited commit but one).
    BAND = 0.02
    K, HORIZON, FOLD_AFTER, KEEP_BEFORE = 4, 16, 40, 8

    def __init__(self, *, gate, spec: str, children: dict[str, str] | None = None,
                 include_dirs: Iterable[str] = (), cfg=None, workdir: str | Path | None = None,
                 k: int | None = None, parallel: int = 8, child_sources: Iterable[str] = ()):
        self.gate, self.k, self.parallel = gate, int(k or self.K), parallel
        self.children = dict(children or {})
        self.spec = spec + "".join(f"\n\n## Specification of the child module {n}, which this module "
                                   f"instantiates\n\n{t}" for n, t in self.children.items())
        self.config = configuration(self.spec, list(include_dirs))
        self.cfg = cfg
        self.workdir = Path(workdir) if workdir else gate.workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.band = self.BAND
        self._decided: dict[tuple, dict] = {}
        self.child_sources = [str(f) for f in child_sources]
        self._child: dict[str, dict | None] = {}

    # ------------------------------------------------------------ the child's ports
    def child_ports(self, rtl: str) -> list[tuple]:
        """(port, net, width, dir) for each child port wired to one of this design's internal nets."""
        g = self.gate
        top = set(g._all_inputs) | set(g.outputs)
        text = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", rtl, flags=re.S))
        out = []
        for src in self.child_sources:
            ref = Path(src).read_text(errors="replace")
            name = re.search(r"^\s*module\s+(\w+)", ref, re.M)
            if not name:
                continue
            decl = {n: (d, int(h) - int(lo) + 1 if h else 1) for d, h, lo, n in re.findall(
                r"\b(input|output)\s+(?:reg\s+|wire\s+)?(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?(\w+)", ref)}
            m = re.search(rf"\b{name.group(1)}\b\s*(?:#\s*\(.*?\)\s*)?\w+\s*\((.*?)\);", text, re.S)
            for port, net in re.findall(r"\.(\w+)\s*\(\s*(\w+)\s*\)", m.group(1)) if m else []:
                if net not in top and port in decl:
                    out.append((port, net, decl[port][1], decl[port][0]))
        return sorted(out, key=lambda t: t[3])  # what this module drives in, then the child's reply

    def child_trace(self, rtl: str) -> dict | None:
        """{"ports": [...], "rows": {tp: [[values] per edge]}} from this design's own simulation."""
        cp = self.child_ports(rtl)
        if not cp:
            return None
        g = self.gate
        wrapped = re.search(r"\bmodule\s+" + re.escape(g.module) + r"__probed\b", rtl)
        text = rtl if wrapped else (__import__("eda_agent.strip_probes", fromlist=["deliverable"])
                                    .deliverable(rtl, g.contract) or rtl)
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h in self._child:
            return self._child[h]
        inst = re.search(re.escape(g.module) + r"__probed\s+(\w+)\s*\(", text)
        path = f"dut.{inst.group(1)}" if inst else "dut"
        tb = (g.workdir / "tb.v").read_text()
        # tb-level wires on this design's own nets: iverilog asserts on a reference into a child
        wires = "".join(f"  wire [{w - 1}:0] p_{port} = {path}.{net};\n" for port, net, w, _ in cp)
        tb = tb.replace("  integer fi,", wires + "  integer fi,", 1)
        tb = tb.replace('$fwrite(fo, "%h', f'$fwrite(fo, "{" ".join("%h" for _ in cp)} | ", '
                        f'{", ".join("p_" + c[0] for c in cp)});\n        $fwrite(fo, "%h', 1)
        d = self.workdir / "child"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{h}.tb.v").write_text(tb)
        (d / f"{h}.sv").write_text(text)
        have = set(re.findall(r"^\s*module\s+(\w+)", text, re.M))
        libs = [f for f in g.extra_sources if Path(f).stem not in have]
        c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(d / f"{h}.vvp"), *[f"-I{x}" for x in g.include_dirs],
                            str(d / f"{h}.tb.v"), str(d / f"{h}.sv"), *libs], capture_output=True, text=True)
        res = None
        if c.returncode == 0:
            o = d / f"{h}.out"
            subprocess.run(["vvp", "-n", str(d / f"{h}.vvp"), f"+in={g.workdir / 'stim.txt'}", f"+out={o}"],
                           capture_output=True, text=True, timeout=3600)
            if o.is_file():
                rows, cur = {tp: [] for tp in g.tps}, -1
                for line in o.read_text().splitlines():
                    if line == "#":
                        cur += 1
                    elif 0 <= cur < len(g.tps):
                        rows[g.tps[cur]].append(line.split(" | ")[0].split())
                res = {"ports": [list(x) for x in cp], "rows": rows}
                o.unlink()
        self._child[h] = res
        return res

    # ------------------------------------------------------------ excerpts
    def episodes(self, A: dict, B: dict) -> list[dict]:
        out = []
        for tp in self.gate.tps:
            a, b = A.get(tp, []), B.get(tp, [])
            diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
            if diff:
                rows = [i for i in diff if i < diff[0] + self.HORIZON]
                cells = sum(x != y for i in rows for x, y in zip(a[i], b[i]))
                out.append({"tp": tp, "first": rows[0], "end": rows[-1], "cells": cells})
        return out

    def pick(self, eps: list[dict], seed: str) -> list[dict]:
        rng, pool, chosen = random.Random(seed), list(eps), []
        while pool and len(chosen) < self.k:
            r, acc = rng.random() * sum(e["cells"] for e in pool), 0
            for j, e in enumerate(pool):
                acc += e["cells"]
                if acc >= r:
                    chosen.append(pool.pop(j))
                    break
        return chosen

    def _reset_note(self) -> str:
        g = self.gate
        held = ", ".join([f"{n}={1 - g.inactive[n]}" for n in g.resets]
                         + [f"{n}={v}" for n, v in g.idle.items() if v and n not in g.resets and n != g.clock])
        rel = ", ".join(f"{n}={g.inactive[n]}" for n in g.resets)
        return (f"- Each testpoint starts with a reset sequence that is not shown: for two clock cycles "
                f"{held or 'every input 0'} and every other input 0; then one cycle with {rel}, the other "
                f"inputs unchanged. Every register starts from that reset.")

    def prompt(self, ep: dict, A: dict, B: dict, swap: bool, child: tuple | None = None) -> str:
        g = self.gate
        rows_in = g.rows_by_tp[ep["tp"]]
        allin = g._all_inputs
        ins = [(allin.index(n), n) for n in g.inputs]
        outs, W = g.outputs, g.width
        x, y = (A[ep["tp"]], B[ep["tp"]]) if swap else (B[ep["tp"]], A[ep["tp"]])
        fold = ep["first"] > self.FOLD_AFTER
        hi = min(len(x), len(y), len(rows_in), ep["end"] + 4) - 1
        cx, cy, cports = [], [], []
        if child and child[0] and child[1]:  # (before, after) child traces, X and Y as the outputs
            ca, cb = child[0]["rows"][ep["tp"]], child[1]["rows"][ep["tp"]]
            cx, cy = (ca, cb) if swap else (cb, ca)
            cports = [c[0] for c in child[0]["ports"]]
            hi = min(hi, len(cx) - 1, len(cy) - 1)
        D = [k for k in range(len(outs)) if any(x[i][k] != y[i][k] for i in range(hi + 1))]
        S = [k for k in range(len(outs)) if k not in D]
        CD = [k for k in range(len(cports)) if any(cx[i][k] != cy[i][k] for i in range(hi + 1))]
        CS = [k for k in range(len(cports)) if k not in CD]

        def hexw(v, n):
            return format(int(v or 0), "x").zfill(max(1, -(-W.get(n, 1) // 4)))
        lines = [" | ".join(["row"] + [n for _, n in ins] + [f"child.{cports[k]}" for k in CS] + [outs[k] for k in S]
                            + [f"X.child.{cports[k]}" for k in CD] + [f"X.{outs[k]}" for k in D]
                            + [f"Y.child.{cports[k]}" for k in CD] + [f"Y.{outs[k]}" for k in D] + [""])]
        folded, i = False, 0
        while i <= hi:
            j = i
            while (fold and j + 1 < ep["first"] - self.KEEP_BEFORE and rows_in[j + 1] == rows_in[i]
                   and x[j + 1] == x[i] and y[j + 1] == y[i]
                   and (not cports or (cx[j + 1] == cx[i] and cy[j + 1] == cy[i]))):
                j += 1
            folded |= j > i
            lines.append(" | ".join([str(i) if j == i else f"{i}-{j}"] + [hexw(rows_in[i][c], n) for c, n in ins]
                                    + [cx[i][k] for k in CS] + [x[i][k] for k in S] + [cx[i][k] for k in CD]
                                    + [x[i][k] for k in D] + [cy[i][k] for k in CD] + [y[i][k] for k in D]
                                    + ["<<" if x[i] != y[i] else ""]))
            i = j + 1
        ports = "\n".join(f"- {d} {n} [{W.get(n, 1)} bit]" for d, names in (("input", [n for _, n in ins]),
                                                                             ("output", outs)) for n in names)
        cfg = f"## Configuration\n\nFrom the design's include files:\n{self.config}\n" if self.config else ""
        if cports:
            drv = [c[0] for c in child[0]["ports"] if c[3] == "input"]
            ret = [c[0] for c in child[0]["ports"] if c[3] == "output"]
            kid = next(iter(self.children), "its child module")
            fold_note_child = (
                f"- This module instantiates {kid}. That child is the given reference implementation: "
                f"correct, and identical in both candidates. Columns child.<port> are its ports: "
                f"{', '.join(drv)} {'is' if len(drv) == 1 else 'are'} driven by this module, "
                f"{', '.join(ret)} {'is' if len(ret) == 1 else 'are'} the child's reply. Outputs of this module "
                f"that come straight from the child differ only because of what this module drives "
                f"into it. Judge this module's own behaviour against its specification: what it drives "
                f"into the child, and its own outputs, given the child's replies.\n")
        else:
            fold_note_child = ""
        fold_note = fold_note_child + ("A row labelled a-b stands for rows a through b, which are all identical to row a in "
                     "inputs and in both candidates' outputs. There is a clock edge after every one of them, so "
                     "internal counters and registers keep advancing through the range.\n" if folded else "")
        return f"""## Specification

{self.spec}

{cfg}## Ports

{ports}

## Simulation conventions

{self._reset_note()}
- In row i the inputs of row i are applied, the outputs are sampled shortly afterwards (before
  the rising clock edge), and then the rising edge occurs. The outputs in row i therefore show
  the state left by the edges of the earlier rows, plus any combinational path from row i's
  inputs.
- Values are hexadecimal. Outputs the two candidates agree on throughout the excerpt are shown
  once; outputs on which they differ are shown as X.<name> and Y.<name>.
- Before row {ep["first"]} both candidates' outputs were identical.
{fold_note}
## Excerpt ({hi + 1} rows)

{chr(10).join(lines)}
"""

    # ------------------------------------------------------------ the judge
    def ask(self, user: str) -> dict:
        """One judgment: {"verdict": "X"|"Y"|..., "output_tokens": n}. Overridable for tests."""
        import openai

        cfg = self.cfg
        client = openai.OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=1800)
        last = None
        for attempt in range(6):
            try:
                stream = client.responses.create(
                    model=cfg.model, store=False, max_output_tokens=64000, stream=True,
                    reasoning={"effort": cfg.reasoning_effort or "xhigh", "summary": "auto"},
                    input=[{"role": "developer", "content": SYSTEM}, {"role": "user", "content": user}])
                final = None
                for ev in stream:
                    if getattr(ev, "type", "") in _TERMINAL:
                        final = ev.response
                if final is None:
                    raise RuntimeError("stream ended without a terminal event")
                rec = {"text": final.output_text, "output_tokens": final.usage.output_tokens}
                with (self.workdir / "calls.jsonl").open("a") as fh:
                    fh.write(json.dumps({"prompt": user, **rec}) + "\n")
                return {"verdict": self.parse(rec["text"]), "output_tokens": rec["output_tokens"]}
            except Exception as exc:  # noqa: BLE001 -- the gateway drops long streams; resend
                last = exc
                __import__("time").sleep(min(60, 5 * 2 ** attempt))
        return {"verdict": "failed", "output_tokens": 0, "error": type(last).__name__}

    @staticmethod
    def parse(text: str) -> str:
        m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", text or "", re.S)
        try:
            v = json.loads(m.group(0))["verdict"].strip().lower() if m else ""
        except (ValueError, KeyError, AttributeError):
            v = ""
        return {"x": "X", "y": "Y"}.get(v, v or "unparsed")

    def decide(self, before: str, after: str) -> dict:
        """{"score", "asked", "answers", "tokens", "episodes"}; score None when the designs cannot be compared."""
        A, B = self.gate.trace(before), self.gate.trace(after)
        if A is None or B is None:
            return {"score": None, "asked": 0, "answers": {}, "tokens": 0, "episodes": []}
        key = (hashlib.sha256(json.dumps(A, sort_keys=True).encode()).hexdigest(),
               hashlib.sha256(json.dumps(B, sort_keys=True).encode()).hexdigest())
        if key in self._decided:
            return self._decided[key]
        chosen = self.pick(self.episodes(A, B), key[0] + key[1])
        jobs = [(e, swap) for e in chosen for swap in (False, True)]
        child = (self.child_trace(before), self.child_trace(after)) if self.child_sources else None
        with ThreadPoolExecutor(max_workers=self.parallel) as pool:
            recs = list(pool.map(lambda job: self.ask(self.prompt(job[0], A, B, job[1], child)), jobs))
        for (e, swap), rec in zip(jobs, recs):
            v = rec["verdict"]
            e.setdefault("answers", []).append({"X": "before" if swap else "after",
                                                "Y": "after" if swap else "before"}.get(v, v))
        votes = [(sum((a == "after") - (a == "before") for a in e["answers"]) / len(e["answers"]), e["cells"])
                 for e in chosen if e.get("answers")]
        weight = sum(c for _, c in votes)
        answers: dict[str, int] = {}
        for e in chosen:
            for a in e.get("answers", []):
                answers[a] = answers.get(a, 0) + 1
        res = {"score": sum(v * c for v, c in votes) / weight if weight else 0.0, "asked": len(chosen),
               "answers": answers, "tokens": sum(r["output_tokens"] for r in recs),
               "episodes": [{"tp": e["tp"], "first": e["first"], "cells": e["cells"], "answers": e.get("answers", [])}
                            for e in chosen]}
        self._decided[key] = res
        return res
