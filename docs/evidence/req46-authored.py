"""The REQ-0046 check a Sonnet subagent authored, verbatim, as the trial input.

The author saw the requirement text, the normalized form with `activation.sustains`
populated, the contract ports and the trace row shape. It saw NO RTL of any kind.
Kept unmodified because it is the measurement: this is what the new expressiveness
bought on a first attempt, and it convicts golden. See req46.md.
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

        baseline = (
            _val(baseline_row, "busy"),
            _val(baseline_row, "dout"),
            _val(baseline_row, "al"),
        )
        disturb_edge = None
        for k in range(start, obs_end):
            now = (_val(trace[k], "busy"), _val(trace[k], "dout"), _val(trace[k], "al"))
            if now != baseline:
                disturb_edge = trace[k].get("edge")
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
