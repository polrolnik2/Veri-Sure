"""Prompt-cache accounting, and the gate that makes a cache miss visible.

Fanning a stage out to one small call per item only works because every call
shares a byte-identical prefix that the provider caches. Measured against the
live gateway on the real `i2c_master_bit_ctrl` spec, a 20,963-character prefix
(~5,240 tokens) reports:

    REQ-0000  in=5011  cached=0
    REQ-0001  in=5008  cached=0
    REQ-0002  in=4991  cached=4864   97%
    REQ-0003  in=5024  cached=4864   97%

At ~400-600 calls per node that is the difference between ~110k billed input
tokens and ~3.6M.

**The failure mode is silent, which is the entire reason this module exists.**
If the prefix stops matching -- a header that interpolates an index, a dict
serialised in a different key order, a repair round that prepends its issues --
every call still succeeds, every artifact still validates, every gate still
passes. The run is merely 30x more expensive. Nothing notices unless something
is built to notice, so the cache is accounted like a correctness property rather
than watched like a metric.

Two accounting rules that stop the number from lying:

* **warm-up calls are excluded, and the report says how many.** A cold prefix
  misses on its first calls by construction; folding those into the rate makes a
  healthy stage look broken and hides the difference between "warming" and
  "never warmed".
* **rates are keyed by `(stage family, model)`.** The escalation ladder moves a
  failing fragment to a different model, whose cache is separate. Pooling those
  lets one escalated miss drag a stage under the threshold, and lets a stage
  that quietly switched model hide behind another's hits.

  *Family*, not the raw stage name, and that distinction was found the hard way.
  A fanned-out stage names each call after its item -- `classify_869`,
  `s2_REQ-0004` -- so keying on the raw name gave 65 keys of one call each, every
  one of them "too few calls to judge", and the report gate was inert on exactly
  the runs it exists for. The offline tests missed it because they passed a
  uniform stage name. `family()` strips the item suffix, and a test now asserts
  the fan-out shape rather than the convenient one.
"""

from __future__ import annotations

import re

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

#: Calls at the head of each (stage, model) that are expected to miss. Measured:
#: the first two calls of a cold prefix reported cached=0, the third onward 97%.
WARMUP_CALLS = 2

#: Below this, after warm-up, the node's report fails. Not the run: the artifacts
#: are fine and the cost is already spent, so discarding work would compound the
#: problem rather than surface it.
MIN_HIT_RATE = 0.80

#: Fewer calls than this and a rate is noise, so no verdict is issued.
MIN_CALLS_FOR_VERDICT = 8


#: What an ITEM suffix looks like: a uid (`REQ-0004`, `TP-0012`) or a bare index
#: (`869`). Everything before the first one is the family.
_ITEM = re.compile(r"^(?:[A-Z]{2,4}-\d+|\d+)$")


def family(stage: str) -> str:
    """The stage a per-item call belongs to: `classify_869` -> `classify`.

    Split at the first ITEM segment rather than at the first underscore, because
    a family can have two words. `normalize_indirect_REQ-0002` is the case that
    forced this: splitting on the first underscore pooled the indirect-resolution
    pass with the first normalisation pass, and THE TWO HAVE DIFFERENT SHARED
    PREFIXES -- different system text, different port note -- so they warm
    separately and cache separately. Pooled, a cold second pass hides behind a
    warm first one and the report says nothing about the stage that was added.

    That is the same defect this module's docstring already records one level
    down, where keying on the raw stage name gave 65 keys of one call each and
    made the gate inert on exactly the runs it exists for.
    """
    parts = stage.split("_")
    kept: list[str] = []
    for part in parts:
        if _ITEM.match(part):
            break
        kept.append(part)
    return "_".join(kept) or stage


@dataclass(frozen=True)
class Call:
    stage: str
    model: str
    input_tokens: int
    cached_tokens: int

    @property
    def hit_rate(self) -> float:
        return self.cached_tokens / self.input_tokens if self.input_tokens else 0.0


@dataclass
class StageStats:
    stage: str
    model: str
    calls: list[Call] = field(default_factory=list)

    @property
    def warmup(self) -> list[Call]:
        return self.calls[:WARMUP_CALLS]

    @property
    def steady(self) -> list[Call]:
        return self.calls[WARMUP_CALLS:]

    @property
    def hit_rate(self) -> float:
        """Over the steady-state calls only. See the module docstring."""
        total = sum(c.input_tokens for c in self.steady)
        return sum(c.cached_tokens for c in self.steady) / total if total else 0.0

    @property
    def verdict(self) -> str:
        if len(self.calls) < MIN_CALLS_FOR_VERDICT:
            return "too_few_calls"
        return "ok" if self.hit_rate >= MIN_HIT_RATE else "below_threshold"

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "model": self.model,
            "calls": len(self.calls),
            "warmup_calls_excluded": len(self.warmup),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "cached_tokens": sum(c.cached_tokens for c in self.calls),
            "steady_input_tokens": sum(c.input_tokens for c in self.steady),
            "steady_cached_tokens": sum(c.cached_tokens for c in self.steady),
            "hit_rate": round(self.hit_rate, 4),
            "verdict": self.verdict,
        }


@dataclass
class CacheStats:
    """Accumulates every call, keyed by `(stage family, model)`."""

    by_key: dict[tuple[str, str], StageStats] = field(default_factory=dict)

    def record(self, *, stage: str, model: str, input_tokens: int,
               cached_tokens: int | None) -> Call:
        fam = family(stage)
        call = Call(fam, model, int(input_tokens or 0), int(cached_tokens or 0))
        key = (fam, model)
        self.by_key.setdefault(key, StageStats(fam, model)).calls.append(call)
        return call

    def record_usage(self, *, stage: str, model: str, usage) -> Call | None:
        """Pull the counts out of an OpenAI usage object of either API shape.

        Chat completions report `prompt_tokens` /
        `prompt_tokens_details.cached_tokens`; the Responses API reports
        `input_tokens` / `input_tokens_details.cached_tokens`. Both are handled
        because specflow runs on whichever the gateway routes, and a port that
        silently recorded zeros for one of them would look exactly like a cache
        that stopped working.
        """
        if usage is None:
            return None
        total = _first_int(usage, ("input_tokens", "prompt_tokens"))
        details = (
            _attr(usage, "input_tokens_details")
            or _attr(usage, "prompt_tokens_details")
        )
        cached = _first_int(details, ("cached_tokens",)) if details is not None else 0
        if total is None:
            return None
        return self.record(stage=stage, model=model, input_tokens=total,
                           cached_tokens=cached or 0)

    # -------------------------------------------------------------- reporting

    def failing(self) -> list[StageStats]:
        return [s for s in self.by_key.values() if s.verdict == "below_threshold"]

    def to_dict(self) -> dict:
        stages = [s.to_dict() for s in self.by_key.values()]
        billed = sum(s["input_tokens"] - s["cached_tokens"] for s in stages)
        return {
            "warmup_calls_excluded_per_stage": WARMUP_CALLS,
            "min_hit_rate": MIN_HIT_RATE,
            "min_calls_for_verdict": MIN_CALLS_FOR_VERDICT,
            "stages": stages,
            "total_calls": sum(s["calls"] for s in stages),
            "total_input_tokens": sum(s["input_tokens"] for s in stages),
            "total_cached_tokens": sum(s["cached_tokens"] for s in stages),
            "billed_input_tokens": billed,
            "ok": not self.failing(),
        }

    def write(self, run_dir: Path) -> Path:
        out = Path(run_dir) / "specflow" / "cache_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return out

    def render(self) -> str:
        """A table someone will actually read, with nothing quietly filtered.

        The excluded warm-up count is printed per row rather than mentioned once
        in a docstring, so a rate is never quoted over a population whose
        filtering is invisible.
        """
        if not self.by_key:
            return "no model calls recorded"
        rows = [f"{'stage':<12} {'model':<16} {'calls':>6} {'input':>10} "
                f"{'cached':>10} {'hit%':>6}  verdict"]
        for s in sorted(self.by_key.values(), key=lambda x: (x.stage, x.model)):
            d = s.to_dict()
            rows.append(
                f"{d['stage']:<12} {d['model']:<16} {d['calls']:>6} "
                f"{d['input_tokens']:>10,} {d['cached_tokens']:>10,} "
                f"{100 * d['hit_rate']:>5.1f}  {d['verdict']}"
                + (f"  (first {d['warmup_calls_excluded']} excluded as warm-up)"
                   if d["warmup_calls_excluded"] else "")
            )
        d = self.to_dict()
        rows.append(
            f"{'TOTAL':<12} {'':<16} {d['total_calls']:>6} "
            f"{d['total_input_tokens']:>10,} {d['total_cached_tokens']:>10,} "
            f"      billed {d['billed_input_tokens']:,}"
        )
        return "\n".join(rows)


def _attr(obj, name: str, default=None):
    """Read `name` off a usage object of ANY shape, without raising.

    `getattr(obj, name, default)` IS NOT SAFE HERE, and the three-argument form
    reads as though it were. agentscope's `ChatUsage` subclasses `dict` via
    `DictMixin`, so its `__getattr__` is `self[name]` and a missing key raises
    KeyError -- while `getattr`'s default only absorbs AttributeError.

    Measured, on the first live call of a full run: `getattr(usage,
    "input_tokens_details", None)` raised `KeyError: 'input_tokens_details'`
    inside the usage accumulator, killing the leaf before any artifact existed.
    The run then exited 0, because the leaf exception is caught and reported as
    a result -- so the whole failure surfaced as a successful run that happened
    to produce nothing.

    A Mapping is read as a mapping, everything else by attribute, and both
    swallow only lookup failure -- never a genuine error from a property.
    """
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except (AttributeError, KeyError, TypeError):
        return default


def _first_int(obj, names: tuple[str, ...]) -> int | None:
    for name in names:
        value = _attr(obj, name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None
