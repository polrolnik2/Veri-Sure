"""Bridge between `eda_agent`'s node-level run and the specflow pipeline.

Kept in `specflow/` rather than threaded through `top_agent.py` so the two can be
tested apart: everything here is a pure function of a run directory plus a model
port, and none of it needs the orchestrator.

The one thing this genuinely fixes on the `eda_agent` side is the spec. `spec:
str` is already a required parameter of `TopAgent.run` (`:963-973`) and both
entry points supply it, but only `cli.py:74` writes it to disk. specflow reads
`prompt.txt`, so `ensure_prompt_file` makes the benchmark path carry it too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import logging

from .cache_stats import CacheStats
from .coverage import build_report, freeze_denominator
from .gate import evaluate
from .model_io import PortSettings, make_port
from .normalize import run_normalize_fanout
from .normalize import write_artifacts as write_normalized
from .refmodel.compose import choose_base, run_refmodel
from .refmodel.compose import write_artifacts as write_refmodel
from .refmodel.validate import validate_source
from .run import reconcile, run_suite
from .s1_requirements import RequirementsOutput, S1Result
from .s1_requirements import gate as gate_s1
from .s1_requirements import renumber as renumber_reqs
from .s1_requirements import run_s1
from .s1_requirements import write_artifacts as write_s1
from .s2_testplan import TestplanOutput
from .s2_testplan import gate as gate_s2
from .s2_testplan import renumber as renumber_tps
from .s2_testplan import run_s2, run_s2_fanout
from .s2_testplan import write_artifacts as write_s2
from .s3_coverage import CoverageOutput
from .s3_coverage import gate as gate_s3
from .s3_coverage import renumber as renumber_cov
from .s3_coverage import run_s3, run_s3_fanout
from .s3_coverage import write_artifacts as write_s3
from .schema import GateVerdict, Issue, has_errors
from .stage import StageResult
from .testcase_agent import (
    STIMULUS_MAX_STEPS,
    SuiteStimulus,
    gate_suite,
    run_suite_stimulus,
    run_suite_stimulus_fanout,
    stimulus_by_tp,
    starved_by_divider,
    stimulus_diagnostics,
    unrealisable_reset,
)
from .tb.render import gate_g5, render_suite

logger = logging.getLogger(__name__)


class _Reused(Exception):
    """A cached artifact was good; skip the generation below it.

    An exception rather than a flag because both blocks it guards are `try`
    bodies already, and threading a boolean through them would put the cache
    check and the thing it guards in different places.
    """


def ensure_prompt_file(run_dir: Path, spec: str) -> Path:
    """Persist the spec so specflow (and any offline replay) can read it.

    `cli.py` does this for the `run` subcommand; the benchmark path builds its
    prompt separately and never writes it, so a benchmark node had no spec on
    disk at all.
    """
    path = Path(run_dir) / "prompt.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(spec.rstrip() + "\n", encoding="utf-8")
    return path


@dataclass
class BuildResult:
    ok: bool
    stage: str = ""
    issues: list[Issue] | None = None
    suite_dir: Path | None = None
    refmodel_path: Path | None = None
    bins: list[dict] | None = None
    #: Non-fatal. A stimulus failure falls back to `default_stimulus` rather
    #: than aborting: a weaker sweep beats no node at all, and the coverage
    #: gate is what reports the gap it leaves.
    stimulus_issues: list[Issue] | None = None
    #: Prompt-cache accounting for this build. Its verdict fails the *report*,
    #: never the run -- the artifacts are fine and the cost is already spent.
    cache: object | None = None

    @property
    def reason(self) -> str:
        if self.ok:
            return "artifacts built"
        n = len(self.issues or ())
        return f"{self.stage} gate failed with {n} issue(s)"


def _reuse(
    run_dir: Path, artifact: str, model, regate
) -> tuple[object, list[Issue]] | None:
    """A certified artifact from a previous run, re-gated rather than trusted.

    The point of reuse is to skip the *model call*, which costs minutes, not the
    *gate*, which is pure code and costs nothing. Re-running it is what keeps
    this honest in both directions: a cached artifact that a since-tightened gate
    would now reject is regenerated, and one that a since-corrected gate would
    now accept is kept. The G1 whitespace fix is the live example -- the same
    `requirements.json` scored 2 errors before it and 0 after, so trusting the
    recorded verdict would have thrown away a usable artifact.

    Returns None when there is nothing usable, and the caller regenerates.
    """
    path = Path(run_dir) / "specflow" / artifact
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        out = model.model_validate(data)
    except Exception:  # noqa: BLE001
        return None
    issues = regate(out)
    if has_errors(issues):
        return None
    return out, issues


def _run_divided_s1(
    *, run_dir: Path, spec: str, contract_json: str, port, max_repairs: int,
    reuse: bool,
) -> tuple[list[dict], list[Issue], bool]:
    """S1 by division, and the artifact it leaves behind.

    Writes the same `requirements.json` the generative arm writes, so every
    downstream stage, the `reuse` path and the committed baselines all read one
    shape regardless of which arm produced it. What differs is `s1_gate.json`,
    which records G1' per unit rather than G1 over the whole spec.

    Returns `(requirements, issues, regenerated)`. The caller needs the last one:
    a stage that was reused does not invalidate the stages after it, and treating
    it as though it did is how `--reuse` ends up rebuilding everything downstream
    of a cache hit.
    """
    from .divide import coverage as unit_coverage
    from .s1_classify import divide_and_classify

    out_dir = Path(run_dir) / "specflow"
    reqs_path = out_dir / "requirements.json"
    if reuse and reqs_path.is_file():
        try:
            data = json.loads(reqs_path.read_text(encoding="utf-8"))
            cached = data.get("requirements") if isinstance(data, dict) else data
            if cached:
                return list(cached), [], False
        except (OSError, json.JSONDecodeError):
            pass

    units, results, reqs = divide_and_classify(
        spec=spec, contract_json=contract_json, port=port, max_repairs=max_repairs,
    )
    issues = [i for r in results for i in r.issues]

    covered, total, gaps = unit_coverage(spec, units)
    out_dir.mkdir(parents=True, exist_ok=True)
    reqs_path.write_text(
        json.dumps({"requirements": reqs}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "s1_gate.json").write_text(
        json.dumps(
            {
                "arm": "divide",
                "ok": not has_errors(issues),
                "units": len(units),
                "requirements": len(reqs),
                # Reported, never claimed. The residue between units is
                # whitespace; a gap carrying a word is a divider defect and must
                # be visible rather than rounded away.
                "spec_chars": total,
                "unit_chars": covered,
                "word_carrying_gaps": len(gaps),
                "largest_requirement_chars": max(
                    (s["end"] - s["start"] for r in reqs for s in r["spec_spans"]),
                    default=0,
                ),
                "issues": [
                    {"severity": i.severity, "path": i.path, "message": i.message,
                     "kind": i.kind}
                    for i in issues
                ],
            },
            indent=2, ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    return reqs, issues, True


def build_artifacts(
    *,
    run_dir: Path,
    spec: str,
    contract_json: str,
    model_port: str = "replay",
    max_repairs: int = 3,
    #: The reference model gets its own budget, and a larger default. Its repair
    #: round is the only one whose feedback comes from RUNNING the artifact
    #: rather than from a script checking its shape, and that feedback converges
    #: rather than plateauing. Measured on `i2c_master_bit_ctrl`: blocking
    #: verdicts went 8 -> 4 -> 3 -> 2 over four rounds, monotonically, and the
    #: node then hard-failed on exhaustion with the trajectory still descending.
    #: The budget was the binding constraint, not the model.
    refmodel_max_repairs: int | None = None,
    #: An agent that EDITS the reference model against the frozen requirement
    #: oracles, instead of prose driving a regeneration. Injected as a
    #: Protocol, like `loop.RtlRepair`, so nothing here imports AgentScope.
    #: Absent one, the stage behaves exactly as it always has.
    refmodel_debugger: object | None = None,
    refmodel_judge_turns: int = 3,
    #: A known-good reference model for this design, if one exists. It is the
    #: ONLY input to trust gate 3, and it never reaches the debug agent or the
    #: generator -- it is used solely to throw away oracles that demand
    #: something no correct model does.
    #:
    #: Leaving it unset does not skip a formality. Measured on the a-i2c run,
    #: where it was unset: 22 of 54 trusted oracles (41%) are failed by the
    #: control model that scores 181/181 against golden RTL, and 10 of the 18
    #: oracles the debug agent could not discharge were in that set. The agent
    #: spent its attempts on demands that no correct model can satisfy, and
    #: `over_strict: 0` in the trust report read as "none found" when it
    #: actually meant "never looked".
    refmodel_control: str | None = None,
    stimulus_agent: bool = True,
    #: Restate each requirement as activation / observable / expectation, and
    #: Step 7's must-fail leg. Off by default: it costs k model calls per
    #: requirement -- 150 to 230 on i2c -- paid once. What it buys is that
    #: VACUOUS stops being inferred from silence under source mutation and is
    #: earned against a design that actually violates the requirement.
    variants: bool = False,
    #: Strengthening rounds after the debug loop converges: mutate the shipped
    #: model and re-ask any oracle a mutant got past. 0 measures and acts on
    #: nothing, which is how it ships -- the rate has to be known first.
    adequacy_rounds: int = 0,
    reuse: bool = False,
    divide_s1: bool = True,
    fanout: bool = True,
    judge: bool = True,
    #: Every model-call switch, stated by the caller. `None` means the defaults
    #: in `PortSettings` -- never the ambient environment, which is what let a
    #: caller's `--env-file` be overridden by whichever file a stage re-read.
    port_settings: "PortSettings | None" = None,
) -> BuildResult:
    """S1 -> S2 -> S3 -> reference model -> rendered suite, gate by gate.

    Stops at the first gate that fails, and says which. Exhaustion is a hard
    failure everywhere: a stage that could not be certified never propagates a
    partial artifact downstream.

    `divide_s1` swaps the generative S1 for division at authorial boundaries plus
    a per-unit classifier (`divide.py` + `s1_classify.py`); `fanout` does the
    same for S2, S3 and the reference model. Both default off so the generative
    arm stays runnable for A/B on the same task, model and effort -- without
    that, any measured delta could be the decomposition or could be the weather.

    With `reuse`, a stage whose artifact is already on disk and still passes its
    gate is not regenerated. Two rules keep that from going stale: the gate is
    always re-run rather than read from the recorded verdict, and once any stage
    regenerates, every stage after it regenerates too -- a cached S2 is only
    valid against the S1 that produced it.
    """
    run_dir = Path(run_dir)
    ensure_prompt_file(run_dir, spec)
    stats = CacheStats()
    port = make_port(model_port, run_dir / "agent_io", stats, port_settings)
    contract = json.loads(contract_json) if contract_json.strip() else {}

    # Set once a stage regenerates: everything downstream must regenerate too,
    # because a cached artifact is only valid against the upstream that made it.
    stale = not reuse

    if divide_s1:
        # Division: the partition is built by code, so granularity stops being
        # the model's to choose. Its gate is G1' rather than G1, and it has no
        # `RequirementsOutput` to re-validate, so reuse is by artifact presence
        # plus the downstream gates that consume it.
        reqs, s1_issues, regenerated = _run_divided_s1(
            run_dir=run_dir, spec=spec, contract_json=contract_json, port=port,
            max_repairs=max_repairs, reuse=not stale,
        )
        if has_errors(s1_issues):
            return BuildResult(False, "S1", s1_issues)
        # Only when S1 actually regenerated. Setting this unconditionally meant
        # the divided arm could never benefit from `--reuse` downstream: the
        # requirements came back from disk in milliseconds and then S2, S3 and
        # the reference model all re-ran anyway. Measured on one run before the
        # fix -- 72 + 200 calls and about ten minutes, to rebuild artifacts that
        # were already on disk and still passing their gates.
        stale = stale or regenerated
    else:
        cached = None if stale else _reuse(
            run_dir, "requirements.json", RequirementsOutput,
            lambda out: gate_s1(spec, out, contract),
        )
        if cached is not None:
            s1 = S1Result(cached[0], list(cached[1]), 0)
        else:
            stale = True
            s1 = run_s1(spec=spec, contract_json=contract_json, port=port,
                        max_repairs=max_repairs)
            renumber_reqs(s1.output)
            write_s1(run_dir, s1)
        if not s1.ok:
            return BuildResult(False, "S1", s1.issues)

        reqs = [r.model_dump() for r in s1.output.requirements]

    # Normalization runs on the requirements and nothing else, so it sits here
    # rather than later: its output is about S1's artifact, and a stage that
    # reads a requirement should be able to read the normalized form beside it.
    #
    # Never fatal. A requirement that could not be normalized is one nothing
    # knows the activation of, which is exactly today's situation for all of
    # them -- so failing the node over it would make the pipeline strictly worse
    # than before this stage existed.
    normalized_by_uid: dict[str, dict] = {}
    normalized_path = run_dir / "specflow" / "normalized.json"
    if not stale and normalized_path.is_file():
        try:
            normalized_by_uid = {
                n["req_uid"]: n
                for n in json.loads(normalized_path.read_text(encoding="utf-8"))
                .get("normalized", []) if n.get("req_uid")
            }
        except (OSError, ValueError, TypeError):
            normalized_by_uid = {}
    # Not optional any more: the oracle stage reads the normalized form, and
    # the oracle stage is the only thing that produces a verdict at all now.
    try:
        if normalized_by_uid:
            raise _Reused
        normalized, norm_results = run_normalize_fanout(
            requirements=reqs, contract_json=contract_json, contract=contract,
            port=port, max_repairs=max_repairs, fanout=fanout,
        )
    except _Reused:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("normalize: not produced (%r)", exc)
    else:
        write_normalized(run_dir, normalized, norm_results)
        normalized_by_uid = {n.req_uid: n.model_dump() for n in normalized
                             if n.req_uid}

    cached = None if stale else _reuse(
        run_dir, "testplan.json", TestplanOutput, lambda out: gate_s2(reqs, out),
    )
    if cached is not None:
        s2 = StageResult(cached[0], list(cached[1]), 0)
    else:
        stale = True
        if fanout:
            merged, per_item = run_s2_fanout(
                requirements=reqs, contract_json=contract_json, port=port,
                max_repairs=max_repairs)
            s2 = StageResult(merged, [i for r in per_item for i in r.issues],
                             max((r.rounds for r in per_item), default=0))
        else:
            s2 = run_s2(requirements=reqs, contract_json=contract_json, port=port,
                        max_repairs=max_repairs)
            renumber_tps(s2.output)
        write_s2(run_dir, s2)
    if not s2.ok:
        return BuildResult(False, "S2", s2.issues)

    tps = [e.model_dump() for e in s2.output.elements]

    cached = None if stale else _reuse(
        run_dir, "coverage_model.json", CoverageOutput,
        lambda out: gate_s3(tps, out, contract),
    )
    if cached is not None:
        s3 = StageResult(cached[0], list(cached[1]), 0)
    else:
        stale = True
        if fanout:
            merged3, per_item3 = run_s3_fanout(
                testplan=tps, contract_json=contract_json, port=port,
                max_repairs=max_repairs)
            s3 = StageResult(merged3, [i for r in per_item3 for i in r.issues],
                             max((r.rounds for r in per_item3), default=0))
        else:
            s3 = run_s3(testplan=tps, contract_json=contract_json, port=port,
                        max_repairs=max_repairs)
            renumber_cov(s3.output)
        write_s3(run_dir, s3)
    if not s3.ok:
        return BuildResult(False, "S3", s3.issues)

    bins = [b.model_dump() for b in s3.output.bins]
    checks = [c.model_dump() for c in s3.output.checks]

    # Concrete stimulus BEFORE the reference model, not after it.
    #
    # It depends on nothing the refmodel produces -- only on the testplan and
    # the contract, both of which S2/S3 have already written -- and running it
    # first is what lets the judge replay each requirement's own scenario
    # against the model. Judging on the generic sweep alone cannot do that:
    # the sweep varies every input every step, so on i2c_master_bit_ctrl the
    # longest run that could advance the FSM is 0, where one START needs ~26
    # edges. These steps are written to hold a command stable for exactly as
    # long as the design needs.
    stim_by_tp: dict[str, list[dict]] = {}
    stim_issues: list[Issue] = []
    # Reused like every other stage, and for the same reason. Stimulus was the
    # one major artifact never written to `specflow/`, so `--reuse` could not
    # cover it and every rerun paid for it again -- 167 calls on
    # i2c_master_bit_ctrl, the most expensive stage in the pipeline now that it
    # fans out, repeated even when nothing upstream of it had changed.
    stim_cached = None if stale else _reuse(
        run_dir, "stimulus.json", SuiteStimulus,
        lambda out: gate_suite(out, testplan=tps, contract=contract,
                               max_steps=STIMULUS_MAX_STEPS),
    )
    if stim_cached is not None:
        stim_issues = (list(stim_cached[1]) + stimulus_diagnostics(stim_cached[0])
                       + unrealisable_reset(tps)
                       + starved_by_divider(stim_cached[0], contract))
        stim_by_tp = stimulus_by_tp(stim_cached[0])
    elif stimulus_agent:
        # A stimulus failure is not fatal: `default_stimulus` still renders a
        # valid suite, and a weaker sweep is worth more than an aborted node.
        # The gate's EXTEND_TB branch is what reports the resulting gap. This
        # also lets a ReplayPort with no recorded stimulus stage fall through
        # to the old behaviour rather than crashing a fixture-driven run.
        try:
            if fanout:
                # One call per testpoint. Testpoints do not constrain each
                # other, so nothing is lost by splitting -- and monolithic was
                # measured degrading badly at scale: on i2c_master_bit_ctrl's
                # 167 testpoints, three rounds returned stimulus for ten of
                # them and the fourth returned all 167 with one step each.
                merged, per_item = run_suite_stimulus_fanout(
                    testplan=tps, contract=contract, port=port,
                    max_repairs=max_repairs,
                    # The spec quotes behind each testpoint, joined through
                    # `covers`. A testpoint carries no spec of its own.
                    requirements=reqs,
                )
                st = StageResult(
                    merged, [i for r in per_item for i in r.issues],
                    sum(r.rounds for r in per_item),
                )
            else:
                st = run_suite_stimulus(
                    testplan=tps, contract=contract, port=port,
                    max_repairs=max_repairs,
                )
        except Exception as exc:  # noqa: BLE001
            stim_issues = [Issue("warning", "stimulus", f"not generated: {exc!r}")]
        else:
            stim_issues = (list(st.issues) + stimulus_diagnostics(st.output)
                           + unrealisable_reset(tps)
                           + starved_by_divider(st.output, contract))
            stim_by_tp = stimulus_by_tp(st.output)
            if not has_errors(stim_issues):
                (run_dir / "specflow" / "stimulus.json").write_text(
                    json.dumps(st.output.model_dump(), indent=2) + "\n",
                    encoding="utf-8",
                )

    # [O] The requirement oracles, BEFORE the reference model exists.
    #
    # Their isolation from the design used to be a discipline -- a prompt
    # builder with no parameter a design could arrive through, plus a test that
    # reads the prompt back. Running the stage here makes it a fact about time
    # instead: there is no reference model yet, so there is nothing to leak.
    #
    # Never fatal. A run whose oracles could not be produced is the run every
    # run was before this stage existed.
    oracle_set = None
    try:
        from .oracles_stage import load as load_oracles
        from .oracles_stage import run_oracle_stage

        if not stale:
            oracle_set = load_oracles(run_dir)
            if oracle_set is not None:
                logger.info("oracles: %d trusted, reused",
                            len(oracle_set.trusted))
                raise _Reused

        oracle_set = run_oracle_stage(
            requirements=reqs, contract_json=contract_json,
            contract=contract, testplan=tps,
            stimulus_by_tp=stim_by_tp or {},
            port=port, workdir=run_dir / "specflow",
            base=choose_base(contract),
            normalized=normalized_by_uid or None,
            control_source=refmodel_control,
            want_variants=variants, run_dir=run_dir, fanout=fanout,
            # Upstream regenerated, so the frozen oracles are about
            # requirements that no longer exist. Freezing is per requirement
            # SET, not per directory.
            rewrite=stale,
        )
    except _Reused:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("oracles: stage did not complete (%r)", exc)

    # The reference model is validated by executing it, so "re-gate rather than
    # trust" here means re-running G4 against the rendered source on disk.
    refmodel_path = run_dir / "specflow" / "ref_model.py"
    rm_issues: list[Issue] = []
    if stale or not refmodel_path.is_file():
        stale = True
        # The reference model is generated whole, by the configured (strong)
        # model, regardless of `fanout`. Splitting generation was the wrong half
        # to fan out: a model needs global context for ordering, reset priority
        # and shared state, and per-requirement calls removed exactly that. The
        # fan-out moved into the gate, where "does this model satisfy
        # requirement N" is a local question with a local answer.
        rm, source = run_refmodel(
            requirements=reqs, contract_json=contract_json, port=port,
            workdir=run_dir / "specflow" / "_refmodel_check",
            max_repairs=(max_repairs if refmodel_max_repairs is None
                         else refmodel_max_repairs),
            # The judge shares the port -- and therefore the small-model
            # override -- because it is a fanned-out per-item stage like the
            # others. The generator above is the same port but a whole-artifact
            # call; the model split is by `SPECFLOW_SMALL_MODEL`, not by port.
            item_port=port,
            run_dir=run_dir,
            # S2 ran before this, so every testpoint -- and the requirement each
            # one covers -- already exists by the time the judge is asked.
            testplan=tps,
            stimulus_by_tp=stim_by_tp or None,
            debugger=refmodel_debugger,
            max_judge_turns=refmodel_judge_turns,
            control_source=refmodel_control,
            normalized=normalized_by_uid or None,
            oracle_set=oracle_set,
            adequacy_rounds=adequacy_rounds,
        )
        refmodel_path = write_refmodel(run_dir, rm, source)
        rm_issues = list(rm.issues)
        if not rm.ok:
            return BuildResult(False, "refmodel", rm.issues)
    else:
        # The coverage map lives in the recorded gate file, not in the model
        # source -- it is the generator's claim about the source, not part of
        # it. Without it the re-gate reports every requirement as unclaimed and
        # regenerates a model that was fine, which is `--reuse` doing the exact
        # opposite of its job.
        try:
            recorded = json.loads(
                (run_dir / "specflow" / "refmodel_gate.json").read_text(encoding="utf-8")
            )
            covers = recorded.get("covers") or {}
        except (OSError, json.JSONDecodeError):
            covers = {}
        rm_issues = validate_source(
            source=refmodel_path.read_text(encoding="utf-8"),
            requirements=reqs, contract=contract,
            expected_base=choose_base(contract),
            workdir=run_dir / "specflow" / "_refmodel_check",
            coverage=covers,
        )
        if has_errors(rm_issues):
            stale = True
            # The SAME arguments as the generative path above. This branch
            # regenerates a model that failed re-validation, and it was doing so
            # with no judge and no behavioural evidence -- so a `--reuse` run
            # whose recorded model went stale produced a model held to a weaker
            # standard than a fresh run would apply, silently.
            rm, source = run_refmodel(
                requirements=reqs, contract_json=contract_json, port=port,
                workdir=run_dir / "specflow" / "_refmodel_check",
                max_repairs=(max_repairs if refmodel_max_repairs is None
                             else refmodel_max_repairs),
                item_port=port,
                run_dir=run_dir,
                testplan=tps,
                stimulus_by_tp=stim_by_tp or None,
                debugger=refmodel_debugger,
                max_judge_turns=refmodel_judge_turns,
                control_source=refmodel_control,
                normalized=normalized_by_uid or None,
                oracle_set=oracle_set,
                adequacy_rounds=adequacy_rounds,
            )
            refmodel_path = write_refmodel(run_dir, rm, source)
            if not rm.ok:
                return BuildResult(False, "refmodel", rm.issues)

    suite_dir = run_dir / "specflow" / "suite"

    # Stimulus per testpoint, from each element's own prose. Without this every
    # testpoint renders with `default_stimulus` -- one shared deterministic-random
    # sweep -- and the suite becomes N copies of one test under N names. Measured
    # on i2c_master_bit_ctrl: 25 modules, 1 distinct stimulus list, and seven
    # failing testpoints failing on the identical 19 vectors. The testplan's
    # `stimulus` field, which S2 is gated on producing, was consumed by nothing.
    manifest = render_suite(
        testplan=tps, bins=bins, checks=checks, contract=contract, out_dir=suite_dir,
        stimulus_by_tp=stim_by_tp or None,
    )
    g5 = gate_g5(out_dir=suite_dir, manifest=manifest, bins=bins, checks=checks)
    if any(i.severity == "error" for i in g5):
        return BuildResult(False, "G5", g5)

    # Written on the way out of every build, successful or not: a run that
    # failed at S3 still spent whatever it spent, and a cache that stopped
    # working is most likely to be noticed on the run that also went wrong.
    stats.write(run_dir)

    return BuildResult(
        True, suite_dir=suite_dir, refmodel_path=refmodel_path, bins=bins,
        stimulus_issues=stim_issues, cache=stats,
    )


def judge(
    *,
    rtl_path: Path,
    hdl_toplevel: str,
    suite_dir: Path,
    refmodel_path: Path,
    bins: list[dict],
    iteration: int = 0,
    extra_sources: Sequence[Path | str] = (),
    include_dirs: Sequence[Path | str] = (),
) -> tuple[GateVerdict, dict]:
    """One evaluation: run the suite and return the three-valued verdict.

    This is the replacement for `sim_reviewer.sim_review`'s two-valued answer.
    That function decides pass or fail from log markers, so `is_pass=True,
    mismatch_cnt=0` means both "everything was checked and passed" and "nothing
    ran". Here the verdict is data written by the runtime, per testpoint, and
    an unexercised testpoint is its own outcome rather than a silent success.
    """
    suite_dir = Path(suite_dir)
    manifest = json.loads((suite_dir / "manifest.json").read_text(encoding="utf-8"))

    outcome = run_suite(
        rtl_path=rtl_path, hdl_toplevel=hdl_toplevel, suite_dir=suite_dir,
        refmodel_path=refmodel_path, iteration=iteration,
        extra_sources=extra_sources, include_dirs=include_dirs,
    )
    denominator = freeze_denominator(bins, suite_dir / "denominator.json")
    report = build_report(denominator=denominator, results=outcome.results)

    verdict = evaluate(
        results=outcome.results,
        report=report,
        missing_records=reconcile(outcome, manifest),
        build_ok=outcome.build_ok,
        build_log=outcome.build_log,
    )
    return verdict, {
        "results": {u: r.status for u, r in outcome.results.items()},
        "uncovered": report.undisposed,
        "build_ok": outcome.build_ok,
        # The waveform, so a caller can hand the repair agent a real file rather
        # than guess a path. Absent when tracing is off or the build failed.
        "wave_vcd": str(outcome.wave_vcd) if outcome.wave_vcd else None,
    }


def trace_summary(suite_dir: Path, wave_vcd: Path | None = None) -> dict:
    """The failure half of a trace report, from specflow's own records.

    `eda_agent.trace_report` derives `fail_time`, `fail_outputs` and
    `input_window` by parsing a SystemVerilog testbench's mismatch log. This
    backend has no such log -- it has something better, a structured record per
    testpoint -- but nothing was reading it, so every one of those fields
    reached the repair agent null or zero while the data sat on disk.

    `fail_step` replaces `fail_time`: a stimulus step index, which is what a
    specflow failure is actually located by. The waveform is named alongside so
    the agent can go from "step 7 of TP-0031, sda_oen wrong" to the wave.
    """
    payload = failure_payload(suite_dir)
    by_signal: dict[str, int] = {}
    first_step: int | None = None
    total = 0
    for entry in payload:
        for m in entry.get("mismatches") or []:
            total += 1
            # Every diverging signal, not just the first. One check covers all
            # the outputs the coverage model listed for it and a state is the
            # tuple of them, so several can leave the model's sequence on the
            # same state -- ranking by the first alone would under-report the
            # rest to exactly the question this summary exists to answer.
            names = m.get("signals") or ([m["signal"]] if m.get("signal") else [])
            for sig in names:
                by_signal[sig] = by_signal.get(sig, 0) + 1
            step = m.get("step")
            if isinstance(step, int) and (first_step is None or step < first_step):
                first_step = step
    return {
        "fail_step": first_step,
        "total_mismatches": total,
        "failing_testpoints": [e["testpoint"] for e in payload],
        "fail_outputs": [
            {"sig": k, "mismatches": v}
            for k, v in sorted(by_signal.items(), key=lambda kv: -kv[1])
        ],
        "wave_vcd": str(wave_vcd) if wave_vcd else None,
    }


def failure_payload(suite_dir: Path) -> list[dict]:
    """Every failing check across every testpoint, with values and stimulus.

    The replacement for a scraped simulation log. `rtl_editor` currently gets a
    log excerpt filtered by keyword, and the recorded failure of that approach
    was 210 MISMATCH lines carrying two actual values. Here each entry already
    carries the check, the expected and actual values, and the stimulus that
    produced them -- and every failing testpoint is present, not just the first.
    """
    payload: list[dict] = []
    for path in sorted((Path(suite_dir) / "results").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "FAIL":
            continue
        payload.append(
            {
                "testpoint": data["tp_uid"],
                "failed_checks": data.get("checks_failed") or [],
                "failed_signals": data.get("signals_failed") or [],
                "mismatches": data.get("mismatches") or [],
            }
        )
    return payload


def describe_oracle(
    *,
    suite_dir: Path,
    refmodel_path: Path,
    testplan: list[dict] | None = None,
    max_chars: int = 16000,
) -> str:
    """What the repair agent is shown in place of a SystemVerilog testbench.

    `rtl_editor.chat` was written for the monolithic SV path and read
    `<run>/tb.sv` off disk to fill its `generated_tb` prompt slot. specflow never
    writes that file -- its testbench is the rendered cocotb suite -- so the very
    first repair iteration died with `FileNotFoundError` and the repair loop had
    never once run on this backend.

    The substitute is deliberately not the rendered testcases. Those are
    generated plumbing: a stimulus list, an `env.cov.hit` per bin and an
    `env.check` per check, identical in shape across every testpoint. What
    actually determines the expected values is the reference model, so that is
    what a repair agent needs to read. It is frozen and no tool can edit it, so
    showing it cannot produce a retrofitted oracle.

    Budgeted in priority order: the model whole first, then as many failing
    testplan elements as fit. Truncating the model would leave the agent
    reasoning about half a specification.
    """
    header = (
        "The oracle is NOT a SystemVerilog testbench. Expected values come from a\n"
        "Python reference model generated from the specification alone -- it has\n"
        "never seen this RTL -- and are compared by a cocotb suite, one test per\n"
        "testplan element. Neither is editable: a mismatch means the RTL and the\n"
        "specification disagree.\n\n"
        "=== reference model (the expected behaviour) ===\n"
    )
    try:
        model_src = Path(refmodel_path).read_text(encoding="utf-8")
    except OSError as exc:
        model_src = f"<reference model unreadable: {exc}>"

    out = header + model_src
    failing = {e["testpoint"] for e in failure_payload(suite_dir)}
    if testplan and failing:
        lines = ["\n\n=== testplan elements for the failing testpoints ===\n"]
        for tp in testplan:
            if tp.get("uid") not in failing:
                continue
            entry = (
                f"[{tp['uid']}] {tp.get('dimension', '?')}\n"
                f"  stimulus: {tp.get('stimulus', '')}\n"
                f"  expected: {tp.get('expected_response', '')}\n"
                f"  check:    {tp.get('check_method', '')}\n"
            )
            if len(out) + sum(map(len, lines)) + len(entry) > max_chars:
                lines.append("  ... further failing testpoints omitted\n")
                break
            lines.append(entry)
        out += "".join(lines)
    return out[:max_chars]
