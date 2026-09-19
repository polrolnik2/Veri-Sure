"""The same check with the two attribution gates its own material already stated.

DIAGNOSIS, NOT AUTHORING. I added these two gates by hand to find out which
confound was load-bearing. Both are read off material the author was already
given, never off the RTL:

  * the per-observable when-clause in `observed_via` -- `dout` is observable
    only "around a filtered-SCL rising sample", `al` only "during an
    arbitration-checking window (WRITE with din=1, cmd=4, ena=1)". The authored
    check watched all three unconditionally.
  * the requirement's own causal wording -- glitches "must not CAUSE filtered-edge
    events". A window in which some other input also moves carries a second
    cause, so an output change there is not attributable and the observation is
    discarded rather than blamed on the glitch.

Neither gate alone is enough, and each removes a different confound: see req46.md.
"""

def _val(row, port):
    """Read `port` from a row, outputs first (mirrors the harness's own lookup)."""
    outs = row.get("outputs") or {}
    if port in outs:
        return outs[port]
    return (row.get("inputs") or {}).get(port)


def _normal(row):
    """Normal operation, per the normalized activation: nReset=1, rst=0, ena=1."""
    ins = row.get("inputs") or {}
    return ins.get("nReset") == 1 and ins.get("rst") == 0 and ins.get("ena") == 1


_WATCHED = ("scl_i", "sda_i", "cmd", "din", "ena", "rst", "nReset")


def _low_runs(trace, port):
    """Every maximal run of consecutive rows where `port` == 0.

    Width is measured in EDGES, not rows: the trace is state-compressed (a run
    of identical rows collapses into one row carrying `held`), so a run that
    spans several rows because something else changed mid-pulse must still sum
    `held` across all of them to recover the true duration -- the same reading
    `pulse()` uses for exactly this reason.
    """
    runs = []
    i, n = 0, len(trace)
    while i < n:
        ins = trace[i].get("inputs") or {}
        if ins.get(port) == 0:
            j, width = i, 0
            while j < n:
                inner = trace[j].get("inputs") or {}
                if inner.get(port) != 0:
                    break
                width += int(trace[j].get("held", 1) or 1)
                j += 1
            runs.append({"port": port, "start": i, "end": j - 1, "width": width})
            i = j
        else:
            i += 1
    return runs


def decide(trace):
    # `sda_i`/`scl_i` idle at 1 (open-drain, released); the glitch the
    # requirement is about is a pull-low run. Gather every such run on both
    # lines, in trace order, so the boundary between one event and the next
    # can be told apart.
    raw_runs = sorted(
        _low_runs(trace, "scl_i") + _low_runs(trace, "sda_i"),
        key=lambda r: r["start"],
    )

    short_runs = []
    sustained_runs = []

    for idx, run in enumerate(raw_runs):
        start, end, width, port = run["start"], run["end"], run["width"], run["port"]
        if start == 0:
            continue  # no row before it to use as a baseline
        baseline_row = trace[start - 1]
        if not _normal(baseline_row):
            continue  # the run did not occur under normal operation
        if not all(_normal(trace[k]) for k in range(start, end + 1)):
            continue

        # Observe only up to the next low run on either line -- far enough to
        # see a filtered response, but not so far that a later, unrelated
        # glitch gets blamed on this one.
        obs_end = raw_runs[idx + 1]["start"] if idx + 1 < len(raw_runs) else len(trace)
        obs_end = max(obs_end, start + 1)

        # ATTRIBUTION. The requirement is causal -- a glitch must not CAUSE a
        # filtered-edge event -- so a change in the observed outputs is
        # evidence about THIS pulse only when nothing else in the window could
        # have caused it. If any other input moves before the window closes,
        # the window carries a second cause and the observation is discarded
        # rather than blamed on the glitch.
        _quiet = True
        for k in range(start, min(obs_end, len(trace))):
            a = trace[k].get("inputs") or {}
            b = (trace[k - 1].get("inputs") or {}) if k else a
            if any(a.get(p) != b.get(p) for p in _WATCHED if p != port):
                _quiet = False
                break
        if not _quiet:
            continue

        # Each observable carries its OWN when-clause in observed_via, and a
        # change seen outside that clause is not evidence about the filter:
        #   busy  -- any time under normal operation
        #   dout  -- only "around a filtered-SCL rising sample", so only after
        #            a rise of scl_i inside the window; dout is written on a
        #            filtered SCL rise and on nothing else, so with scl_i flat
        #            any dout motion is something the design was going to do
        #            regardless of this glitch
        #   al    -- only "during an arbitration-checking window
        #            (WRITE with din=1, cmd=4, ena=1)"
        disturb_edge = None
        seen_scl_rise = False
        for k in range(start, obs_end):
            row, ins = trace[k], (trace[k].get("inputs") or {})
            prev_ins = (trace[k - 1].get("inputs") or {}) if k else {}
            if prev_ins.get("scl_i") == 0 and ins.get("scl_i") == 1:
                seen_scl_rise = True
            watched = ["busy"]
            if seen_scl_rise:
                watched.append("dout")
            if ins.get("cmd") == 4 and ins.get("din") == 1 and ins.get("ena") == 1:
                watched.append("al")
            if any(_val(row, p) != _val(baseline_row, p) for p in watched):
                disturb_edge = row.get("edge")
                break

        entry = {
            "port": port,
            "start_edge": trace[start].get("edge"),
            "width": width,
            "disturb_edge": disturb_edge,
        }
        (short_runs if width <= 1 else sustained_runs).append(entry)

    # Point 1: both a sub-threshold pulse and a sustained change must be
    # present, or there is nothing to discriminate on.
    if not short_runs or not sustained_runs:
        return (None, None,
                "the trace contains no usable pair: it needs both a "
                "sub-threshold glitch (run length <= 1 edge) and a sustained "
                "change (run length >= 2 edges) on scl_i or sda_i under normal "
                "operation (nReset=1, rst=0, ena=1) to run the differential "
                "majority-filter check")

    # Point 2: a short glitch must leave busy, dout and al undisturbed.
    disturbed_short = [r for r in short_runs if r["disturb_edge"] is not None]
    if disturbed_short:
        bad = disturbed_short[0]
        return (False, bad["disturb_edge"],
                f"a {bad['width']}-edge glitch on {bad['port']} starting at "
                f"edge {bad['start_edge']} (run length <= 1, below the "
                f"majority-filter threshold) was followed by a change in "
                f"busy/dout/al at edge {bad['disturb_edge']}; a glitch that "
                f"cannot win a majority of the three samples must not disturb "
                f"the filtered outputs")

    # Point 3: at least one sustained change must actually produce an
    # observable response, or the absence of change on the short pulses is
    # not suppression -- it is a design that ignores the line entirely.
    responsive_sustained = [r for r in sustained_runs if r["disturb_edge"] is not None]
    if not responsive_sustained:
        return (None, None,
                "every sustained change (run length >= 2 edges) on scl_i/sda_i "
                "left busy, dout and al unchanged in this trace, so there is "
                "no evidence the outputs can respond to these lines at all; "
                "the short glitches leaving them undisturbed therefore proves "
                "nothing about majority-vote suppression")

    ok_edge = responsive_sustained[0]["disturb_edge"]
    return (True, ok_edge,
            f"{len(short_runs)} sub-threshold glitch(es) (run length <= 1 "
            f"edge) on scl_i/sda_i left busy, dout and al undisturbed, while "
            f"{len(responsive_sustained)} sustained change(s) (run length >= "
            f"2 edges) on the same lines produced an observable change (first "
            f"at edge {ok_edge}) -- the majority filter suppresses short "
            f"glitches without masking real changes")
