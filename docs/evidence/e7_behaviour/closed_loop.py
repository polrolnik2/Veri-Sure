"""closed_loop.py MODULE -- every design of MODULE driven CLOSED-LOOP by each corpus's stimulus.

`realize.py` + `sim.py` give every design the SAME fixed input sequence, timed to the run's
reference model. That is the right test of cycle equivalence and the wrong one for latency: a
design that answers a cycle late still receives the next command on the model's schedule, so a
pure latency difference can cascade into what looks like a functional one.

Here each design runs the stimulus the way the shipped testbench runs it: `until` waits resolve
against THE DESIGN'S OWN outputs (timeout as declared), reset steps drive every input idle and
the resets active, the 4000-edge budget and the settle tail apply, and open-drain lines are
wired (`line = stimulus AND *_oen`, re-evaluated every edge, `bus_lines_from`). The step
decoding is the testbench's own (`normalise_step`, `is_reset_step`, `reset_ports`).
-> cl_out/<module>/<design>.json : {stim_run: {tp: [[out hex strings per edge]]}}
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, "/home/user/Veri-Sure/benchmarks")
from eda_agent.strip_probes import deliverable  # noqa: E402
from run_chipverilog import child_sources, submodules  # noqa: E402
from specflow.ports import (asserted_resets, idle_values, inactive_value,  # noqa: E402
                            is_reset, pinned_inputs)
from specflow.refmodel.oracles import EDGE_BUDGET  # noqa: E402
from specflow.tb.runtime import (SETTLE_EDGES, bus_lines_from, is_reset_step,  # noqa: E402
                                 normalise_step, reset_ports)

#: Working tree (stimulus, traces, metrics): large and regenerable, so outside the repo.
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = Path("/home/user/Veri-Sure/docs/evidence/e7")
CF_TAGS = {"cf-gen": "cfg", "cf-checks": "cfc", "cf-model": "cfm",
           #: byte_ctrl generation-only samples with the real child: its like-for-like ablation
           "abl-child-gen1": "acg1", "abl-child-gen2": "acg2", "abl-child-gen3": "acg3"}
DES = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des")
mod = sys.argv[1]
runs = [r for r in ("luna12", "luna13", "luna14", "luna15") if (EQ / "corpora" / r / mod).is_dir()]
task = next(p.parent for p in DES.rglob("description.txt") if p.parent.name == mod)
kids = [Path(p) for p in child_sources(submodules(task, mod))]
C0 = json.loads((EQ / "corpora" / runs[0] / mod / "contract.json").read_text())
clock = (C0.get("clocking") or {}).get("clock", {}).get("name")
ins = [p["name"] for p in C0["io"] if p["dir"] == "input" and p["name"] != clock]
outs = [p["name"] for p in C0["io"] if p["dir"] == "output"]
W = {p["name"]: int(p.get("width") or 1) for p in C0["io"]}
bus = [b for b in bus_lines_from(C0) if b["input"] in ins and b["oen"] in outs]
#: **THE TESTBENCH'S PER-TESTPOINT RESET** (`Env.reset`): every input idle, every declared reset
#: asserted for 2 edges, then released for 1 -- run before EVERY testpoint, not recorded. Without it
#: a testpoint whose stimulus starts without a reset step (34-82% of them) inherited the previous
#: testpoint's state, while the reference model's rows start fresh.
IDLE = dict(idle_values(C0))
RESETS = [n for n in ins if is_reset(n)]


def program(run: str) -> Path:
    """Each testpoint as steps: `1 n until_idx until_val inputs...`; `0` separates testpoints."""
    p = EQ / "cl_prog" / run / f"{mod}.txt"
    if p.is_file():
        return p
    contract = json.loads((EQ / "corpora" / run / mod / "contract.json").read_text())
    s = json.loads((EQ / "corpora" / run / mod / "stimulus.json").read_text())
    stim = {t["tp_uid"]: t.get("stimulus_steps") or [] for t in (s["testpoints"] if isinstance(s, dict) else s)}
    idle_resets, all_idle = dict(pinned_inputs(contract)), dict(idle_values(contract))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        for tp in sorted(t for t, st in stim.items() if st):
            fh.write("0\n")
            state = dict(idle_resets)
            for raw in stim[tp]:
                inputs, hold, until, timeout = normalise_step(raw)
                if is_reset_step(raw):
                    state = dict(all_idle)
                    state.update(asserted_resets(contract, only=reset_ports(raw)))
                    until, timeout = None, 0
                else:
                    state.update(idle_resets)
                    state.update(inputs)
                n = max(1, int((timeout if until else hold) or 0))
                ui, uv = (outs.index(str(until["port"])), int(until["value"])) if until else (-1, 0)
                fh.write(f"1 {n} {ui} {uv:x} " + " ".join(format(int(state.get(k) or 0), "x") for k in ins) + "\n")
            #: the settle tail, holding the last inputs, as the testbench runs it
            fh.write(f"1 {SETTLE_EDGES} -1 0 " + " ".join(format(int(state.get(k) or 0), "x") for k in ins) + "\n")
    return p


def tb() -> str:
    def dw(n):
        return f"[{W.get(n, 1) - 1}:0] " if W.get(n, 1) > 1 else ""

    L = ["`timescale 1ns/1ps", "module tb;", f"  reg {clock} = 0;"]
    L += [f"  reg {dw(n)}i_{n}; reg {dw(n)}n_{n};" for n in ins] + [f"  wire {dw(n)}o_{n};" for n in outs]
    conns = [f".{clock}({clock})"] + [f".{n}(i_{n})" for n in ins] + [f".{n}(o_{n})" for n in outs]
    L += [f"  {mod} dut({', '.join(conns)});",
          "  function [127:0] outv(input integer k);", "    case (k)"]
    L += [f"      {i}: outv = o_{n};" for i, n in enumerate(outs)]
    L += ["      default: outv = 128'bx;", "    endcase", "  endfunction",
          "  integer fi, fo, r, typ, n, ui, k, rows, exh, reached; reg [127:0] uv; reg [8*1024:1] fin, fout;",
          "  initial begin",
          '    if (!$value$plusargs("in=%s", fin) || !$value$plusargs("out=%s", fout)) $finish;',
          '    fi = $fopen(fin, "r"); fo = $fopen(fout, "w"); rows = 0; exh = 0;',
          '    while ($fscanf(fi, "%d", typ) == 1) begin',
          '      if (typ == 0) begin',
          '        $fwrite(fo, "#\\n"); rows = 0; exh = 0;']
    L += [f"        i_{n} = {int(IDLE.get(n, 0) or 0)};" for n in ins if n not in RESETS]
    L += [f"        i_{n} = {1 - inactive_value(n)};" for n in RESETS]
    wire = [f"if (o_{b['oen']} === 1'b0) i_{b['input']} = 1'b0;" for b in bus]
    L += [f"        repeat (2) begin #1; {' '.join(wire)} #1; #1 {clock} = 1; #1 {clock} = 0; end"]
    L += [f"        i_{n} = {inactive_value(n)};" for n in RESETS]
    L += [f"        #1; {' '.join(wire)} #1; #1 {clock} = 1; #1 {clock} = 0;",
          '      end',
          "      else begin",
          '        r = $fscanf(fi, "%d %d %h", n, ui, uv);']
    L += [f'        r = $fscanf(fi, "%h", n_{n});' for n in ins]
    L += ["        k = 0; reached = 0;",
          "        while (k < n && !reached && !exh) begin",
          f"          if (rows >= {EDGE_BUDGET}) exh = 1;",
          "          else begin"]
    L += [f"            i_{n} = n_{n};" for n in ins]
    L += ["            #1;"]
    #: wired-AND: the design pulling its enable low pulls the line low (`_apply_bus`)
    L += [f"            if (o_{b['oen']} === 1'b0) i_{b['input']} = 1'b0;" for b in bus]
    L += ["            #1;",
          '            $fwrite(fo, "' + " ".join(["%h"] * len(outs)) + '\\n", ' + ", ".join(f"o_{n}" for n in outs) + ");",
          "            if (ui >= 0 && outv(ui) === uv) reached = 1;",
          f"            #1 {clock} = 1; #1 {clock} = 0; rows = rows + 1; k = k + 1;",
          "          end", "        end", "      end", "    end",
          "    $fclose(fo); $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


def designs():
    d = {"golden": [task / f"{mod}.v"]}
    for r in runs:
        for k in (1, 2, 3):
            f = E / r / "ablation" / mod / f"gen{k}" / "rtl_deliverable.sv"
            if f.is_file():
                d[f"{r}.gen{k}"] = [f]
        ed = E / r / "editor" / mod
        if (ed / "rtl_generated.sv").is_file():
            contract = json.loads((EQ / "corpora" / r / mod / "contract.json").read_text())
            gen = (ed / "rtl_generated.sv").read_text()
            w = EQ / "designs" / r / mod
            w.mkdir(parents=True, exist_ok=True)
            (w / "r0.sv").write_text(deliverable(gen, contract) or gen)
            d[f"{r}.r0"] = [w / "r0.sv"]
        if (ed / "rtl_deliverable.sv").is_file():
            d[f"{r}.final"] = [ed / "rtl_deliverable.sv"]
        #: The checks-only feedback rerun (`CHECKS-FEEDBACK.md`): `cfc` and `cfm` repair one start
        #: under checks-only and model feedback; `cfg` is byte_ctrl's start, generated with its child.
        for tag, key in CF_TAGS.items():
            f = E / r / f"editor-{tag}" / mod / "rtl_deliverable.sv"
            if f.is_file():
                d[f"{r}.{key}"] = [f]
    return d


def main():
    out = EQ / "cl_out" / mod
    out.mkdir(parents=True, exist_ok=True)
    work = EQ / "cl_work" / mod
    work.mkdir(parents=True, exist_ok=True)
    (work / "tb.v").write_text(tb())
    tps_of = {}
    for r in runs:
        prog = program(r)
        s = json.loads((EQ / "corpora" / r / mod / "stimulus.json").read_text())
        stim = s["testpoints"] if isinstance(s, dict) else s
        tps_of[r] = sorted(t["tp_uid"] for t in stim if t.get("stimulus_steps"))
        assert prog.read_text().count("\n0\n") + 1 == len(tps_of[r])
    only = set(sys.argv[2:])
    for name, files in designs().items():
        if only and name not in only:
            continue
        have = {m for f in files for m in re.findall(r"^\s*module\s+(\w+)", Path(f).read_text(), re.M)}
        vvp = work / f"{name}.vvp"
        cmd = ["iverilog", "-g2012", "-s", "tb", "-o", str(vvp), f"-I{task}", f"-I{task.parent}",
               str(work / "tb.v"), *map(str, files), *(str(k) for k in kids if k.stem not in have)]
        c = subprocess.run(cmd, capture_output=True, text=True)
        if c.returncode:
            (out / f"{name}.json").write_text(json.dumps({"compile_error": (c.stderr or c.stdout)[-2000:]}))
            print(f"{mod} {name}: COMPILE ERROR", flush=True)
            continue
        res = {}
        for r in runs:
            o = work / f"{name}.{r}.out"
            p = subprocess.run(["vvp", "-n", str(vvp), f"+in={program(r)}", f"+out={o}"],
                               capture_output=True, text=True, timeout=3600)
            if not o.is_file():
                res[r] = {"run_error": (p.stderr or p.stdout)[-1500:]}
                print(f"{mod} {name}: RUN ERROR on {r}", flush=True)
                continue
            per, cur = {tp: [] for tp in tps_of[r]}, -1
            for line in o.read_text().splitlines():
                if line == "#":
                    cur += 1
                    continue
                per[tps_of[r][cur]].append(line.split())
            res[r] = per
            o.unlink()
        vvp.unlink(missing_ok=True)
        (out / f"{name}.json").write_text(json.dumps(res))
        print(f"{mod} {name}: ok ({', '.join(f'{r}:{sum(len(v) for v in res[r].values())}' for r in runs if isinstance(res[r], dict) and 'run_error' not in res[r])} edges)", flush=True)


main()
