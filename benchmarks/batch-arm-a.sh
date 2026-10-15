#!/bin/bash
# Run arm A over a list of tasks with replicates, score each, log each.
#
# REPLICATES ARE THE POINT. One run of one task is an anecdote: the pipeline is
# sampling from a model, so the same task can produce RTL that passes and RTL
# that does not. A miss rate needs a denominator, and the denominator is runs.
#
# EACH RUN IS SCORED AND LOGGED AS IT FINISHES, not at the end. The container
# is reclaimed after a period of inactivity and takes the run directory with
# it; a batch that scored only at the end would lose every result to one
# reclaim. `telemetry.py --csv` replaces a run's row rather than appending, so
# re-running this over a partly-finished batch is safe.
#
# CONCURRENCY IS DELIBERATELY LOW. The gateway is shared with whatever else is
# running, and OPENAI_MAX_RETRIES is 2 by design here (8 retries of a call the
# gateway structurally cannot complete is ~40 minutes of silence). Three at a
# time keeps bursts inside what two retries absorb.
#
#     benchmarks/batch-arm-a.sh 3 fpu_exceptions:2 or1200_dc_fsm:3
set -u
REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
ARM=/home/user/arm-a
RUNS=/home/user/runs
PAR="${1:?usage: batch-arm-a.sh PARALLEL task:count [task:count ...]}"
shift
# THE EFFORT IS THE LEVER THAT DECIDES WHETHER ARM A RUNS AT ALL, and it lives
# in the env file because arm A has no model switches -- `chipverilog_arm_a.py`
# calls `load_openai_config()` with no model or effort argument.
#
# At xhigh, gpt-5.6-luna reasons past this gateway's 300s idle reaper and the
# connection is closed: 10 of 11 batch runs died that way, and an isolated
# retry died identically at 903s == 3 x 301s. Streaming plus reasoning
# summaries moved the failure but did not remove it. At medium the same task
# (or1200_dc_fsm) completes in 4 minutes with a passing self-TB.
#
# So ARM_ENV selects the configuration, and every run in one batch must use
# ONE of them: an effort mixed across a set makes its runs incomparable to each
# other, which is the confound this project keeps paying for.
ARM_ENV="${ARM_ENV:-$REPO/.env.local}"
# Runs are named `a-<TAG><task>-<n>`, so a batch at one configuration cannot
# overwrite a batch at another. Without it the medium re-run would have
# destroyed the two xhigh results that DID complete, and the telemetry row
# keyed on the run name would have silently been replaced rather than added.
ARM_TAG="${ARM_TAG:-}"

find_task() {
    find "$REPO/benchmarks/chipverilog/Des" -maxdepth 2 -type d -name "$1" | head -1
}

one() {                                  # one() TASK_DIR TASK RUN_DIR
    local dir="$1" task="$2" run="$3"
    rm -rf "$run"; mkdir -p "$run"
    ( cd "$ARM" && echo $BASHPID > "$run/run.pid"
      "$REPO/.venv/bin/python" chipverilog_arm_a.py \
          --task-dir "$dir" --out "$run" --env-file "$REPO/.env.local" \
      ) > "$run.log" 2>&1
    echo "$?" > "$run/done"
    # SCORE ONLY WHAT EXISTS. A run that produced no rtl.sv is a result too --
    # scoring it would report a tool error where the finding is "made nothing".
    if [ -s "$run/rtl.sv" ]; then
        "$REPO/.venv/bin/python" "$REPO/benchmarks/score_chipverilog.py" \
            --run-dir "$run" --task "$task" >> "$run.log" 2>&1
    fi
    "$REPO/.venv/bin/python" "$REPO/benchmarks/telemetry.py" \
        --run "$run" --csv "$REPO/benchmarks/telemetry.csv" >> "$run.log" 2>&1
    printf '%s  %-24s self_tb=%-5s verdict=%s\n' "$(date '+%H:%M:%S')" \
        "$(basename "$run")" \
        "$(python3 -c "import json;print(json.load(open('$run/baseline.json')).get('is_sim_pass'))" 2>/dev/null)" \
        "$(python3 -c "import json;print(json.load(open('$run/score.json')).get('status'))" 2>/dev/null || echo none)"
}

for spec in "$@"; do
    task="${spec%%:*}"; n="${spec##*:}"; [ "$n" = "$task" ] && n=1
    dir="$(find_task "$task")"
    if [ -z "$dir" ]; then echo "!! no task dir for $task; skipped"; continue; fi
    for i in $(seq 1 "$n"); do
        while [ "$(jobs -rp | wc -l)" -ge "$PAR" ]; do wait -n; done
        one "$dir" "$task" "$RUNS/a-$ARM_TAG$task-$i" &
    done
done
wait
echo "batch complete"
