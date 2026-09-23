# Can selection fix the audit column? No, and the corpus says why.

Three questions, measured on `full2` with GOLDEN RTL as the audit control and
the relaxed blindness target of < 20%.

    target:  span > 0.90    blindness < 0.20    audit = 0

## 1. Deleting the checks this branch's design-free rules flag

    config        checks   span      blindness   audit
    baseline         122   0.9737    0.1454      9/37 = 0.2432
    -unbounded       119   0.9474    0.1454      8/35 = 0.2286
    -phase            91   0.7105    0.2212      3/25 = 0.1200
    -both             88   0.6842    0.2212      2/23 = 0.0870

Audit falls to 0.087 and **span collapses to 68%** while blindness crosses the
target. The phase screen alone removes 31 of 122 checks and costs 26 points of
span. Deletion without re-authoring is not a route.

## 2. The frontier of selection, which is a DIAGNOSTIC and never a rule

Selection can only remove, and removal moves the columns in fixed directions:
span down, blindness up, audit down. So the best selection can do is remove
EXACTLY the checks that convict the control:

    baseline               122   SPAN 0.9737 MET   BLIND 0.1454 MET   AUDIT 0.2432 no
    minus the convicting   112   SPAN 0.8947 no    BLIND 0.1454 MET   AUDIT 0.0000 MET

**Span 0.8947 against a target of 0.90 -- short by 0.53 points.** Ten checks
removed cost NINE requirements their only coverage, so 111 trusted becomes 102
of 114 behavioural.

(Choosing a set this way is gating on the grade and is barred from shipping.
It is computed to answer whether the target is reachable at all.)

## 3. Is there another body for those requirements? Almost never.

The corpus holds 616 bodies over 152 requirements, median 4 each. For each of
the ten convicting requirements, every OTHER body authored for it was replayed
against golden:

    req        bodies   well-formed alternatives that do NOT convict
    REQ-0034        4   0
    REQ-0035        4   0
    REQ-0053        3   0
    REQ-0055        3   0
    REQ-0058        4   2
    REQ-0066        2   0
    REQ-0067        2   0
    REQ-0110        2   0
    REQ-0111        2   0
    REQ-0112        2   0

**One of ten.** Every body the pipeline ever authored for the other nine
convicts the known-good design.

So the convictions are not an artifact of picking the wrong body, and a bigger
pool does not help: the pipeline reads those nine sentences the same way in
every draft it writes. **Selection cannot fix this, with the accepted set or
with the whole corpus.** The defect is upstream of selection, in how the
requirement is read.

## 4. Is it exclusively the probes?

No -- but it is the largest share.

    cause                                    checks                        probes?
    probe PHASE, contract has no such field  REQ-0066 0067 0110 0111 0112  yes
    downstream of the same                   REQ-0035                      yes
    `slave_wait` EXTENT, sentence ambiguous  REQ-0053 REQ-0055             no
    `throughout` over TO_END, a check defect REQ-0034                      no
    cause not found                          REQ-0058                      unknown

Six of ten are probe expressiveness: a `dir: "probe"` entry obliges a name and
a width, and the specification's equation says nothing about whether the value
is a wire or a flop, so the population picks one reading and a correct design
may pick the other.

Two are not about probes at all. The `slave_wait` sentence admits a level and
an event, and golden picks the event; that ambiguity would survive any probe
contract. One is a plain check-authoring defect, now refused by
`unbounded_invariant`.

**And the coherence is worth noting: the ONE requirement selection can rescue,
REQ-0058, is the one whose cause is not a systematic misreading.** Where the
pipeline reads a sentence one way in every draft, no alternative body exists to
select; where a single body was merely wrong, alternatives do exist.

## What this leaves

Span and blindness are met at baseline (0.9737, 0.1454). Audit is not, and
neither deletion nor selection reaches it without giving up span. The routes
that remain all author rather than select:

  * state the phase in the probe contract, or make a probe-reading event check
    phase-tolerant unless the requirement states a timing -- six of ten;
  * resolve the `slave_wait` reading in the specification -- two of ten;
  * REQ-0058, cause still unknown -- one of ten, and already rescuable.
