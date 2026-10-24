"""fusion_offline.py -- can the heterogeneous latch signals be FUSED, rather than one chosen?

Each audited commit (LATCH-OFFLINE.json, -cf-model.json: 166 commits, both arms) carries golden-free
signals: the change in passing shipped requirements (P), in agreement with the fresh samples (C),
and in agreement with the run's reference model (R), plus the counts of requirements reported
broken or silenced. Golden's net verdict (cells fixed - broken) is the label, used only to score.

1. LABEL MODEL (no golden). The triplet method of weak supervision: for three voters with
   conditionally independent errors, E[v_i v_j] = (2a_i - 1)(2a_j - 1), so each voter's accuracy
   a_i follows from the pairwise agreements alone. Estimated accuracies are set beside the true
   ones, and each observed pairwise moment beside the one independence predicts from the true
   accuracies, with its standard error.
2. LEARNED VERIFIER (golden in training only). Logistic regression on the golden-free features,
   scored leaving one MODULE out: the weights are fitted on three modules and judged on the fourth,
   so every score is on a module the model never saw. Against the consensus latch as built
   (agreement rises >= 0.1 pt, or passing rises and agreement falls < 0.5 pt) and the current latch.
-> docs/evidence/e7/FUSION-OFFLINE.json, tables on stdout.
"""

import json
import math
from pathlib import Path

import numpy as np

E = Path(__file__).resolve().parents[1] / "e7"
rows = []
for arm, f in (("checks", "LATCH-OFFLINE.json"), ("model", "LATCH-OFFLINE-cf-model.json")):
    for r in json.loads((E / f).read_text())["rows"]:
        if r["golden_net"] != 0:
            rows.append({**r, "arm": arm, "module": r["job"].split()[0], "y": 1 if r["golden_net"] > 0 else -1})
y = np.array([r["y"] for r in rows])


def sgn(v, eps=1e-12):
    return 0 if abs(v) <= eps else (1 if v > 0 else -1)


V = {"P (passing requirements)": np.array([sgn(r["dpass"]) for r in rows]),
     "C (agreement with fresh samples)": np.array([sgn(r["dcons"]) for r in rows]),
     "R (agreement with reference model)": np.array([sgn(r["dref"]) for r in rows])}
out = {"n": len(rows), "label_model": {}, "verifier": {}}

print(f"## 1. Label model: accuracy estimated without golden vs true ({len(rows)} commits golden scores as better or worse)\n")
names = list(V)
m = {}
for i in names:
    for j in names:
        if i < j:
            both = (V[i] != 0) & (V[j] != 0)
            m[(i, j)] = m[(j, i)] = float(np.mean(V[i][both] * V[j][both])) if both.any() else 0.0
print("| voter | votes | true accuracy | triplet estimate |")
print("|---|---|---|---|")
for i in names:
    j, k = [n for n in names if n != i]
    prod = m[(i, j)] * m[(i, k)] / m[(j, k)] if abs(m[(j, k)]) > 1e-9 else float("nan")
    est = (1 + math.copysign(math.sqrt(abs(prod)), m[(i, j)] if abs(m[(i, j)]) > 0 else 1)) / 2 \
        if prod == prod else float("nan")
    vote = V[i] != 0
    true = float(np.mean(V[i][vote] == y[vote]))
    out["label_model"][i] = {"votes": int(vote.sum()), "true": true, "estimate": est}
    print(f"| {i} | {int(vote.sum())} | {100 * true:.0f}% | {100 * est:.0f}% |")
print("\nPairwise moments E[v_i v_j]: observed, and predicted by independence from the true accuracies:\n")
for i in names:
    for j in names:
        if i < j:
            both = (V[i] != 0) & (V[j] != 0)
            pred_ij = float(np.mean(V[i][both] * y[both]) * np.mean(V[j][both] * y[both]))
            se = math.sqrt((1 - m[(i, j)] ** 2) / both.sum())
            out["label_model"][f"moment {i[:1]}-{j[:1]}"] = {"n": int(both.sum()), "observed": m[(i, j)],
                                                             "independent": pred_ij, "se": se}
            print(f"- {i[:1]}{j[:1]}: {m[(i, j)]:+.2f} observed, {pred_ij:+.2f} if independent "
                  f"(n {int(both.sum())}, se {se:.2f})")
err = {n: np.where(V[n] != 0, (V[n] != y).astype(float), np.nan) for n in names}
print("\nCorrelation of the voters' ERRORS (both voting); independence would be ~0:\n")
for i in names:
    for j in names:
        if i < j:
            both = ~np.isnan(err[i]) & ~np.isnan(err[j])
            c = float(np.corrcoef(err[i][both], err[j][both])[0, 1]) if both.sum() > 2 else float("nan")
            out["label_model"][f"error corr {i[:1]}-{j[:1]}"] = c
            print(f"- {i[:1]} and {j[:1]}: {c:+.2f}")


def feats(r):
    return [r["dpass"] / 10, 100 * r["dcons"], 100 * r["dref"], float(r["broken"]), float(r["silenced"]),
            float(r["dpass"] > 0), float(r["dcons"] >= 0.001)]


FEATS = ["passing change /10", "agreement change (pt)", "ref-model change (pt)", "reported broken",
         "silenced", "passing rose", "agreement rose >= 0.1 pt"]


def fit(X, t, lam=1.0, it=200):
    Xb = np.hstack([X, np.ones((len(X), 1))])
    w = np.zeros(Xb.shape[1])
    for _ in range(it):  # Newton's method, L2 on the weights (not the bias)
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ (p - t) + lam * np.r_[w[:-1], 0]
        H = (Xb.T * (p * (1 - p))) @ Xb + lam * np.diag(np.r_[np.ones(len(w) - 1), 0])
        w -= np.linalg.solve(H, g)
    return w


def auc(score, lab):
    pos, neg = score[lab == 1], score[lab == -1]
    if not len(pos) or not len(neg):
        return float("nan")
    return float(np.mean([(p > q) + 0.5 * (p == q) for p in pos for q in neg]))


X = np.array([feats(r) for r in rows])
mu, sd = X.mean(0), X.std(0) + 1e-9
Xs = (X - mu) / sd
t = (y == 1).astype(float)
pred = np.zeros(len(rows))
for mod in sorted({r["module"] for r in rows}):
    test = np.array([r["module"] == mod for r in rows])
    w = fit(Xs[~test], t[~test])
    pred[test] = 1 / (1 + np.exp(-(np.hstack([Xs[test], np.ones((test.sum(), 1))]) @ w)))
w_all = fit(Xs, t)
out["verifier"]["weights_all_data"] = dict(zip(FEATS + ["bias"], map(float, w_all)))

RULES = {
    "current latch": lambda r, p: r["latched"],
    "consensus latch as built (margin 0.1, tolerance 0.5)":
        lambda r, p: r["dcons"] >= 0.001 or (r["dpass"] > 0 and r["dcons"] > -0.005),
    "learned verifier (p > 0.5, module held out)": lambda r, p: p > 0.5,
}
print("\n## 2. Learned verifier, each module scored with weights fitted on the other three\n")
print("| rule | accepted | accepted better / worse | rejected better / worse | gains / losses kept (points of edges) |")
print("|---|---|---|---|---|")
for name, fn in RULES.items():
    acc = np.array([fn(r, p) for r, p in zip(rows, pred)])
    ab, aw = int(((y == 1) & acc).sum()), int(((y == -1) & acc).sum())
    rb, rw = int(((y == 1) & ~acc).sum()), int(((y == -1) & ~acc).sum())
    gains = 100 * sum(r["dedge"] for r, a in zip(rows, acc) if a and r["dedge"] > 0)
    losses = 100 * sum(r["dedge"] for r, a in zip(rows, acc) if a and r["dedge"] < 0)
    out["verifier"][name] = {"acc_better": ab, "acc_worse": aw, "rej_better": rb, "rej_worse": rw,
                             "gains": gains, "losses": losses}
    print(f"| {name} | {int(acc.sum())} | {ab} / {aw} | {rb} / {rw} | {gains:+.1f} / {losses:+.1f} |")
print("\nRanking quality (AUC, 0.5 = chance), every commit scored out of its own module:\n")
for lab, s in (("passing change", np.array([r["dpass"] for r in rows], float)),
               ("agreement change", np.array([r["dcons"] for r in rows])),
               ("ref-model change", np.array([r["dref"] for r in rows])),
               ("learned verifier", pred)):
    a = auc(s, y)
    out["verifier"][f"auc {lab}"] = a
    print(f"- {lab}: {a:.2f}")
print("\nWeights fitted on all modules (standardised features):",
      ", ".join(f"{n} {v:+.2f}" for n, v in zip(FEATS + ["bias"], w_all)))
(E / "FUSION-OFFLINE.json").write_text(json.dumps(out, indent=1) + "\n")
