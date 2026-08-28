#!/bin/bash
# Package a run so it survives this container.
#
# WHY THIS EXISTS. Run directories live OUTSIDE the repo (/home/user/runs, not
# the checkout) and `runs/` inside the repo is gitignored, so a run is not in
# git by construction. The container is reclaimed after a period of inactivity
# -- measured at ~6 minutes past the end of a turn -- and takes the whole
# directory with it. Three runs have already been lost that way.
#
# TWO TIERS, because they want different homes. Measured on a2-i2c (71 MB):
#
#   specflow/ + the gate and score artifacts   5.2 MB -> 372 KB gzipped
#       The RESULTS. Small enough to commit, and worth committing: they are
#       what a later run is compared against, and a diff over them is readable.
#
#   agent_io/                                   65 MB -> 12 MB gzipped
#       Every prompt, response and meta.json. This is what lets a finding be
#       re-derived months later -- the stage analysis that corrected the
#       oracles.json mix-up was reconstructed entirely from these files. Too
#       big to put in git history permanently, where it cannot be removed
#       without a rewrite. Hand it over as a file instead.
#
#     benchmarks/save-run.sh /home/user/runs/c1-i2c /home/user/runs/pack
set -euo pipefail
RUN="${1:?usage: save-run.sh RUN_DIR OUT_DIR}"
OUT="${2:?usage: save-run.sh RUN_DIR OUT_DIR}"
NAME="$(basename "$RUN")"
mkdir -p "$OUT"

# The results tier. `--ignore-failed-read` so a run that stopped early still
# packages what it did produce: a partial run is evidence, and the commonest
# reason to reach for this script is that something went wrong.
tar -czf "$OUT/$NAME-results.tgz" --ignore-failed-read -C "$(dirname "$RUN")" \
    "$NAME/specflow" \
    "$NAME/contract.json" "$NAME/prompt.txt" "$NAME/baseline.json" \
    "$NAME/contract_lint.txt" "$NAME/leaf_exception.txt" 2>/dev/null || true

# The transcript tier, separately so the results can be committed alone.
if [ -d "$RUN/agent_io" ]; then
    tar -czf "$OUT/$NAME-agent_io.tgz" -C "$RUN" agent_io
fi

# A manifest, so what is IN the archive is legible without unpacking it -- and
# so a missing artifact is visible as a missing line rather than inferred from
# a size. `leaf_exception.txt` present is the tell that the run died; see the
# note in the plan about a leaf failure still exiting 0.
{
    echo "run:      $NAME"
    echo "packaged: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "uptime:   $(uptime -s)"
    echo
    echo "present:"
    for f in specflow/oracles.json specflow/ref_model.py specflow/normalized.json \
             specflow/requirements.json specflow/testplan.json specflow/stimulus.json \
             specflow/variants.json specflow/witness.py specflow/cache_report.json \
             specflow/refmodel_gate.json contract.json leaf_exception.txt; do
        [ -e "$RUN/$f" ] && printf '  %-34s %s\n' "$f" "$(du -h "$RUN/$f" | cut -f1)"
    done
    echo
    echo "archives:"
    ls -lh "$OUT/$NAME"-*.tgz 2>/dev/null | awk '{printf "  %-40s %s\n", $9, $5}'
} > "$OUT/$NAME-manifest.txt"
cat "$OUT/$NAME-manifest.txt"
