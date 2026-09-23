# Frozen corpora, and how to run the pipeline unattended

## Why these exist

Four runs' artifacts went with a container reclaim on this branch, and every
number taken from them had to be recomputed or withdrawn. Three more --
`o1`..`o3` -- survived and STILL cannot be re-scored, because their contract
was never written down: they declare 17 probes where `full2` declares 24, so
replaying one's population under the other's contract reports every probe
unavailable and blindness reaches 99.7% by construction.

Both are the same failure: evidence that depends on a directory surviving, in
an environment where directories do not.

## What is frozen

    docs/evidence/e6/corpora/full2.tar.gz          390 KB
    docs/evidence/e6/corpora/full2.MANIFEST.json   readable, committed alongside
    docs/evidence/e6/corpora/full7.tar.gz          395 KB
    docs/evidence/e6/corpora/full7.MANIFEST.json

A run directory is ~150 MB; a corpus is ~390 KB, because `suite/` regenerates
from the testplan, the stimulus and the contract, and its `results/` are
simulator output. `agent_io/` is left out too: prompts and responses, and model
traces are gitignored here.

Each carries the contract, requirements, normalized forms, testplan, stimulus,
coverage model, probes, the frozen oracle set WITH its corpus of superseded
bodies, the spec-derived population, the reference model, and the scorecard the
run recorded -- plus a sha256 of every file.

    corpus   module                contract   population        checks
    full2    i2c_master_bit_ctrl   24 probes  7, all distinct   122 of 616 bodies
    full7    i2c_master_bit_ctrl   24 probes  7, all distinct   123 of 587 bodies

**"24 probes" IS NOT "THE SAME 24 PROBES."** `full7` declares
`read_sample_window` and `write_stable_high_phase` where `full2` declares
`filter_cnt_expired` and `filtered_scl_rise`. That is the `o1`..`o3` failure at
finer grain, and it is why the manifest records probe NAMES and the verifier
cross-checks them against the population's own `PROBE_PORTS` rather than
counting.

`full2` had no `contract.json` of its own -- the packer found that on its first
run, which is what it was written to catch. The one supplied is `recheck_run`'s,
and it is sound: all seven of `full2`'s population members declare exactly its
24 probe names, set-equal.

## Re-running one

    python3 docs/evidence/e6_verify_corpus.py <corpus-dir> [<golden-suite-dir>]

Checks every file against its digest, cross-checks the probes, then re-scores.
With a golden suite directory the audit column comes from an RTL control
instead of the Python transliteration, which is the difference between a
denominator of 14 checks and one of 37.

**A DIFFERENCE FROM THE RECORDED FIGURES IS EXPECTED AND IS NOT A FAILURE.**
The recorded numbers were computed by the code of their day. `full2` re-scores
today at span 0.9737 (unchanged), blindness 0.1454 against a recorded 0.1464 --
the boundary fix -- and audit 0.2432 over 37 checks against a recorded 0.0000
over 14. A re-score measures today's code against a frozen corpus, which is
what freezing one is for.

## Running the pipeline unattended

    python3 docs/evidence/e6_autorun.py <run-dir> \
        --spec     benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/description.txt \
        --contract benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json \
        --control  benchmarks/controls/i2c_master_bit_ctrl/ref_model.py \
        [--reuse] [--resume] [--population 7]

Three things it does that a driver script did not:

**It preflights.** One four-token call decides whether the gateway answers, and
it refuses to start if not. Discovering `429 BUDGET_EXCEEDED` after S1 is
discovering it having paid for S1. It also applies the two environment
corrections this project keeps re-learning: the base URL needs its `/v1` suffix
and the model name must drop its `openai/` prefix.

**It packs on completion, and on failure.** A run that died at the oracle stage
still spent what it spent, and its S1, probe, S2 and S3 artifacts are exactly
the material the four lost runs would have left behind.

**The control goes in as `audit_control` only.** That parameter reaches
`scorecard.score`, which has no author, no prompt and no repair path.
`refmodel_control` reaches the oracle stage and can reject. A control may
REJECT an oracle and may never REPAIR one; passed this way it does not even
reject, it only scores.

### `--resume` collapsed a population once

`ResumePort` keys recorded responses on `(stage, round_)`, and every population
member shares `WITNESS_STAGE` -- so one recorded witness was replayed seven
times and `full10`'s seven "designs" were one design with seven names: all
files identical, one distinct md5, cells 0, blindness n/a. That result was
withdrawn. `oracles_stage._population` now bypasses call-level resume; the
warning stays because the shape of the bug outlived its instance.

## Publishing to Hugging Face

**NOT DONE, AND NOT ATTEMPTED.** No `HF_TOKEN`, `HUGGINGFACE_TOKEN` or
`HUGGING_FACE_HUB_TOKEN` exists in this environment, so the upload cannot run
from here -- and publishing is a decision about someone else's research
artifacts, which is not a decision to make silently.

The pathway, for whoever does decide:

    pip install huggingface_hub
    huggingface-cli login                       # or set HF_TOKEN
    python3 - <<'EOF'
    from huggingface_hub import HfApi
    api = HfApi()
    repo = "<org>/veri-sure-corpora"
    api.create_repo(repo, repo_type="dataset", exist_ok=True, private=True)
    api.upload_folder(folder_path="docs/evidence/e6/corpora",
                      repo_id=repo, repo_type="dataset")
    EOF

Three things to settle first, none of them technical:

  * **Licensing.** The corpora derive from the OpenCores i2c specification and
    RTL in `benchmarks/`. Whatever licence governs that governs anything
    published from it.
  * **Private or public.** `private=True` above is the safe default and a
    deliberate one.
  * **What the card claims.** A dataset card that reports span / blindness /
    audit without saying that audit is measured over 37 of 111 checks, and why,
    would repeat in public the exact misreading this branch spent a session
    correcting. `TRIPLE.md` and `PROBE-TRADE.md` are the text it should carry.
