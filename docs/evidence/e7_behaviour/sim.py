"""sim.py MODULE -- drive every design of MODULE (golden, 3 generation-only samples per
corpus, each editor job's generated and repaired design) through every corpus's fixed input
sequences, open-loop, and record the spec outputs at each edge.

The testbench applies a row's inputs while the clock is low, lets them settle, SAMPLES THE
OUTPUTS (before the edge -- the convention the checks use), then clocks. Testpoints of one
corpus run back to back in one simulation; each starts with its own reset step.
-> out/<module>/<design>.json : {stim_run: {tp: [[out hex strings per edge]]}}
"""

import json
import re
import subprocess
import sys
import os
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, "/home/user/Veri-Sure/benchmarks")
from eda_agent.strip_probes import deliverable  # noqa: E402
from run_chipverilog import child_sources, submodules  # noqa: E402
from specflow.ports import idle_values, inactive_value, is_reset  # noqa: E402

#: Working tree (stimulus, traces, metrics): large and regenerable, so outside the repo.
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = Path("/home/user/Veri-Sure/docs/evidence/e7")
DES = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des")
mod = sys.argv[1]
runs = [
    r
    for r in ("luna12", "luna13", "luna14", "luna15")
    if (EQ / "stim" / r / f"{mod}.json").is_file()
]
task = next(p.parent for p in DES.rglob("description.txt") if p.parent.name == mod)
kids = [Path(p) for p in child_sources(submodules(task, mod))]
stims = {r: json.loads((EQ / "stim" / r / f"{mod}.json").read_text()) for r in runs}
S0 = stims[runs[0]]
clock = S0["clock"]
ins = [n for n in S0["inputs"] if n != clock]
#: **THE TESTBENCH'S PER-TESTPOINT RESET** (`Env.reset`): every input idle, every declared reset
#: asserted for 2 edges, then released for 1 -- run before EVERY testpoint, not recorded. Without it
#: a testpoint whose stimulus starts without a reset step (34-82% of them) inherited the previous
#: testpoint's state, while the reference model's rows start fresh.
C0 = json.loads((EQ / "corpora" / runs[0] / mod / "contract.json").read_text())
IDLE = dict(idle_values(C0))
RESETS = [n for n in ins if is_reset(n)]
outs = S0["outputs"]
W = S0["width"]


def designs():
    d = {"golden": [task / f"{mod}.v"]}
    for r in runs:
        for k in (1, 2, 3):
            f = E / r / "ablation" / mod / f"gen{k}" / "rtl_deliverable.sv"
            if f.is_file():
                d[f"{r}.gen{k}"] = [f]
        ed = E / r / "editor" / mod
        if (ed / "rtl_generated.sv").is_file():
            contract = json.loads(
                (EQ / "corpora" / r / mod / "contract.json").read_text()
            )
            gen = (ed / "rtl_generated.sv").read_text()
            w = EQ / "designs" / r / mod
            w.mkdir(parents=True, exist_ok=True)
            (w / "r0.sv").write_text(deliverable(gen, contract) or gen)
            d[f"{r}.r0"] = [w / "r0.sv"]
        if (ed / "rtl_deliverable.sv").is_file():
            d[f"{r}.final"] = [ed / "rtl_deliverable.sv"]
    return d


def tb() -> str:
    def dw(n):
        return f"[{W.get(n, 1) - 1}:0] " if W.get(n, 1) > 1 else ""
    L = ["`timescale 1ns/1ps", "module tb;", f"  reg {clock} = 0;" if clock else ""]
    L += [f"  reg {dw(n)}i_{n};" for n in ins] + [f"  wire {dw(n)}o_{n};" for n in outs]
    conns = (
        ([f".{clock}({clock})"] if clock else [])
        + [f".{n}(i_{n})" for n in ins]
        + [f".{n}(o_{n})" for n in outs]
    )
    L += [
        f"  {mod} dut({', '.join(conns)});",
        "  integer fi, fo, r, typ; reg [8*1024:1] fin, fout;",
        "  initial begin",
        '    if (!$value$plusargs("in=%s", fin) || !$value$plusargs("out=%s", fout)) $finish;',
        '    fi = $fopen(fin, "r"); fo = $fopen(fout, "w");',
        '    while ($fscanf(fi, "%d", typ) == 1) begin',
        '      if (typ == 0) begin',
        '        $fwrite(fo, "#\\n");',
        *[f"        i_{n} = {int(IDLE.get(n, 0) or 0)};" for n in ins if n not in RESETS],
        *[f"        i_{n} = {1 - inactive_value(n)};" for n in RESETS],
        f"        repeat (2) begin #2; #1 {clock} = 1; #1 {clock} = 0; end",
        *[f"        i_{n} = {inactive_value(n)};" for n in RESETS],
        f"        #2; #1 {clock} = 1; #1 {clock} = 0;",
        '      end',
        "      else begin",
    ]
    L += [f'        r = $fscanf(fi, "%h", i_{n});' for n in ins]
    L += [
        "        #1;",
        '        $fwrite(fo, "'
        + " ".join(["%h"] * len(outs))
        + '\\n", '
        + ", ".join(f"o_{n}" for n in outs)
        + ");",
    ]
    L += [
        f"        #1 {clock} = 1; #1 {clock} = 0;" if clock else "        #2;",
        "      end",
        "    end",
        "    $fclose(fo); $finish;",
        "  end",
        "endmodule",
    ]
    return "\n".join(L) + "\n"


def stimfile(r: str) -> Path:
    p = EQ / "stimtxt" / r / f"{mod}.txt"
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        idx = [stims[r]["inputs"].index(n) for n in ins]
        with p.open("w") as fh:
            for tp in sorted(stims[r]["tps"]):
                fh.write("0\n")
                for row in stims[r]["tps"][tp]["rows"]:
                    fh.write(
                        "1 "
                        + " ".join(format(int(row[i] or 0), "x") for i in idx)
                        + "\n"
                    )
    return p


def defines(files) -> set:
    return {
        m
        for f in files
        for m in re.findall(r"^\s*module\s+(\w+)", Path(f).read_text(), re.M)
    }


def main():
    out = EQ / "out" / mod
    out.mkdir(parents=True, exist_ok=True)
    work = EQ / "work" / mod
    work.mkdir(parents=True, exist_ok=True)
    (work / "tb.v").write_text(tb())
    only = set(sys.argv[2:])
    for name, files in designs().items():
        if only and name not in only:
            continue
        have = defines(files)
        libs = [k for k in kids if k.stem not in have]
        vvp = work / f"{name}.vvp"
        cmd = [
            "iverilog",
            "-g2012",
            "-s",
            "tb",
            "-o",
            str(vvp),
            f"-I{task}",
            f"-I{task.parent}",
            str(work / "tb.v"),
            *map(str, files),
            *map(str, libs),
        ]
        c = subprocess.run(cmd, capture_output=True, text=True)
        if c.returncode:
            (out / f"{name}.json").write_text(
                json.dumps({"compile_error": (c.stderr or c.stdout)[-2000:]})
            )
            print(
                f"{mod} {name}: COMPILE ERROR {(c.stderr or c.stdout).strip().splitlines()[-1][:160]}",
                flush=True,
            )
            continue
        res = {}
        for r in runs:
            o = work / f"{name}.{r}.out"
            p = subprocess.run(
                ["vvp", "-n", str(vvp), f"+in={stimfile(r)}", f"+out={o}"],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if not o.is_file():
                res[r] = {"run_error": (p.stderr or p.stdout)[-1500:]}
                print(
                    f"{mod} {name}: RUN ERROR on {r}: {(p.stderr or p.stdout).strip()[-200:]}",
                    flush=True,
                )
                continue
            tps, cur = sorted(stims[r]["tps"]), -1
            per = {tp: [] for tp in tps}
            for line in o.read_text().splitlines():
                if line == "#":
                    cur += 1
                    continue
                per[tps[cur]].append(line.split())
            res[r] = per
            o.unlink()
        vvp.unlink(missing_ok=True)
        (out / f"{name}.json").write_text(json.dumps(res))
        print(
            f"{mod} {name}: ok ({', '.join(f'{r}:{sum(len(v) for v in res[r].values())}' for r in runs)} edges)",
            flush=True,
        )


main()
