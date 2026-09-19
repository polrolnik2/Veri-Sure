# The guard that preferred a check deciding nothing

`_choose_bodies` applied `dissent_weighted` as a **tier** -- `inside or tier` --
so any body inside the guard beat any body outside it whatever either one
decided. A body convicting NOBODY is as far inside the guard as a body can get,
so the guard against over-strictness was selecting for the other sign of the
same defect.

## What it cost, on the confirming end-to-end run

Four requirements froze a body separating nothing over a sibling separating
thousands of cells:

    REQ-0001   closes    0  ->  7863
    REQ-0021   closes    0  ->  4749
    REQ-0121   closes    0  ->  3612
    REQ-0059   closes    0  ->    24

## The sweep that says this is the repair and not a fit

`max_dissent_weighted` over the same corpus, blindness only -- computed from the
seven spec-derived designs and from nothing else:

    maxdw                1.0     2.0     3.0     3.5    4.0+
    tier first         16.6%   14.6%   14.1%    9.0%    9.0%
    separation first    9.0%    9.2%    9.2%    9.0%    9.0%

**The threshold stops being a knob.** It ships at 2.0 and is left there. On the
first run's corpus, where no body convicted more than two designs and the guard
never bound, both rules read 5.7% at every value -- a fix that is a no-op where
the defect did not bite.

## The triple, both corpora, scored by `specflow/scorecard.py`

| corpus | rule | span | blindness | audit | |
|---|---|---|---|---|---|
| run 1 | as shipped | 99.1% | 5.7% | 0/15 | MET |
| run 1 | separation first | 99.1% | 5.7% | 0/15 | MET (no-op) |
| run 2 | as shipped | 97.4% | **14.6%** | 0/14 | NOT MET |
| run 2 | separation first | 97.4% | **9.2%** | 0/14 | **MET** |

`as shipped` on run 2 reproduces that run's own `scorecard.json` exactly, which
is what says the offline instrument is the run's instrument.

**The rule was chosen on span and blindness.** Both are computed from the
spec-derived population; the control is read by `scorecard` and by nothing else.
The audit column is reported beside the sweep and was not swept: choosing a
threshold by the grade is gating on the control in slow motion.

## What was ruled out first, and is recorded as a null

* **Coordinate ascent** -- running the same greedy to a fixed point instead of
  one pass: 3887 -> 3868 blind cells, 0.07 points. The pass order is not the
  defect.
* **Supplementary bodies** -- admitting any further body that is alive,
  unrefuted and inside the guard and that separates a cell nothing else
  separates: **+0 admitted**. Not one remained. The residue was not a selection
  failure and not an authoring failure.
* **Authoring at cells** -- 40 bodies authored at blind cells, `_adopt_cell_bodies`
  took 0 and the chooser took 4. 4 of 40 = 10%, inside the plan's pre-registered
  "<=15% fully caught closes the line" band for E4.

## The drivers

    e6_corpus_tables.py   replay one run's whole corpus against its own
                          population once, and cache it
    e6_dissent_sweep.py   sweep the guard on golden-free quantities only
    e6_score_map.py       score a chosen-body map with the run's own scorecard
    e6_check_rtl.py       judge a candidate RTL with the frozen check set and
                          with nothing else
