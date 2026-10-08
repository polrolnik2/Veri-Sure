#!/bin/bash
# claim.sh <rendezvous-dir> [wait-seconds] [stale-seconds]
#
# Prints the path of ONE prompt this worker now owns, or DONE, or TIMEOUT.
#
# The claim is keyed by the prompt's CONTENT, not its name. `AgentPort` reuses
# `(stage, round_)` across a repair round -- it deletes the response and writes a
# NEW prompt under the same filename -- so a name-keyed claim would be held by
# round 1 forever and round 2 would never be picked up. A content hash makes the
# rewritten prompt a different thing to claim, which is what it is.
#
# AND CLAIMS EXPIRE. A worker that dies mid-answer holds its claim forever, and
# the stage is blocked on a prompt nobody will ever write. Observed: two prompts
# each held by one dead claim, with four live workers idling beside them. A claim
# older than STALE with still no response is treated as abandoned.
D="${1:?rendezvous dir}"
END=$((SECONDS + ${2:-900}))
STALE=${3:-420}
while [ "$SECONDS" -lt "$END" ]; do
  for p in "$D"/*_prompt.txt; do
    [ -e "$p" ] || continue
    r="${p%_prompt.txt}_response.txt"
    [ -f "$r" ] && continue
    h=$(sha256sum "$p" | cut -c1-16)
    c="$p.claim.$h"
    if mkdir "$c" 2>/dev/null; then
      echo "$p"; exit 0
    fi
    # Held. Abandoned?
    if [ -d "$c" ] && [ -z "$(find "$c" -maxdepth 0 -newermt "-${STALE} seconds" 2>/dev/null)" ]; then
      rmdir "$c" 2>/dev/null && mkdir "$c" 2>/dev/null && { echo "$p"; exit 0; }
    fi
  done
  [ -f "$D/DONE" ] && { echo DONE; exit 0; }
  sleep 3
done
echo TIMEOUT
