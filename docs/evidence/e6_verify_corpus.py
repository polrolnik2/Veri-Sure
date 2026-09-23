"""Check a packed corpus is intact and re-scorable, then re-score it.

    e6_verify_corpus.py <corpus-dir> [<golden-suite-dir>]

**A CORPUS NOBODY HAS RE-RUN IS A CLAIM, NOT AN ARTIFACT.** Three runs on this
branch (`o1`..`o3`) look re-scorable by uid and are not, because their contract
was never stored; two more died with a container. This asks, of a packed
corpus, the three questions that decide whether it can be used at all:

  1. Is every file present and byte-identical to what was packed?
  2. Do the population's `PROBE_PORTS` match the contract's probe entries? A
     mismatch is silent at score time -- every probe reads unavailable and
     blindness reaches ~100% by construction.
  3. **Was the golden suite driven by THIS corpus's stimulus?** `decide_rtl`
     looks a trace up by `tp_uid`, and every i2c run there has ever been mints
     TP-0069 while regenerating the stimulus behind it, so pointing one run's
     checks at another run's traces does not fail -- the lookup succeeds and
     answers a different question. `stimulus_digest` over this corpus's own
     `stimulus_steps` reproduces the digest its traces carry, 482 of 482, so
     this is checkable offline, and it is checked before any audit figure is
     printed rather than after.
  4. Does it still score, and how does that compare to what the run recorded?

Answer 3 is EXPECTED TO DIFFER and that is not a failure. The boundary fix
alone moved `full7`'s blindness from 0.2450 to 0.2896, because the recorded
figure predates it. A re-score measures today's code against a frozen corpus,
which is the point of freezing one.

With a golden suite directory, the audit column is taken from an RTL control
rather than the Python transliteration -- see `e6_rescore_rtl_control.py` for
why that changes the denominator from 14 checks to 37.

Golden is RUN and never read.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.scorecard import score  # noqa: E402
from specflow.tb.runtime import stimulus_digest  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_integrity(root: Path, manifest: dict) -> list[str]:
    bad = []
    for name, rec in sorted((manifest.get("files") or {}).items()):
        f = root / name
        if not f.is_file():
            bad.append(f"{name}: MISSING")
        elif sha256(f) != rec["sha256"]:
            bad.append(f"{name}: DIGEST MISMATCH")
    return bad


def check_probes(root: Path) -> tuple[bool, list[str], list[str]]:
    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    cp = set(declared_probes(contract))
    pp: set = set()
    for m in sorted((root / "population").glob("*.py")):
        hit = re.search(r"PROBE_PORTS\s*=\s*(\[[^\]]*\])",
                        m.read_text(encoding="utf-8"))
        if hit:
            pp |= set(eval(hit.group(1)))
    return pp == cp, sorted(pp - cp), sorted(cp - pp)


def check_stimulus(root: Path, gold: Path) -> tuple[int, int, list[str]]:
    """`(matched, mismatched, foreign)` between a golden suite and this corpus.

    **THIS IS THE `o1`..`o3` FAILURE ONE LEVEL DOWN.** Those three shared every
    `req_uid` and `tp_uid` with `full2` and declared a different contract. A
    golden suite shares every `tp_uid` with every other run of the same module
    and can have been driven by entirely different steps -- measured elsewhere
    on this branch: "322 shared uids, ZERO with identical step lists; one
    drives a reset in 158 testpoints and the other in none."
    """
    _s = json.loads((root / "stimulus.json").read_text())
    stim = _s["testpoints"] if isinstance(_s, dict) else _s
    want = {s["tp_uid"]: stimulus_digest(s.get("stimulus_steps") or [])
            for s in stim}
    matched = mismatched = 0
    foreign: list[str] = []
    for f in sorted((gold / "suite" / "results").glob("*.trace.json")):
        t = json.loads(f.read_text())
        uid, got = t.get("tp_uid"), t.get("stimulus_digest")
        if uid not in want:
            foreign.append(str(uid))
        elif got is None:
            #: A trace predating `stimulus_digest` cannot answer, and silently
            #: counting it as a match is exactly the assumption this exists to
            #: refuse.
            mismatched += 1
        elif got == want[uid]:
            matched += 1
        else:
            mismatched += 1
    return matched, mismatched, foreign


def main() -> int:
    root = Path(sys.argv[1])
    gold = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    print(f"corpus {manifest['name']}, packed {manifest['packed_at']}\n")

    bad = check_integrity(root, manifest)
    print(f"1. integrity      {len(manifest.get('files') or {})} file(s), "
          + ("ALL INTACT" if not bad else f"{len(bad)} PROBLEM(S)"))
    for b in bad:
        print(f"     {b}")
    if bad:
        return 1

    ok, extra, missing = check_probes(root)
    print(f"2. probe agreement {'OK' if ok else 'MISMATCH'}")
    if not ok:
        print(f"     only in population: {extra}")
        print(f"     only in contract  : {missing}")
        print("     -> this corpus CANNOT be scored: every probe would read "
              "unavailable and blindness would reach ~100% by construction")
        return 1

    if gold is not None:
        matched, mismatched, foreign = check_stimulus(root, gold)
        ok3 = mismatched == 0 and matched > 0
        print(f"3. golden suite   {'BELONGS TO THIS CORPUS' if ok3 else 'DOES NOT MATCH'}"
              f" -- {matched} trace(s) driven by this corpus's stimulus, "
              f"{mismatched} not, {len(foreign)} testpoint(s) it does not name")
        if not ok3:
            print("     -> REFUSING TO REPORT AN AUDIT COLUMN. decide_rtl looks "
                  "traces up by tp_uid, which\n        every run of this module "
                  "reuses, so scoring against these would succeed and\n        "
                  "answer a different question. Re-run the control under this "
                  "corpus's own\n        stimulus: e6_replay_corpus.py "
                  f"{root} <rtl.v> <out-dir>")
            return 1

    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    oracles = json.loads((root / "oracles.json").read_text())["oracles"]
    _n = json.loads((root / "normalized.json").read_text())
    normalized = _n["normalized"] if isinstance(_n, dict) else _n
    requirements = json.loads(
        (root / "requirements.json").read_text())["requirements"]
    _s = json.loads((root / "stimulus.json").read_text())
    stim = _s["testpoints"] if isinstance(_s, dict) else _s
    by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
    population = [p.read_text() for p in sorted((root / "population").glob("*.py"))]

    kw: dict = {}
    if gold is not None:
        traces = load_traces(gold / "suite" / "results")
        held = [RequirementOracle(
            req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
            clause=x.get("clause", ""), source=x["source"]) for x in oracles]
        v: dict = {}
        #: Step 3 above already refused a foreign suite; this arms
        #: `decide_rtl`'s own refusal as well, so the check holds even if this
        #: driver's step 3 is ever edited out.
        for r in decide_rtl(held, traces, contract, transactional=True,
                            stimulus_by_tp=by_tp):
            if not r.broken and r.ok is not None:
                v.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
        seen = {n for t in traces.values() for e in (t.get("edges") or [])
                for n, val in (e.get("dut") or {}).items() if val is not None}
        kw = {"audit_verdicts": v,
              "audit_absent": tuple(n for n in declared_probes(contract)
                                    if n not in seen)}

    card = score(oracles=oracles, normalized=normalized, stimulus_by_tp=by_tp,
                 contract=contract, population=population,
                 requirements=requirements, **kw)
    rec = manifest.get("recorded_scorecard") or {}
    src = "an RTL control" if gold is not None else "the packed control"
    print(f"\n{4 if gold is not None else 3}. re-score       against {src}\n")
    print(f"     {'column':11} {'recorded':>10} {'now':>10}")
    #: `audit` is None with no control -- "absent, not 0%", which the
    #: scorecard is deliberate about -- so neither side may be formatted as a
    #: float unconditionally.
    def fmt(v):
        return "         -" if v is None else f"{float(v):10.4f}"

    for key in ("span", "blindness", "audit"):
        print(f"     {key:11} {fmt(rec.get(key))} {fmt(getattr(card, key))}")
    print(f"     {'judged on':11} {str(rec.get('control_judges')):>10} "
          f"{card.control_judges:10d}")
    for n in card.notes:
        print(f"     note: {str(n)[:150]}")
    print("\n     A DIFFERENCE HERE IS NOT A FAILURE: the recorded figures were "
          "computed\n     by the code of the day, and a re-score measures "
          "today's against a frozen\n     corpus, which is what freezing one "
          "is for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
