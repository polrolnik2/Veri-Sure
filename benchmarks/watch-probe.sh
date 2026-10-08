#!/bin/bash
# ONE PASS, NOT A LOOP. Run this as a harness background task
# (`Bash(run_in_background: true)`) and its EXIT is the wake signal: the
# harness re-invokes the session when a tracked background task ends.
#
# That is the whole point, and it is what every previous design here lacked.
# `setsid`, `nohup` and `disown` detach a process from a SHELL; what gets taken
# away in this environment is the MACHINE. Measured: the container was
# reclaimed at 14:20:08 and a `nohup`-launched probe died with it, leaving no
# record and firing no wake -- the session found out only because a human asked.
#
# `uptime -s` is written on every pass because it is the datum that tells a
# RECLAIM from a CRASH without guessing. A reboot timestamp newer than the run's
# start means the machine went away; the same timestamp means the run itself
# failed, which is a different problem with a different fix.
#
# Never `pkill -f` a pattern that also matches this script's own command line --
# it has cost two shells already. Kill by recorded PID.
set -u

PIDFILE="${1:?usage: watch-probe.sh PIDFILE WATCHFILE DONEFILE [INTERVAL_S] [HEARTBEAT_S]}"
WATCH="${2:?usage: watch-probe.sh PIDFILE WATCHFILE DONEFILE [INTERVAL_S] [HEARTBEAT_S]}"
# EXPLICIT, not derived. The first version guessed it as
# `$(dirname "$WATCH")/done`, and the watch file sat one level above the run
# directory holding the marker -- so a run that SUCCEEDED was reported as
# "gone with no done-marker". The wake fired correctly and said the wrong
# thing, which is worse than not firing: it invites treating a good result as
# a crash.
DONEFILE="${3:?usage: watch-probe.sh PIDFILE WATCHFILE DONEFILE [INTERVAL_S] [HEARTBEAT_S]}"
INTERVAL="${4:-20}"
# Seconds between heartbeat lines. An ARGUMENT rather than a constant so the
# behaviour can be exercised in seconds instead of asserted in a comment.
HEARTBEAT="${5:-300}"

note() { printf '%s  uptime_since=%s  %s\n' "$(date '+%H:%M:%S')" "$(uptime -s)" "$1" >> "$WATCH"; }

if [ ! -f "$PIDFILE" ]; then
    note "NO PIDFILE at $PIDFILE -- nothing to watch"
    exit 2
fi
PID="$(cat "$PIDFILE")"
note "watching pid=$PID"

# HEARTBEAT, because a silent watchdog is not observably a watchdog. The first
# version wrote one line at start and one at exit, so ten minutes of a healthy
# run and ten minutes of a dead one produced identical files -- and the only
# way to tell them apart was `ps`, which is exactly the check the watchdog
# exists to remove. `uptime -s` on every line is what makes a RECLAIM legible
# after the fact: the reboot timestamp changes mid-file.
BEAT=$(( HEARTBEAT / INTERVAL )); [ "$BEAT" -lt 1 ] && BEAT=1
ticks=0
while kill -0 "$PID" 2>/dev/null; do
    sleep "$INTERVAL"
    ticks=$(( ticks + 1 ))
    if [ $(( ticks % BEAT )) -eq 0 ]; then
        note "alive pid=$PID  ${ticks}x${INTERVAL}s"
    fi
done

# Exiting is the message. Non-zero so the notification reads as "look at this"
# rather than "a task finished", and the status line says which it was.
if [ -f "$DONEFILE" ]; then
    note "pid=$PID EXITED, run reported DONE"
    exit 0
fi
note "pid=$PID GONE with no done-marker -- reclaim or crash; check uptime above"
exit 1
