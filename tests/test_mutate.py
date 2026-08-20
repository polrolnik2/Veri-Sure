"""One wrong design, deterministically, so a discrimination check has a subject.

"The generated reference model passes golden" is unfalsifiable on its own: a
model returning constants passes golden on a quiet stimulus too. The only way to
separate agreement from vacuity is to check that something WRONG fails, and only
one of the three designs under test has an LLM-written candidate lying around.

Deliberately one operator and deliberately reported: a multi-site mutant makes a
failure hard to attribute, and an unreported one makes the measurement
unreproducible.
"""

from __future__ import annotations

import pytest

from benchmarks.mutate import mutate


def test_it_changes_exactly_one_operator():
    src = "module m; assign y = a + b; assign z = c + d; endmodule\n"
    out, what = mutate(src)
    assert out == "module m; assign y = a - b; assign z = c + d; endmodule\n"
    assert "line 1" in what and "+ becomes -" in what


def test_it_is_deterministic():
    src = "module m; assign y = a + b; endmodule\n"
    assert mutate(src)[0] == mutate(src)[0]


def test_a_later_site_is_reachable():
    src = "module m; assign y = a + b; assign z = c + d; endmodule\n"
    assert mutate(src, 1)[0].count("-") == 1
    assert "assign y = a + b" in mutate(src, 1)[0]


def test_comments_are_never_mutated():
    """A mutant that only edits a comment is behaviourally identical to golden,
    and would silently turn the discrimination check into a no-op."""
    src = "module m; // add: a + b\nassign y = a & b; endmodule\n"
    out, what = mutate(src)
    assert "// add: a + b" in out
    assert "&" not in out.split("//")[1].split("\n")[1] or "|" in out
    assert "becomes" in what


def test_strings_and_directives_are_left_alone():
    src = '`include "defs_a+b.v"\nmodule m; $display("a+b"); assign y = a + b; endmodule\n'
    out, _ = mutate(src)
    assert '`include "defs_a+b.v"' in out
    assert '$display("a+b")' in out
    assert "assign y = a - b" in out


def test_it_refuses_rather_than_returning_golden_unchanged():
    """Silently returning the input would make every discrimination check pass."""
    with pytest.raises(SystemExit):
        mutate("module m; endmodule\n", 99)
