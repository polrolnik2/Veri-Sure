"""Join simulation results against the frozen denominator, and categorise gaps.

Two coverage streams exist and only one of them gates. Functional coverage --
which bins were hit -- is a Python dict written by the runtime, and it is the
only input to the accept decision. Code coverage from Verilator is a diagnostic:
toggle coverage is a good repair payload but a bad accept criterion, because
coverage is an unreliable indicator in the bug-exposure regime, which is where
this pipeline permanently lives.

Gap categories are assigned by script wherever that is possible. Only the
genuinely ambiguous one -- a bin a testcase targets that still never hit -- needs
a model, and it is the category GoGoTB reports its agent failing at most often.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .schema import TestpointResult

#: Mechanically determinable categories, plus the one that is not.
GapCategory = str

CHECK_FAILED = "check_failed"
NO_TESTCASE = "no_testcase"
UNREACHABLE_PROVED = "unreachable_proved"
STIMULUS_GAP = "stimulus_gap"


@dataclass(frozen=True)
class BinStatus:
    bin_uid: str
    hit: bool
    category: GapCategory | None = None
    disposition: dict | None = None


@dataclass
class CoverageReport:
    denominator: list[str] = field(default_factory=list)
    statuses: dict[str, BinStatus] = field(default_factory=dict)

    @property
    def uncovered(self) -> list[str]:
        return sorted(u for u, s in self.statuses.items() if not s.hit)

    @property
    def undisposed(self) -> list[str]:
        """Uncovered bins with no recorded disposition -- the ones that block."""
        return sorted(
            u for u, s in self.statuses.items() if not s.hit and s.disposition is None
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "denominator": self.denominator,
                "bins": {
                    u: {
                        "hit": s.hit,
                        "category": s.category,
                        "disposition": s.disposition,
                    }
                    for u, s in sorted(self.statuses.items())
                },
            },
            indent=2,
        ) + "\n"


def freeze_denominator(bins: list[dict], path: Path) -> list[str]:
    """Write the denominator once, at loop entry, and read it forever after.

    This is a file rather than a convention because it is the mechanism that
    makes bin padding impossible. The coverage model may grow -- `add_testcase`
    can introduce checks -- but the denominator cannot, so an agent cannot raise
    its coverage percentage by inventing bins nobody asked for.
    """
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["bins"]

    uids = sorted(b["uid"] for b in bins)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bins": uids}, indent=2) + "\n", encoding="utf-8")
    return uids


def _targeted_bins(testcases: list[dict]) -> set[str]:
    return {t for tc in testcases for t in (tc.get("targets") or [])}


def build_report(
    *,
    denominator: list[str],
    results: dict[str, TestpointResult],
    dispositions: dict[str, dict] | None = None,
    testcases: list[dict] | None = None,
) -> CoverageReport:
    dispositions = dispositions or {}
    hit: set[str] = set()
    failed_bins: set[str] = set()

    for res in results.values():
        hit |= set(res.bins_hit)
        if res.status == "FAIL":
            failed_bins |= set(res.bins_hit)

    targeted = _targeted_bins(testcases or [])
    statuses: dict[str, BinStatus] = {}

    for uid in denominator:
        was_hit = uid in hit
        disposition = dispositions.get(uid)

        if was_hit:
            category = CHECK_FAILED if uid in failed_bins else None
        elif disposition is not None:
            category = UNREACHABLE_PROVED
        elif testcases is not None and uid not in targeted:
            # Mechanical: nothing was ever written to reach it.
            category = NO_TESTCASE
        else:
            # A testcase targets it and it still never hit. This is the only
            # category that needs judgement, and the one GoGoTB's agent failed
            # at for 16 of its 24 residual gaps.
            category = STIMULUS_GAP

        statuses[uid] = BinStatus(uid, was_hit, category, disposition)

    return CoverageReport(denominator=list(denominator), statuses=statuses)


# ------------------------------------------------------- code coverage (diagnostic)

_INFO_SF = re.compile(r"^SF:(.+)$")
_INFO_DA = re.compile(r"^DA:(\d+),(\d+)$")


def parse_lcov_info(path: Path) -> dict[str, list[int]]:
    """Uncovered source lines per file, from `verilator_coverage --write-info`.

    Diagnostic only -- never a gate criterion. Returned so the repair agent can
    be told "this region never executed", which is a far better payload than a
    trace slice.
    """
    uncovered: dict[str, list[int]] = {}
    current = ""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = _INFO_SF.match(line)
        if m:
            current = m.group(1)
            uncovered.setdefault(current, [])
            continue
        m = _INFO_DA.match(line)
        if m and current and int(m.group(2)) == 0:
            uncovered[current].append(int(m.group(1)))
    return {k: v for k, v in uncovered.items() if v}


def merge_coverage(dats: list[Path], out_dat: Path, out_info: Path) -> bool:
    """Merge per-iteration .dat files and emit lcov .info.

    Input files are positional: `-read` appears in Verilator 5.020's perl docs
    and is rejected by 5.038.
    """
    import subprocess  # noqa: S404 -- invoking a known local tool

    dats = [d for d in dats if Path(d).exists()]
    if not dats:
        return False

    out_dat, out_info = Path(out_dat), Path(out_info)
    out_dat.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(  # noqa: S603
            ["verilator_coverage", "--write", str(out_dat), *[str(d) for d in dats]],
            check=True, capture_output=True, timeout=120,
        )
        subprocess.run(  # noqa: S603
            ["verilator_coverage", "--write-info", str(out_info), str(out_dat)],
            check=True, capture_output=True, timeout=120,
        )
    except Exception:  # noqa: BLE001
        return False
    return out_info.exists()
