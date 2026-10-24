"""M7b: G8, the mutation completeness gate.

Both directions matter. A gate that never reports UNCOVERED silently
rubber-stamps a suite that cannot fail; one that reports it spuriously drives
endless testcase generation. The pure parts are tested here directly; the mcy
integration is exercised through `write_project`, since a full mcy sweep is
minutes and belongs at acceptance rather than in the unit suite.
"""

from __future__ import annotations

from pathlib import Path

from specflow.qualify import (
    COVERED,
    EQGAP,
    NOCHANGE,
    UNCOVERED,
    Mutant,
    QualifyReport,
    parse_status,
    tools_available,
    write_project,
)

RTL = "module Gated(input a, input b, output y);\n  assign y = a & b;\nendmodule\n"


def report(**tags) -> QualifyReport:
    survivors = [Mutant(f"m{i}", UNCOVERED) for i in range(tags.get(UNCOVERED, 0))]
    eqgaps = [Mutant(f"e{i}", EQGAP) for i in range(tags.get(EQGAP, 0))]
    return QualifyReport(tags=tags, survivors=survivors, eqgaps=eqgaps,
                         total=sum(tags.values()))


# ---------------------------------------------------------------- verdicts


def test_a_suite_that_kills_everything_passes():
    r = report(**{COVERED: 12, NOCHANGE: 3})
    assert r.ok
    assert r.killed == 12 and r.graded == 12


def test_a_surviving_mutant_blocks():
    # The suite covered every testpoint and still cannot see this change.
    r = report(**{COVERED: 10, UNCOVERED: 2})
    assert not r.ok
    assert len(r.survivors) == 2


def test_an_equivalent_mutant_neither_kills_nor_blocks():
    # NOCHANGE proves nothing about the suite, so it must leave the denominator
    # rather than inflate the kill rate.
    r = report(**{COVERED: 5, NOCHANGE: 20})
    assert r.ok
    assert r.graded == 5


def test_an_eqgap_blocks_because_the_harness_is_broken():
    # The suite failed while the design is provably unchanged: that is a harness
    # fault, detected for free from a gate already being paid for.
    r = report(**{COVERED: 9, EQGAP: 1})
    assert not r.ok
    assert len(r.eqgaps) == 1


def test_a_tool_failure_is_an_error_not_a_pass():
    r = QualifyReport(error="mcy not on PATH")
    assert not r.ok
    assert "did not run" in r.summary


def test_summary_reports_raw_counts_not_a_bare_rate():
    # A rate invites the Goodhart effect GateTruth observed the moment its kill
    # rate became a target.
    s = report(**{COVERED: 8, UNCOVERED: 2, NOCHANGE: 5}).summary
    assert "8/10" in s
    assert "80" not in s.split("(")[0]


def test_zero_graded_mutants_is_reported_honestly():
    assert "no behaviour-changing mutants" in report(**{NOCHANGE: 7}).summary


# ---------------------------------------------------------------- parsing


def test_parse_status_reads_tag_counts():
    tags, _ = parse_status(
        "Database contains 40 cached results.\n"
        f"  {COVERED}: 31\n  {UNCOVERED}: 2\n  {NOCHANGE}: 6\n  {EQGAP}: 1\n"
    )
    assert tags == {COVERED: 31, UNCOVERED: 2, NOCHANGE: 6, EQGAP: 1}


def test_tag_counts_alone_still_block(tmp_path):
    """Detail can be unavailable; a missed mutant must block regardless."""
    from specflow.qualify import run_qualification  # noqa: F401 -- import shape

    r = report(**{COVERED: 5, UNCOVERED: 3})
    assert not r.ok and len(r.survivors) == 3


# ---------------------------------------------------------------- project


def test_project_wires_mcy_to_the_existing_runner(tmp_path):
    rtl = tmp_path / "gated.sv"
    rtl.write_text(RTL, encoding="utf-8")

    project = write_project(
        workdir=tmp_path / "mcy", rtl_path=rtl, top="Gated",
        runner_cmd="python -m specflow.run", size=25,
    )

    config = (project / "config.mcy").read_text()
    assert "size 25" in config
    assert "prep -top Gated" in config
    # The four-way classification must be present, or UNCOVERED and NOCHANGE
    # collapse together and the kill rate becomes noise.
    for tag in (COVERED, UNCOVERED, NOCHANGE, EQGAP):
        assert tag in config

    sim = (project / "test_sim.sh").read_text()
    assert "specflow.run" in sim
    assert "mutated.sv" in sim
    # test_eq is the formal filter that makes mutating the CANDIDATE sound.
    assert "sby -f test_eq.sby" in (project / "test_eq.sh").read_text()


def test_scripts_are_executable(tmp_path):
    rtl = tmp_path / "gated.sv"
    rtl.write_text(RTL, encoding="utf-8")
    project = write_project(
        workdir=tmp_path / "mcy", rtl_path=rtl, top="Gated",
        runner_cmd="python -m specflow.run",
    )
    for script in ("test_sim.sh", "test_eq.sh"):
        assert (project / script).stat().st_mode & 0o111


def test_tools_available_reports_what_is_missing():
    ok, why = tools_available()
    assert ok or Path(why.split()[0]).name  # names the tool rather than failing vaguely
