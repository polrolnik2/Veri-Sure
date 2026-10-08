"""The quantified instrument, on both stimulus renderings. No model calls.

This is the set the RTL editor is handed, and the numbers it will be judged
against. Everything here comes from four `loop_run.py` runs -- golden and the
ChipVerilog codex t1 candidate, each with the stimulus as the pipeline wrote it
and again with every step held 60 edges.

                     golden                    candidate
                FAIL UNCOV pass  rate     FAIL UNCOV pass  rate   disc  inv  sep
  as written      12    27   51   87%       21    25   44   77%     13    7  +6
  hold=60          3    27   60   97%       19    25   46   79%     15    1  +14

Coverage is 70% on golden and 72% on the candidate under BOTH renderings --
pacing does not change which checks fire, only what they see. Everything else
moves, and it moves the right way: the paced run gives golden a 97% pass rate
and lifts separation from +6 to +14.

THE PACED COLUMN IS THE HONEST INSTRUMENT and it is not clean. Of the 19 checks
the candidate fails:

  15  the candidate fails and golden passes -- the real repair targets
   2  REQ-0006 and REQ-0095 fail BOTH, so they are false demands: an editor
      told to fix them would be asked to change a design that is right
   2  REQ-0029 and REQ-0096 fire on the candidate and NEVER fire on golden.
      Not counted as discriminating, because golden returned no verdict to
      discriminate against -- but a check reaching a state only the candidate
      enters is evidence about the candidate, not noise

and one check, REQ-0030, convicts golden alone.

So the editor is being handed 19 findings of which 15 are sound, 2 are wrong,
and 2 are unjudged. That ratio is the thing to watch: the plan's §12 risk is
that a debug loop pointed at RTL will faithfully "repair" a correct design
toward whatever its instrument demands, and 2 of 19 is the current rate at
which this instrument would ask it to.

WHAT IS STILL NOT MEASURED. Every number here is one candidate on one design.
Separation +14 says this set distinguishes THIS pair; it does not say the set
would distinguish a different candidate, and nothing here bounds how much of
the 15 is one shared root cause in the candidate rather than 15 defects.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
N = 90
ARMS = {
    "as written": ("pacing-golden-aswritten.json", "pacing-candidate-aswritten.json"),
    "hold=60": ("pacing-golden-hold60.json", "pacing-candidate-hold60.json"),
}


def _load(name: str) -> tuple[set, set, int]:
    d = json.loads((HERE / name).read_text())
    return ({r["req_uid"] for r in d["failing"]}, set(d["uncovered"]),
            int(d["passing_count"]))


def main() -> int:
    print(f"{'':14}{'golden':>26}{'candidate':>28}{'':>18}")
    print(f"{'':14}{'FAIL':>6}{'UNCOV':>6}{'pass':>6}{'rate':>8}"
          f"{'FAIL':>7}{'UNCOV':>6}{'pass':>6}{'rate':>8}"
          f"{'disc':>7}{'inv':>5}{'sep':>6}")
    detail = {}
    for label, (gp, cp) in ARMS.items():
        gf, gu, gpass = _load(gp)
        cf, cu, cpass = _load(cp)
        disc = sorted(cf - gf - gu)
        inv = sorted(gf - cf - cu)
        detail[label] = {"discriminating": disc, "inverted": inv,
                         "both_fail": sorted(gf & cf),
                         "candidate_only_evidence": sorted(cf & gu)}
        print(f"{label:14}{len(gf):>6}{len(gu):>6}{gpass:>6}"
              f"{100 * (N - len(gf)) / N:>7.0f}%"
              f"{len(cf):>7}{len(cu):>6}{cpass:>6}"
              f"{100 * (N - len(cf)) / N:>7.0f}%"
              f"{len(disc):>7}{len(inv):>5}{len(disc) - len(inv):>+6}")

    d = detail["hold=60"]
    print("\nUNDER THE PACED STIMULUS -- what the editor is handed")
    print(f"  {len(d['discriminating']):>2} sound targets:  "
          + " ".join(d["discriminating"]))
    print(f"  {len(d['both_fail']):>2} FALSE DEMANDS (fail golden too): "
          + " ".join(d["both_fail"]))
    print(f"  {len(d['candidate_only_evidence']):>2} fire only on the candidate "
          f"(golden never reached them): "
          + " ".join(d["candidate_only_evidence"]))
    print(f"  {len(d['inverted']):>2} convict golden alone: " + " ".join(d["inverted"]))
    json.dump(detail, open(HERE / "instrument.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
