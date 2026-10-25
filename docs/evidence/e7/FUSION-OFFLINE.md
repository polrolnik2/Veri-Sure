# Fusing the latch signals instead of choosing one

The latch has three golden-free signals for each commit:
- **P:** passing shipped requirements;
- **C:** agreement with the fresh samples;
- **R:** agreement with the run's reference model.

`LATCH-OFFLINE.md` chose C alone. This tests whether two standard ways of combining heterogeneous
noisy signals do better:
- **a label model,** which uses no golden;
- **a learned verifier,** which uses golden only in training and is scored on a module it never
  saw.

The data are the same audited commits: 166 from both arms, of which golden scores 125 as net
better or worse. Figures come from `e7_behaviour/fusion_offline.py` and are written to
`FUSION-OFFLINE.json`.

## 1. Label model (triplet method, no golden)

This is weak supervision's estimator. If three voters' errors are independent, the agreement of
each pair fixes each voter's accuracy.

| voter | votes | true accuracy | estimated without golden |
|---|---|---|---|
| P, passing requirements | 92 | 58% | 71% |
| C, agreement with fresh samples | 121 | **71%** | 54% |
| R, agreement with reference model | 111 | 41% | 27% |

**It ranks the voters wrongly:** it rates P above C. The reasons:

- **Only one voter carries signal.** C's 71% is the only accuracy clearly above chance. P is
  near chance, and R is below it, which the method cannot represent: it assumes every voter beats
  a coin.
- **The pairwise moments are within noise.** Each is about ±0.10 at n ≈ 90–110 (one standard
  error).

  | pair | observed E[vᵢvⱼ] | predicted if independent |
  |---|---|---|
  | P–R | −0.20 | −0.04 |
  | C–P | +0.03 | +0.06 |
  | C–R | +0.04 | −0.07 |

  The estimator divides one of these by another, so the noise dominates.
- **Errors are not detectably correlated.** The error correlations are −0.16, −0.03 and +0.12.
  Correlated errors are not why the method fails here. The cause is too few informative voters
  for the commit count.
- **Majority vote is worse than C alone:** 58% on the 115 commits where the vote is not tied.

## 2. Learned verifier (logistic regression, module held out)

The features are the three changes, the counts of requirements reported broken and silenced,
and two indicator features. The weights are fitted on three modules and scored on the fourth.

| rule | accepted | accepted better / worse | rejected better / worse | gains / losses kept, points of edges |
|---|---|---|---|---|
| current latch | 39 | 16 / 23 | 29 / 57 | +48.7 / −233.0 |
| consensus latch as built | 31 | **23 / 8** | 22 / 72 | +39.7 / −3.5 |
| learned verifier | 19 | 14 / 5 | 31 / 75 | +32.0 / −2.3 |

Ranking quality (AUC; 0.5 is chance):

| signal | AUC |
|---|---|
| passing change | 0.53 |
| **agreement change** | **0.80** |
| ref-model change | 0.42 |
| learned verifier | 0.69 |

- **The fitted weights are dominated by agreement.** The agreement change has a weight of +1.58
  in standardised units, and the agreement-rose indicator +0.61. Every other feature is at most
  0.28 in magnitude.
- **The verifier ranks worse than agreement alone.** The other features add noise that does not
  transfer across modules.
- **The verifier accepts fewer commits.** Its accepts are about as often net better as the
  consensus latch's (74% against 74%), but it keeps less of the gain.

## What this does and does not show

- **Combining the commit-level signals does not beat agreement alone.** The other two carry
  little or negative information. A fusion rule cannot make up information its voters lack.
- **The comparison is not fully held out for consensus.**
  - Agreement was chosen on the checks-arm half of these commits (`LATCH-OFFLINE.md`).
  - Its margin and tolerance were set from live smoke runs.
  - The learned verifier's scores are held out by module; agreement's AUC is a raw signal, not
    fitted.
- **The sample is small and clustered:** 125 commits, 4 modules, and correlated commits within a
  session.
- **Finer-grained fusion is untested.** At the cell level there are many more voters: each
  requirement check, each peer and each output port.
  - With many informative voters, a label model can estimate each one's reliability without
    golden.
  - A commit could then be scored by the change in the posterior correctness of the cells it
    moves. That posterior would draw on each check and each peer's reliability, not one coarse
    count.
  - Even so, that model cannot recover a defect shared by every peer and every check, which is
    the dc_fsm luna14 case in `LATCH-OFFLINE.md`.
