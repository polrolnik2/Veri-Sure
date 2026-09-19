"""Two runs of normalization on identical inputs. How much of it repeats?

Every span, audit and blindness figure in this evidence directory is computed
on ONE sample of the normalized forms. Nothing had measured how much that
sample varies, so nothing knew whether a difference between two runs was a
result or a draw. Two full runs of the E2 driver over the same 115
requirements, same contract, same direct-pass inputs, are kept as
`normalized-all-sample1.json` and `-sample2.json`.

Zero model calls -- this reads the two artifacts.
"""
import json

A = json.load(open("docs/evidence/e3/normalized-all-sample1.json"))
B = json.load(open("docs/evidence/e3/normalized-all-sample2.json"))
FIELDS = ("activation", "expectation", "observable", "observed_via")


def unroutable(d):
    return {u for u, n in d.items()
            if not (n.get("observable") or []) and not n.get("observed_via")}


def same(x, y):
    return json.dumps(x, sort_keys=True) == json.dumps(y, sort_keys=True)


print(f"forms: {len(A)} and {len(B)}")
ua, ub = unroutable(A), unroutable(B)
print("\nTHE ROUTING DECISION -- what actually gates downstream")
print(f"  unroutable: {len(ua)} vs {len(ub)}; they disagree on "
      f"{len(ua ^ ub)} requirement(s): {sorted(ua ^ ub)}")

per = {f: 0 for f in FIELDS}
any_diff = 0
for u in A:
    d = [f for f in FIELDS if not same(A[u].get(f), B.get(u, {}).get(f))]
    if d:
        any_diff += 1
        for f in d:
            per[f] += 1
print("\nTHE TEXT -- what the author reads")
print(f"  forms differing in any of {FIELDS}: {any_diff} of {len(A)}"
      f" = {100 * any_diff / len(A):.0f}%")
for f, c in per.items():
    print(f"    {f:14} {c:3d} = {100 * c / len(A):.0f}%")

#: THE SPLIT IS THE FINDING. A restatement that changes the wording and keeps
#: the port is a different PROMPT and the same DECISION. `observable` and the
#: unroutable set are the fields anything downstream branches on, and they are
#: the two that barely move.
print(f"\n  text varies on {100 * any_diff / len(A):.0f}% of forms; "
      f"`observable` on {100 * per['observable'] / len(A):.0f}%; "
      f"the unroutable set on {100 * len(ua ^ ub) / len(A):.1f}%")
