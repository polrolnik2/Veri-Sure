# luna12 or1200_dc_fsm, model-feedback arm -- `rtl.sv` lost

The job finished normally at 23:12 (2 rounds, 66/1/13 -> 77/0/3, ChipVerilog
`function_fail`). Seconds later a stray re-launch of this module's arms wiped
its working directory before the probe-port `rtl.sv` was collected: the
driver script (`job.sh`, outside the repo) was edited while this job's copy of
it was still running, and bash, which reads a script as it goes, resumed at a
stale offset inside the edited file. The stray runs had no start design, so
they failed before writing a summary or a verdict.

`rtl_deliverable.sv` here is the deliverable `e7_module.py` handed ChipVerilog
for the verdict in `chipverilog.json` -- the spec-interface wrapper, probes
unconnected -- recovered from `deliverable/cf-model/or1200_dc_fsm/rtl.sv`. It is
what the behaviour harness simulates. `editor_summary.json` and
`chipverilog.json` are the job's own.
