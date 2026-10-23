"""Agreement with independently generated designs, as a latch criterion for the RTL editor.

**WHY.** The editor's own latch -- passing shipped requirements rise -- was audited commit by
commit against golden (`docs/evidence/e7/FEEDBACK-AUDIT.md`, 73 commits): the direction of its
verdict is unrelated to golden's. A golden-free alternative was tested offline on the same commits
and on a held-out arm (`docs/evidence/e7/LATCH-OFFLINE.md`): the change in agreement with a few
designs generated independently from the same specification tracks golden.

**WHAT.** `ConsensusGate` drives any design open loop through the run's own stimulus, realized
against the run's reference model (golden-free: everything comes from the run directory), and
scores it by the share of edges on which every spec output equals a peer's, averaged over the
peers. `judge(before, after)` says whether a commit raises that agreement and which outputs moved
away from the peers. Peers are only ever simulated: their code and values never reach the editor.

The testbench is the e7 behaviour harness's (`docs/evidence/e7_behaviour/sim.py`), so the gate
measures what the offline test measured: each testpoint starts with the runtime's reset (every
input idle, resets asserted for two edges, released for one), inputs are applied with the clock
low, outputs are sampled before the edge.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from .strip_probes import deliverable


def _tb(module: str, clock: str | None, ins: list[str], outs: list[str], width: dict,
        idle: dict, resets: list[str], inactive: dict) -> str:
    def dw(n):
        return f"[{width.get(n, 1) - 1}:0] " if width.get(n, 1) > 1 else ""
    conns = ([f".{clock}({clock})"] if clock else []) + [f".{n}(i_{n})" for n in ins] + [f".{n}(o_{n})" for n in outs]
    tick = f"#1 {clock} = 1; #1 {clock} = 0;" if clock else "#2;"
    lines = ["`timescale 1ns/1ps", "module tb;", f"  reg {clock} = 0;" if clock else ""]
    lines += [f"  reg {dw(n)}i_{n};" for n in ins] + [f"  wire {dw(n)}o_{n};" for n in outs]
    lines += [
        f"  {module} dut({', '.join(conns)});",
        "  integer fi, fo, r, typ; reg [8*1024:1] fin, fout;",
        "  initial begin",
        '    if (!$value$plusargs("in=%s", fin) || !$value$plusargs("out=%s", fout)) $finish;',
        '    fi = $fopen(fin, "r"); fo = $fopen(fout, "w");',
        '    while ($fscanf(fi, "%d", typ) == 1) begin',
        "      if (typ == 0) begin",
        '        $fwrite(fo, "#\\n");',
        *[f"        i_{n} = {int(idle.get(n, 0) or 0)};" for n in ins if n not in resets],
        *[f"        i_{n} = {1 - inactive[n]};" for n in resets],
        f"        repeat (2) begin #2; {tick} end",
        *[f"        i_{n} = {inactive[n]};" for n in resets],
        f"        #2; {tick}",
        "      end",
        "      else begin",
        *[f'        r = $fscanf(fi, "%h", i_{n});' for n in ins],
        "        #1;",
        '        $fwrite(fo, "' + " ".join(["%h"] * len(outs)) + '\\n", ' + ", ".join(f"o_{n}" for n in outs) + ");",
        f"        {tick}",
        "      end",
        "    end",
        "    $fclose(fo); $finish;",
        "  end",
        "endmodule",
    ]
    return "\n".join(lines) + "\n"


def realize_stimulus(run_dir: Path, contract: dict) -> dict[str, list[list[int | None]]]:
    """Each testpoint's steps replayed through the run's reference model -> fixed input rows."""
    from specflow.refmodel.compose import choose_base
    from specflow.refmodel.oracles import replay

    run_dir = Path(run_dir)
    src_dir = run_dir / "specflow" if (run_dir / "specflow" / "stimulus.json").is_file() else run_dir
    src = (run_dir / "ref_model.py").read_text()
    s = json.loads((src_dir / "stimulus.json").read_text())
    stim = s["testpoints"] if isinstance(s, dict) else s
    ins = [p["name"] for p in contract["io"] if p["dir"] == "input"]
    base = choose_base(contract)
    rows: dict[str, list[list[int | None]]] = {}
    for t in stim:
        steps = t.get("stimulus_steps") or []
        if steps:
            rep = replay(src, contract, steps, base=base)
            rows[t["tp_uid"]] = [[r["inputs"].get(n) for n in ins] for r in rep.rows]
    return rows


class ConsensusGate:
    """Score designs by edge agreement with independently generated peers on one stimulus."""

    #: **THE SMALLEST RISE THAT COUNTS**, as a share of edges (0.001 = 0.1 points). In the audited
    #: commits a rise below it was a coin flip against golden (checks arm 5 better : 6 worse, model
    #: arm 3 : 6), a rise above 1 point nearly always right (11 : 0, 3 : 1). Chosen after seeing
    #: both arms (docs/evidence/e7/LATCH-OFFLINE.md), so it is a tuned value, not a tested one. The
    #: first live smoke run latched a +0.08-point rise that broke 1,565 output cells.
    MIN_GAIN = 0.001

    def __init__(self, *, contract: dict, rows_by_tp: dict[str, list[list[int | None]]],
                 peers: Iterable[str], include_dirs: Iterable[str] = (),
                 extra_sources: Iterable[str] = (), workdir: str | Path | None = None,
                 min_gain: float | None = None):
        from specflow.ports import idle_values, inactive_value, is_reset

        self.contract = contract
        self.min_gain = self.MIN_GAIN if min_gain is None else float(min_gain)
        self.module = str(contract.get("module_name") or "TopModule")
        io = contract.get("io") or []
        self.clock = (contract.get("clocking") or {}).get("clock", {}).get("name")
        self.inputs = [p["name"] for p in io if p.get("dir") == "input" and p["name"] != self.clock]
        self._all_inputs = [p["name"] for p in io if p.get("dir") == "input"]
        self.outputs = [p["name"] for p in io if p.get("dir") == "output"]
        width = {p["name"]: int(p.get("width") or 1) for p in io}
        resets = [n for n in self.inputs if is_reset(n)]
        self.include_dirs = [str(d) for d in include_dirs]
        self.extra_sources = [str(f) for f in extra_sources]
        self.workdir = Path(workdir or tempfile.mkdtemp(prefix="consensus_gate_"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / "tb.v").write_text(_tb(self.module, self.clock, self.inputs, self.outputs, width,
                                               dict(idle_values(contract)), resets,
                                               {n: inactive_value(n) for n in resets}))
        self.tps = sorted(rows_by_tp)
        idx = [self._all_inputs.index(n) for n in self.inputs]
        with (self.workdir / "stim.txt").open("w") as fh:
            for tp in self.tps:
                fh.write("0\n")
                for row in rows_by_tp[tp]:
                    fh.write("1 " + " ".join(format(int(row[i] or 0), "x") for i in idx) + "\n")
        self._cache: dict[str, dict | None] = {}
        self.peers = [t for t in (self.trace(p) for p in peers) if t is not None]

    @classmethod
    def from_run(cls, run_dir: str | Path, peers: Iterable[str], **kw) -> "ConsensusGate":
        """Contract and stimulus from an editor run directory (`specflow/`, `ref_model.py`)."""
        run_dir = Path(run_dir)
        cpath = run_dir / "specflow" / "contract.json"
        contract = json.loads((cpath if cpath.is_file() else run_dir / "contract.json").read_text())
        return cls(contract=contract, rows_by_tp=realize_stimulus(run_dir, contract), peers=peers, **kw)

    def trace(self, rtl: str) -> dict | None:
        """{testpoint: [[output hex strings] per edge]}, or None if it does not compile."""
        #: A design already wrapped (`<top>__probed` inside) is shipped as is: wrapping it again
        #: would declare `<top>__probed` twice.
        if re.search(r"\bmodule\s+" + re.escape(self.module) + r"__probed\b", rtl):
            text = rtl
        else:
            text = deliverable(rtl, self.contract) or rtl
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h in self._cache:
            return self._cache[h]
        src, vvp, out = self.workdir / f"{h}.sv", self.workdir / f"{h}.vvp", self.workdir / f"{h}.out"
        src.write_text(text)
        have = set(re.findall(r"^\s*module\s+(\w+)", text, re.M))
        libs = [f for f in self.extra_sources if Path(f).stem not in have]
        c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(vvp),
                            *[f"-I{d}" for d in self.include_dirs], str(self.workdir / "tb.v"), str(src), *libs],
                           capture_output=True, text=True)
        res = None
        if c.returncode == 0:
            subprocess.run(["vvp", "-n", str(vvp), f"+in={self.workdir / 'stim.txt'}", f"+out={out}"],
                           capture_output=True, text=True, timeout=3600)
            if out.is_file():
                res, cur = {tp: [] for tp in self.tps}, -1
                for line in out.read_text().splitlines():
                    if line == "#":
                        cur += 1
                    elif 0 <= cur < len(self.tps):
                        res[self.tps[cur]].append(line.split())
        for f in (vvp, out, src):
            f.unlink(missing_ok=True)
        self._cache[h] = res
        return res

    @staticmethod
    def _agree(x: dict, y: dict, port: int | None = None) -> float:
        e = t = 0
        for tp, a in x.items():
            b = y.get(tp, [])
            if port is None:
                e += sum(ra == rb for ra, rb in zip(a, b))
            else:
                e += sum(len(ra) > port and len(rb) > port and ra[port] == rb[port] for ra, rb in zip(a, b))
            t += max(len(a), len(b))
        return e / t if t else 0.0

    def agreement(self, rtl: str) -> float | None:
        """Mean over the peers of the share of edges where every spec output equals the peer's."""
        tr = self.trace(rtl)
        if tr is None or not self.peers:
            return None
        return statistics.mean(self._agree(tr, p) for p in self.peers)

    def judge(self, before: str, after: str) -> dict:
        """Did `after` move toward the peers, and which outputs moved away?"""
        a0, a1 = self.agreement(before), self.agreement(after)
        fell = []
        tb, ta = self.trace(before), self.trace(after)
        if tb is not None and ta is not None and self.peers:
            for k, name in enumerate(self.outputs):
                d = statistics.mean(self._agree(ta, p, k) - self._agree(tb, p, k) for p in self.peers)
                if d < -1e-9:
                    fell.append((name, d))
        fell.sort(key=lambda kv: kv[1])
        return {"peers": len(self.peers), "before": a0, "after": a1, "min_gain": self.min_gain,
                "rises": a0 is not None and a1 is not None and a1 >= a0 + self.min_gain - 1e-12
                and a1 > a0 + 1e-12,
                "outputs_moved_away": [n for n, _ in fell],
                #: False when no spec output differs on any edge: the batch cannot move agreement
                "behaviour_changed": None if tb is None or ta is None else tb != ta}
