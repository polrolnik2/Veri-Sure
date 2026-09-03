"""Recompute the bit-controller's input filter FROM THE DECLARED INPUTS ALONE.

This is the whole point of the experiment. Every register below is a function of
`scl_i, sda_i, clk_cnt, nReset, rst, ena` and the clock -- all of them INPUT
ports the testbench itself drove. Nothing here reads a DUT output and nothing
reads a DUT internal, so this layer states an assumption about the STIMULUS, not
a belief about the design: a DUT whose own filter is broken still diverges from
it, and still gets convicted.

Transcribed from i2c_master_bit_ctrl.v lines 235-304. Register values are the
values ENTERING an edge (pre-update), which is the convention `Env._record`
samples the DUT's own registers on -- pinned by `check_convention` below rather
than assumed.
"""


def _maj3(f):
    """&f[2:1] | &f[1:0] | (f[2] & f[0]) -- majority of three."""
    b2, b1, b0 = (f >> 2) & 1, (f >> 1) & 1, f & 1
    return int((b2 & b1) | (b1 & b0) | (b2 & b0))


def derive(edges):
    """Yield one dict of derived filter registers per recorded edge."""
    cSCL = cSDA = 0
    fSCL = fSDA = 0b111
    sSCL = sSDA = dSCL = dSDA = 1
    filter_cnt = 0
    out = []
    for row in edges:
        inp = row.get("inputs") or {}
        out.append({"cSCL": cSCL, "cSDA": cSDA, "fSCL": fSCL, "fSDA": fSDA,
                    "sSCL": sSCL, "sSDA": sSDA, "dSCL": dSCL, "dSDA": dSDA,
                    "filter_cnt": filter_cnt})
        nReset = int(inp.get("nReset", 1) or 0)
        rst = int(inp.get("rst", 0) or 0)
        ena = int(inp.get("ena", 0) or 0)
        clk_cnt = int(inp.get("clk_cnt", 0) or 0)
        scl_i = int(inp.get("scl_i", 1) or 0)
        sda_i = int(inp.get("sda_i", 1) or 0)

        # every next-value is computed from the CURRENT state: these are four
        # independent always blocks, not a pipeline.
        if not nReset:
            n_c = (0, 0)
            n_f = (0b111, 0b111)
            n_s = (1, 1, 1, 1)
            n_cnt = 0
        else:
            n_c = ((0, 0) if rst else
                   (((cSCL << 1) | scl_i) & 3, ((cSDA << 1) | sda_i) & 3))
            if rst:
                n_f = (0b111, 0b111)
            elif filter_cnt == 0:
                n_f = (((fSCL << 1) | ((cSCL >> 1) & 1)) & 0b111,
                       ((fSDA << 1) | ((cSDA >> 1) & 1)) & 0b111)
            else:
                n_f = (fSCL, fSDA)
            n_s = ((1, 1, 1, 1) if rst
                   else (_maj3(fSCL), _maj3(fSDA), sSCL, sSDA))
            n_cnt = (0 if (rst or not ena)
                     else (clk_cnt >> 2) if filter_cnt == 0 else filter_cnt - 1)

        cSCL, cSDA = n_c
        fSCL, fSDA = n_f
        sSCL, sSDA, dSCL, dSDA = n_s
        filter_cnt = n_cnt
    return out


def check_convention(edges):
    """`dscl_oen <= #1 scl_oen` -- pins WHEN a recorded register was sampled.

    If rows hold pre-update values, dut_internal.dscl_oen at row i+1 equals
    dut.scl_oen at row i. Getting this backwards would shift every derived
    value by one edge and silently invalidate the whole experiment.
    """
    ok = bad = 0
    for a, b in zip(edges, edges[1:]):
        prev = (a.get("dut") or {}).get("scl_oen")
        got = (b.get("dut_internal") or {}).get("dscl_oen")
        if prev is None or got is None:
            continue
        ok, bad = (ok + 1, bad) if int(prev) == int(got) else (ok, bad + 1)
    return ok, bad


def check_against_dut(edges, der):
    """`if (sSCL & ~dSCL) dout <= #1 sSDA` -- validates the DERIVATION itself.

    The golden design latches dout on the filtered SCL rising edge, so on golden
    traces the derived filter predicts a real recorded output. This is the only
    honest way to trust a re-implementation: check it against the design's own
    behaviour, on a signal the derivation never reads.
    """
    ok = bad = 0
    for i in range(len(edges) - 1):
        if der[i]["sSCL"] == 1 and der[i]["dSCL"] == 0:
            got = (edges[i + 1].get("dut") or {}).get("dout")
            if got is None:
                continue
            ok, bad = (ok + 1, bad) if int(got) == der[i]["sSDA"] else (ok, bad + 1)
    return ok, bad
