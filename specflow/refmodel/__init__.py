"""Generation and validation of the Python reference model.

The model is the testbench's oracle: expected values come from here and nowhere
else. It is derived from the specification alone -- the generating agent is never
shown `rtl.sv`, and at the point this stage runs no RTL exists yet, so the
isolation is a property of the pipeline's ordering rather than of a prompt rule.
"""

from .base import RefModel

__all__ = ["RefModel"]
