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
        one "$dir" "$task" "$RUNS/a-$task-$i" &
    done
done
wait
echo "batch complete"
