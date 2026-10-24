"""byte_child_drive.py -- in byte_ctrl's arbitration excerpts, what makes the two candidates' outputs differ?

Both candidates instantiate the benchmark's own i2c_master_bit_ctrl (the designs define only the
byte controller; the simulator links the child). Every child input is a top-level input passed
through, except `cmd` and `din`, which the byte controller's FSM drives. So an output difference
on the child's pins (SCL/SDA, busy, al) can only start as a difference in the cmd / din sequence
fed to the child; the byte controller's own outputs (cmd_ack, ack_out, dout) come from its FSM.

This simulates both candidates of every byte_ctrl commit ARBITRATION-OFFLINE asked about, with
the child's ports probed, and reports per excerpt: which outputs differ (child-driven or
FSM-driven), the row where the child's cmd / din first differ against the row where the outputs
first differ, and the commands each candidate issued in between. Counts and command names only.
"""

import contextlib
import io
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = str(HERE / "arbitration_offline.py")
SRC = Path(P).read_text().split('if os.environ.get("ARB_DRY"):')[0]
os.environ.setdefault("ARB_VARIANT", "3")
g = {"__file__": P, "__name__": "arb"}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(SRC, P, "exec"), g)  # targets and episodes; no calls
EQ, FA, MOD = g["EQ"], g["FA"], "i2c_master_byte_ctrl"
CHILD_OUT = {"i2c_busy", "i2c_al", "scl_o", "scl_oen", "sda_o", "sda_oen"}
CMD = {"0": "NOP", "1": "START", "2": "STOP", "4": "WRITE", "8": "READ"}  # I2C_CMD_* (i2c_master_defines.v)
WORK = EQ / "byte_child_drive"
WORK.mkdir(parents=True, exist_ok=True)
task = next(p.parent for p in FA["DES"].rglob("description.txt") if p.parent.name == MOD)
kids = [str(k) for k in FA["child_sources"](FA["submodules"](task, MOD))]
tb = (EQ / "work" / MOD / "tb.v").read_text()


def probed(rtl, tag):
    """Per row: the child's cmd, din, cmd_ack, dout, as the bench samples the outputs."""
    # the byte controller's own nets on the child's ports: iverilog's elaborator asserts on a
    # hierarchical reference into the linked child instance
    conns = re.search(r"\bi2c_master_bit_ctrl\b\s*(?:#\s*\(.*?\)\s*)?\w+\s*\((.*?)\);", rtl, re.S).group(1)
    net = dict(re.findall(r"\.(\w+)\s*\(\s*(\w+)\s*\)", conns))
    b = tb.replace("  integer fi,", f"  wire [3:0] p_cmd = dut.{net['cmd']};\n  wire p_din = dut.{net['din']};\n"
                   f"  wire p_ack = dut.{net['cmd_ack']};\n  wire p_dout = dut.{net['dout']};\n  integer fi,", 1)
    b = b.replace('$fwrite(fo, "%h %h %h %h %h %h %h %h %h\\n",',
                  '$fwrite(fo, "%h %h %h %h | ", p_cmd, p_din, p_ack, p_dout);\n'
                  '        $fwrite(fo, "%h %h %h %h %h %h %h %h %h\\n",', 1)
    assert b.count("p_cmd") == 2, "bench layout changed"
    (WORK / f"{tag}.tb.v").write_text(b)
    (WORK / f"{tag}.sv").write_text(rtl)
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(WORK / f"{tag}.vvp"), f"-I{task}", f"-I{task.parent}",
                    str(WORK / f"{tag}.tb.v"), str(WORK / f"{tag}.sv"), *kids], check=True, capture_output=True)
    return WORK / f"{tag}.vvp"


def run(vvp, run_):
    tps = sorted(json.loads((EQ / "stim" / run_ / f"{MOD}.json").read_text())["tps"])
    o = vvp.with_suffix(".out")
    subprocess.run(["vvp", "-n", str(vvp), f"+in={EQ / 'stimtxt' / run_ / f'{MOD}.txt'}", f"+out={o}"],
                   check=True, capture_output=True, timeout=3600)
    per, cur = {tp: [] for tp in tps}, -1
    for line in o.read_text().splitlines():
        if line == "#":
            cur += 1
        else:
            child, _ = line.split(" | ")
            per[tps[cur]].append(child.split())
    o.unlink()
    return per


outs = json.loads((EQ / "stim" / "luna12" / f"{MOD}.json").read_text())["outputs"]
kind, lead, drive = Counter(), [], Counter()
for n, r in enumerate(x for x in g["rows"] if x["mod"] == MOD):
    t = next(t for t in g["targets"] if t["source"] == r["source"])
    ca = run(probed(t["before"], f"c{n}a"), r["run"])
    cb = run(probed(t["after"], f"c{n}b"), r["run"])
    for e in r["asked"]:
        a, b = r["_A"][r["run"]][e["tp"]], r["_B"][r["run"]][e["tp"]]
        rows = range(e["first"], e["end"] + 1)
        ports = {outs[k] for i in rows for k in range(len(a[i])) if a[i][k] != b[i][k]}
        kind["child-driven only" if ports <= CHILD_OUT else "FSM-driven only" if not ports & CHILD_OUT
             else "both"] += 1
        x, y = ca[e["tp"]], cb[e["tp"]]
        cmd_first = next((i for i in range(min(len(x), len(y))) if x[i][:2] != y[i][:2]), None)
        if cmd_first is None:
            drive["child cmd / din identical throughout"] += 1
            continue
        lead.append(e["first"] - cmd_first)
        field = "cmd" if x[cmd_first][0] != y[cmd_first][0] else "din"
        drive[f"first difference on the child's {field}"] += 1
        seq = [(CMD.get(x[i][0], x[i][0]), CMD.get(y[i][0], y[i][0])) for i in range(cmd_first, e["first"] + 1)]
        before = [s for s, _ in seq]
        after = [s for _, s in seq]
        dedup = lambda v: [c for i, c in enumerate(v) if i == 0 or c != v[i - 1]]  # noqa: E731
        drive[f"before {'>'.join(dedup(before))[:40]} | after {'>'.join(dedup(after))[:40]}"] += 1
print(f"byte_ctrl excerpts: {sum(kind.values())}; outputs that differ: {dict(kind)}")
print(f"rows from the child's cmd / din diverging to the outputs diverging: "
      f"{sorted(lead)} (median {sorted(lead)[len(lead) // 2] if lead else None})")
print("commands fed to the child from its divergence to the outputs', before | after (repeats merged):")
for k, v in drive.most_common():
    print(f"  {v} x {k}")
