#!/bin/bash
# c1-i2c: a FULL run (no --reuse) exercising every fix landed since a2-i2c.
#
# IN THE REPO, NOT IN THE RUN DIRECTORY. The first version of this lived in
# /home/user/runs/, which is outside the checkout and gitignored -- so the exact
# configuration a result came from would have vanished with the container. Same
# reasoning that moved the watchdog here in 3985eeb: a run's config IS part of
# its result, and a config only one machine has ever seen is not reproducible.
#
# WHAT THIS RUN IS FOR, in landing order:
#   af986aa  `until` is a disjunction, so a close condition is a list
#   e3cd085  `edges` / $rose -- an edge is not a level
#   311801d  the SVA toolbox
#   b6a22d6  `after_activation` derived from the schema...
#   122a18d  ...and accepted by all seven window operators
#   454ff56  the clock-as-edge gate
#   098c360  a cache key even when an agent passes none
#   ec1870f  usage read off a dict subclass without raising
#   d2b59e8  the debug loop's third counter reaches the artifact
#
# `--small-effort medium`, NOT high. High was tried and dropped: measured at
# 33 s per classify unit, it needed ~45 minutes for the FIRST of ten stages.
# Medium is also what a2-i2c ran, so the oracle numbers stay comparable --
# raising it would add a second variable beside the SVA fixes and make a
# movement impossible to attribute.
#
# `--adequacy-rounds 0` and `--refmodel-judge-turns 1`: stop after the first
# reference model is generated, so its cost can be read before more is spent.
# Adequacy would build a second model.
#
# Launch as a HARNESS BACKGROUND TASK, never nohup/setsid/disown: what gets
# taken away in this environment is the machine, and only a tracked task's exit
# wakes the session.
set -u
RUN="${1:-/home/user/runs/c1-i2c}"
REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
mkdir -p "$RUN"
cd "$REPO"
echo $$ > "$RUN/run.pid"
.venv/bin/python benchmarks/run_chipverilog.py \
  --task i2c_master_bit_ctrl \
  --out "$RUN" \
  --env-file .env.local \
  --small-model gpt-5-mini \
  --small-effort medium \
  --variants \
  --correspondence \
  --adequacy-rounds 0 \
  --advisory-abandoned \
  --refmodel-judge-turns 1 \
  --refmodel-debug-attempts 15
rc=$?
# The done marker carries the exit code, and the exit code is NOT sufficient on
# its own: a leaf exception is caught and reported as a result, so a run that
# produced nothing still exits 0. Check for specflow/ref_model.py and for
# leaf_exception.txt before believing a zero here.
echo "$rc" > "$RUN/done"
exit "$rc"
