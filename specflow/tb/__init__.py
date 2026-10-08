"""Testbench runtime and rendering.

The only cocotb-specific part of specflow. `runtime.py` is hand-written and
protected: it owns the clock, the scoreboard, the coverage recorder and the
verdict record, so a rendered testcase supplies stimulus and nothing else.
"""
