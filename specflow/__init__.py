"""Spec-grounded verification pipeline for Veri-Sure.

Chain: spec text -> requirements -> testplan -> coverage model -> verdict.

Every link is produced by an agent and certified by a deterministic gate in
`assure.py`. The agent never decides whether its own output covered the spec.
"""

__all__ = ["schema", "ids", "assure"]
