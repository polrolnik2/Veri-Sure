"""G8: mutation qualification. Can this suite detect a behaviour change at all?

G7 asks whether every spec testpoint was exercised. G8 asks the complementary
question the spec cannot answer, because a suite can cover every testpoint and
still be unable to fail.

**Runs once, at acceptance -- never per iteration.** mcy re-runs the whole suite
once per mutant, so at 40-100 mutants that is 40-100 full cocotb runs. G7 is a
dict lookup; this is minutes. So G7 produces a *provisional* accept and G8
converts it to a final one.

Mutate the candidate, not a golden. GateTruth mutates a reference and concludes
agentic use is impractical because a reference is required; it is not. "This
mutant provably changes observable behaviour AND the suite still passes" convicts
the *suite*, whatever the base design's correctness. mcy's `test_eq` leg is the
formal filter that makes the inference sound -- it separates UNCOVERED from
NOCHANGE, an equivalent mutant correctly discarded. What is given up is that a
kill no longer evidences the candidate is right, which is G6's and G7's job.

A surviving mutant is a **witness**, not a score: a concrete perturbation the
suite cannot see, which points at the missing check far more precisely than an
uncovered bin does.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # noqa: S404 -- invoking known local tools
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: mcy's four tags. EQGAP is free gold: the suite fails while the design is
#: provably unchanged, which means the *harness* is broken -- a flakiness and
#: over-constraint detector obtained from a gate already being paid for, with no
#: equivalent anywhere in the current system.
COVERED, UNCOVERED, NOCHANGE, EQGAP = "COVERED", "UNCOVERED", "NOCHANGE", "EQGAP"


@dataclass(frozen=True)
class Mutant:
    mutation_id: str
    tag: str
    spec: str = ""


@dataclass
class QualifyReport:
    tags: dict[str, int] = field(default_factory=dict)
    survivors: list[Mutant] = field(default_factory=list)
    eqgaps: list[Mutant] = field(default_factory=list)
    total: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        """Any surviving mutant or any harness gap blocks final acceptance."""
        return not self.error and not self.survivors and not self.eqgaps

    @property
    def killed(self) -> int:
        return self.tags.get(COVERED, 0)

    @property
    def graded(self) -> int:
        """Denominator excludes equivalent mutants, which prove nothing."""
        return self.tags.get(COVERED, 0) + self.tags.get(UNCOVERED, 0)

    @property
    def summary(self) -> str:
        if self.error:
            return f"qualification did not run: {self.error}"
        if not self.graded:
            return "no behaviour-changing mutants were generated"
        # Raw counts, never a bare percentage: a rate invites the Goodhart
        # effect GateTruth observed the moment its kill rate became a target.
        return (
            f"killed {self.killed}/{self.graded} behaviour-changing mutants "
            f"({self.tags.get(NOCHANGE, 0)} equivalent, "
            f"{self.tags.get(EQGAP, 0)} harness gaps)"
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "tags": self.tags,
                "killed": self.killed,
                "graded": self.graded,
                "survivors": [asdict(m) for m in self.survivors],
                "eqgaps": [asdict(m) for m in self.eqgaps],
                "total": self.total,
                "error": self.error,
            },
            indent=2,
        ) + "\n"


CONFIG_TEMPLATE = """\
[options]
size {size}
tags {covered} {uncovered} {nochange} {eqgap}

[script]
read -sv {rtl_name}
prep -top {top}

[files]
{rtl_name}

[logic]
tb_okay = (result("test_sim") == "PASS")
eq_okay = (result("test_eq") == "PASS")

if tb_okay and not eq_okay:
    tag("{uncovered}")
elif not tb_okay and not eq_okay:
    tag("{covered}")
elif tb_okay and eq_okay:
    tag("{nochange}")
elif not tb_okay and eq_okay:
    tag("{eqgap}")
else:
    assert 0

[report]
if tags("{eqgap}"):
    print("EQGAP: %d" % tags("{eqgap}"))
if tags("{covered}") + tags("{uncovered}"):
    print("Coverage: %.2f%%" % (100.0 * tags("{covered}") /
          (tags("{covered}") + tags("{uncovered}"))))

[test test_sim]
expect PASS FAIL
run bash $PRJDIR/test_sim.sh

[test test_eq]
expect PASS FAIL
run bash $PRJDIR/test_eq.sh
"""

TEST_SIM = """\
#!/bin/bash
exec 2>&1
set -e
bash $SCRIPTS/create_mutated.sh -o mutated.sv
if {runner} --rtl "$PWD/mutated.sv" --quiet; then
  echo "1 PASS" >> output.txt
else
  echo "1 FAIL" >> output.txt
fi
exit 0
"""

TEST_EQ = """\
#!/bin/bash
exec 2>&1
set -ex
bash $SCRIPTS/create_mutated.sh -c -o mutated.il
ln -sf $PRJDIR/test_eq.sv $PRJDIR/test_eq.sby .
sby -f test_eq.sby
gawk "{{ print 1, \\$1; }}" test_eq/status >> output.txt
exit 0
"""

_MUTANT_RE = re.compile(r"^\s*(\d+)\s+(\w+)\s*(.*)$")


def tools_available() -> tuple[bool, str]:
    for tool in ("mcy", "yosys", "sby", "gawk"):
        if not shutil.which(tool):
            return False, f"{tool} not on PATH"
    return True, ""


def write_project(
    *,
    workdir: Path,
    rtl_path: Path,
    top: str,
    runner_cmd: str,
    size: int = 40,
) -> Path:
    """Lay out an mcy project whose `test_sim` invokes the existing suite.

    Nothing about the suite changes: mcy calls the same runner the debug loop
    does, against a mutated RTL file.
    """
    workdir = Path(workdir)
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    rtl_name = Path(rtl_path).name
    shutil.copy(rtl_path, workdir / rtl_name)

    (workdir / "config.mcy").write_text(
        CONFIG_TEMPLATE.format(
            size=size, rtl_name=rtl_name, top=top,
            covered=COVERED, uncovered=UNCOVERED, nochange=NOCHANGE, eqgap=EQGAP,
        ),
        encoding="utf-8",
    )
    (workdir / "test_sim.sh").write_text(
        TEST_SIM.format(runner=runner_cmd), encoding="utf-8"
    )
    (workdir / "test_eq.sh").write_text(TEST_EQ, encoding="utf-8")
    for script in ("test_sim.sh", "test_eq.sh"):
        (workdir / script).chmod(0o755)
    return workdir


def parse_status(text: str) -> tuple[dict[str, int], list[Mutant]]:
    """Read `mcy status` output into tag counts and the tagged mutants."""
    tags: dict[str, int] = {}
    mutants: list[Mutant] = []
    for line in text.splitlines():
        m = re.search(r'cached "(\w+)" results for "(\w+)"', line)
        if m:
            continue
        m = re.match(r"^\s*(\w+):\s*(\d+)\s*$", line)
        if m and m.group(1) in {COVERED, UNCOVERED, NOCHANGE, EQGAP}:
            tags[m.group(1)] = int(m.group(2))
    return tags, mutants


def run_qualification(
    *,
    rtl_path: Path,
    top: str,
    runner_cmd: str,
    workdir: Path,
    size: int = 40,
    timeout_s: int = 1800,
) -> QualifyReport:
    """Run mcy end to end. Any tool problem is an error, never a silent pass."""
    ok, why = tools_available()
    if not ok:
        return QualifyReport(error=why)

    project = write_project(
        workdir=workdir, rtl_path=rtl_path, top=top,
        runner_cmd=runner_cmd, size=size,
    )

    try:
        subprocess.run(  # noqa: S603
            ["mcy", "init"], cwd=project, capture_output=True,
            timeout=300, check=False,
        )
        subprocess.run(  # noqa: S603
            ["mcy", "run", "-j", "2"], cwd=project, capture_output=True,
            timeout=timeout_s, check=False,
        )
        status = subprocess.run(  # noqa: S603
            ["mcy", "status"], cwd=project, capture_output=True,
            timeout=300, check=False, text=True,
        )
    except subprocess.TimeoutExpired as exc:
        return QualifyReport(error=f"mcy timed out: {exc}")

    tags, mutants = parse_status(status.stdout or "")
    survivors = [m for m in mutants if m.tag == UNCOVERED]
    eqgaps = [m for m in mutants if m.tag == EQGAP]

    # Tag counts are authoritative even when per-mutant detail is unavailable:
    # a suite that missed something must block regardless of how much detail the
    # report could recover.
    if not survivors and tags.get(UNCOVERED, 0):
        survivors = [
            Mutant(f"unknown_{i}", UNCOVERED) for i in range(tags[UNCOVERED])
        ]
    if not eqgaps and tags.get(EQGAP, 0):
        eqgaps = [Mutant(f"unknown_{i}", EQGAP) for i in range(tags[EQGAP])]

    return QualifyReport(
        tags=tags, survivors=survivors, eqgaps=eqgaps,
        total=sum(tags.values()),
    )
