#!/bin/bash
# Reconstruct arm A of the ChipVerilog comparison: Veri-Sure WITHOUT the agent
# hardening, plus the minimum needed to reach the model at all.
#
# Without this script arm A exists only as an unversioned worktree, which makes
# the before/after comparison impossible to repeat. What arm A *is* has to be
# auditable, because the whole claim rests on the two arms differing in exactly
# one thing.
#
# WHAT IS EXCLUDED (the hardening under test):
#   specflow/ in its entirety -- the spec -> requirements -> testplan -> coverage
#   chain, the Python reference model, the cocotb renderer, gates G1-G8, the
#   hard-gated loop and the testcase tool -- plus the eda_agent bridge and the
#   retirement of the SystemVerilog path. tb_generator.py, _run_instance and
#   TB_4_SHOT_EXAMPLES all remain.
#
# WHAT IS INCLUDED, and why it is not hardening:
#   1. transport (config.py, model.py, responses_model.py). The merge-base tree
#      cannot reach gpt-5.6-luna at all: a hardcoded temperature that reasoning
#      models reject, no environment path for reasoning_effort, and a gateway
#      that refuses function tools together with reasoning effort on
#      chat-completions while every agent here is tool-using. A zero caused by
#      `400 unknown_parameter` is indistinguishable from a zero caused by a bad
#      testbench, so measuring the transport is not the experiment.
#   2. hierarchy plumbing (sim_reviewer.py). Lets a candidate instantiate
#      pre-made children, which ChipVerilog supplies to candidates itself. A
#      module-level registry rather than a rewrite of _run_instance: changing
#      that arm's control flow would alter the thing being measured. Inert for
#      leaf tasks, where the registry stays empty.
#
# Neither touches a testbench, a prompt, a gate, or a verdict.
set -euo pipefail

REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
DEST=${1:?usage: make_arm_a.sh <destination-dir> [merge-base-sha]}
BASE=${2:-86b3d9f50bb3099ed03bc6a3cf7d4d59fb4c7b7f}

echo "reconstructing arm A at $DEST from $BASE"
git -C "$REPO" worktree add --detach "$DEST" "$BASE"

# 1. transport, taken as a diff from this branch so it cannot drift out of sync
git -C "$REPO" diff "$BASE" HEAD -- eda_agent/config.py eda_agent/model.py \
    | git -C "$DEST" apply
cp "$REPO/eda_agent/responses_model.py" "$DEST/eda_agent/responses_model.py"

# 2. hierarchy plumbing
git -C "$DEST" apply "$REPO/benchmarks/arm_a_hierarchy.patch"

# 3. the runner
cp "$REPO/benchmarks/chipverilog_arm_a.py" "$DEST/"

echo
echo "verifying arm A is the pre-hardening tree:"
[ -d "$DEST/specflow" ]                  && { echo "  FAIL specflow/ present"; exit 1; }
[ -f "$DEST/eda_agent/tb_generator.py" ] || { echo "  FAIL tb_generator.py missing"; exit 1; }
grep -q TB_4_SHOT_EXAMPLES "$DEST/eda_agent/prompts.py" || { echo "  FAIL prompt corpus missing"; exit 1; }
echo "  ok  specflow/ absent, tb_generator.py present, TB_4_SHOT_EXAMPLES present"
echo
echo "changed vs $BASE (must be transport + hierarchy only):"
git -C "$DEST" diff --stat
echo
echo "run it with:"
echo "  cd $DEST && python3 chipverilog_arm_a.py \\"
echo "      --task-dir $REPO/benchmarks/chipverilog/Des/<family>/<module> \\"
echo "      --out <run-dir> --env-file $REPO/.env.local"
