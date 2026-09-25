"""Golden as a DIAGNOSTIC: the five checks that convict a known-good design.

Golden RTL says WHERE to look. It never says what to write -- every repair here
is justified by the requirement's own sentence, and one repair is applied even
though it does not clear the conviction, because the thing it fixes was wrong
independently of any verdict.

These are HAND repairs, written to assemble a quantified instrument for the RTL
editor experiment. They are not a pipeline capability and nothing here claims
the author agent would have produced them.

  REQ-0117  REPAIRED, CLEARS.  The normalized `until` closed the window on
            scl_oen==0. The requirement puts the release "as the WRITE bit
            enters its stable HIGH phase", and scl_oen==0 is that same bit's
            LOW phase, which comes first -- so the window shut before the
            obligation could be owed. Measured on golden TP-0268: window opens
            at edge 120 with scl_oen already 1, closes at 128, and golden
            releases at 133. Closing on cmd_ack instead: both testpoints pass.

  REQ-0020  DROPPED, NOT_ASSERTABLE.  Its whole spec span is a port-table
            gloss -- "ena: Core enable signal. It gates normal timing/filter
            operation." Normalization turned that into an expectation the spec
            never states (cmd_ack must not pulse; busy, dout, scl_oen, sda_oen
            must hold). The design does the opposite ON PURPOSE: `!ena` forces
            `cnt <= clk_cnt; clk_en <= 1'b1`, so with ena low the bit FSM
            advances EVERY clock, and busy/dout are not gated by ena at all.
            Measured: golden pulses cmd_ack at edge 72 inside the window that
            opened at 66. The sentence has no falsifiable consequence at the
            boundary, which is what NOT_ASSERTABLE is for; this run's
            assertability step was offered it and kept it.

  REQ-0006  REPAIRED, STILL CONVICTS -- and applied anyway.  "an active
            (non-NOP) command" was normalized as `cmd: 1`, which is
            I2C_CMD_START: the one command during which the controller drives
            SDA low itself, so "the controller expects SDA to be high" is
            definitionally false there. Only a WRITE transmits din. cmd 1 -> 4
            is a strictly more faithful transcription and it is the exact
            defect the port-encoding work exists to prevent, so it is applied.
            It does not clear the conviction: it moves it from TP-0299 to
            TP-0014, into the residue below.

THE RESIDUE, and why it is not repaired here. REQ-0006, REQ-0030 and REQ-0095
are ONE cause: each anchors on a raw input edge whose consequence the design
produces about six clocks later, through cSDA -> fSDA -> sSDA -> dSDA ->
sto_condition -> al, by which time the window has closed on cmd_ack.

  REQ-0006  golden TP-0014: sda_i falls at edge 190, cmd_ack at 191, al at 196.
  REQ-0030  golden TP-0073: sda_i rises at edge 826, cmd_ack at 828; busy falls
            at 832, which is the filtered STOP arriving after the command had
            already completed -- so golden is right not to call it arbitration
            loss during an active command.
  REQ-0095  golden TP-0223: window opens at edge 0, cmd_ack at 4, al at 9.

Every requirement says "the FILTERED SDA" or "the filtered bus". The filter
exists in the specification's words and has no port. Closing these windows late
enough to admit it would mean encoding a depth the specification never states,
read off the design -- which is calibrating the instrument to the thing it is
supposed to judge. They stay in the suite, convicting, and are reported.
"""

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"
HERE = Path(__file__).parent

#: The best available check for every requirement, in overwrite order: the
#: frozen 110, then the 43 over-strict re-authored, then the 23 the new tools
#: reach. A requirement a later run REJECTED drops out rather than silently
#: keeping the older check.
def base_suite() -> dict:
    frozen = {o["req_uid"]: o for o in json.load(
        open("/home/user/runs/c1-i2c/specflow/oracles.json"))["oracles"]}
    full43 = {o["req_uid"]: o for o in json.load(
        open(A / "full43/run/specflow/oracles.json"))["oracles"]}
    new = {o["req_uid"]: o for o in json.load(
        open(A / "affected23/run/specflow/oracles.json"))["oracles"]}
    over = set(json.load(open(A / "over_strict.json"))["over_strict"])
    sub = set(json.load(open(A / "affected.json"))["over_strict"])
    mix = {**{u: o for u, o in frozen.items() if u not in over},
           **{u: o for u, o in full43.items() if u in over}}
    mix.update({u: o for u, o in new.items() if u in sub})
    for u in sub:
        if u not in new:
            mix.pop(u, None)
    return mix


DROPPED = {"REQ-0020": "NOT_ASSERTABLE: the spec span is a port-table gloss "
                       "and its expectation is not in the specification"}
RESIDUE = ("REQ-0006", "REQ-0030", "REQ-0095")


def repaired_suite() -> dict:
    mix = base_suite()
    patches = json.load(open(HERE / "repair5-checks.json"))
    for u, blob in patches.items():
        mix[u] = {**mix[u], "source": blob["source"], "clause": blob["clause"]}
    for u in DROPPED:
        mix.pop(u, None)
    return mix


def build(mix):
    return [RequirementOracle(**{k: o[k] for k in
            ("req_uid", "clause", "source", "tp_uids") if k in o})
            for _, o in sorted(mix.items())]


def main() -> int:
    traces = {"golden": load_traces(S / "rtl_golden2/suite/results"),
              "candidate": load_traces(S / "rtl_cand2/suite/results")}
    traces["golden"].update(load_traces(A / "staged_golden/suite/results"))

    arms = {"BEFORE": base_suite(), "AFTER": repaired_suite()}
    res, sizes = {}, {}
    print(f"{'suite':<9}{'n':>4}{'pass':>6}{'convict':>9}{'silent':>8}"
          f"{'coverage':>10}{'pass rate':>11}   rtl")
    for label, mix in arms.items():
        sizes[label] = n = len(mix)
        for rtl in ("golden", "candidate"):
            d = {x.req_uid: x.ok for x in decide_rtl(build(mix), traces[rtl],
                                                     json.load(open(A / "full43/run/contract.json")))}
            res[(label, rtl)] = d
            c = collections.Counter(d.values())
            print(f"{label if rtl == 'golden' else '':<9}{n:>4}{c[True]:>6}"
                  f"{c[False]:>9}{c[None]:>8}{100*(n-c[None])/n:>9.0f}%"
                  f"{100*(n-c[False])/n:>10.0f}%   {rtl}")
        print()

    print(f"{'suite':<9}{'discriminating':>15}{'inverted':>10}{'separation':>12}")
    for label in arms:
        g, c = res[(label, "golden")], res[(label, "candidate")]
        disc = sorted(u for u in g if g[u] is True and c.get(u) is False)
        inv = sorted(u for u in g if g[u] is False and c.get(u) is True)
        print(f"{label:<9}{len(disc):>15}{len(inv):>10}{len(disc)-len(inv):>+12}")

    g = res[("AFTER", "golden")]
    still = sorted(u for u in g if g[u] is False)
    print(f"\nconvicting golden AFTER: {len(still)}  -> {' '.join(still)}")
    print("  all of them are the filtered-bus latency residue"
          if set(still) == set(RESIDUE) else "  UNEXPECTED: not the known residue")
    json.dump({"sizes": sizes, "dropped": DROPPED, "residue": list(RESIDUE),
               "verdicts": {f"{k[0]}/{k[1]}": v for k, v in res.items()}},
              open(HERE / "repair5.json", "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
