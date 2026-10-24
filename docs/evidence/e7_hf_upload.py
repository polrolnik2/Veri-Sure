"""Publish the frozen runs to a Hugging Face dataset repository.

    HF_TOKEN=... e7_hf_upload.py RUN [RUN ...] [--tarballs DIR] [--repo OWNER/NAME]
                                 [--public] [--dry-run]

    e7_hf_upload.py luna12 luna13 luna14 luna15 --tarballs <stage>

Per run, from `docs/evidence/e7/<RUN>/` (committed):

    <RUN>/corpora/<module>-ok.tar.gz   the packed corpus (`e6_pack_corpus.py`):
                                       contract, requirements, normalized forms,
                                       testplan, stimulus, coverage, probes, the
                                       oracle set WITH its corpus, the shipped set,
                                       the population, the reference model, the
                                       scorecard, and a sha256 of every file
    <RUN>/results/<module>/            golden-replay scores and audit logs
    <RUN>/editor/<module>/             the RTL Editor job: summary, verdict, final
                                       and generated RTL, usage, compressed log
    <RUN>/summary.json, README.md      the run's table and notes

and, when `--tarballs DIR` holds `DIR/<RUN>/runs/<module>.tar.gz`:

    <RUN>/runs/<module>.tar.gz         the whole run directory, model I/O included
                                       (`agent_io/`: every prompt and response),
                                       waveforms (`*.vcd`) excluded

Make those with `tar --exclude='*.vcd' -czf DIR/<RUN>/runs/<m>.tar.gz -C <runs-root>/<RUN> <m>`.
And when it holds `DIR/<RUN>/editor-runs/<job>.tar.gz`:

    <RUN>/editor-runs/<job>.tar.gz     an RTL Editor job's directory, model I/O
                                       included (`debug_trajectory.jsonl`: every
                                       turn's text, tool calls and diffs;
                                       `debugger_prompt.txt`); `suite/` excluded.
                                       `<module>-<timestamp>` is an attempt that
                                       did not reach its verdict.
The golden-replay traces (`gold/`, `bound/`, ...) are not uploaded: they are
regenerated from a corpus by `e7_module.py` / `e7_bind_golden.py`.

`REPS.md` (the cross-rep comparison) goes to the root, and the dataset card is
built from it. So do the RTL Editor's `EDITOR-RESULTS.md`, `EDITOR-CACHE.md`,
`EDITOR.json` and `editor-usage/`.

**PRIVATE UNLESS `--public`.** Publishing a research artifact is the owner's
decision; a private repository can be made public from its settings page, and a
public one cannot be un-published.

Needs a token with WRITE access in `HF_TOKEN`. The Hugging Face connector
available to an agent session is read-only (ls/cat/search), so it cannot do this.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "e7"


def _opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


#: The RTL Editor's cross-run files, uploaded to the root beside REPS.md.
EDITOR_ROOT = ("EDITOR-RESULTS.md", "EDITOR-CACHE.md", "EDITOR.json", "editor-usage")


def _card(runs: list[str], with_io: dict[str, list[str]], repo: str,
          with_editor_io: dict[str, list[str]] | None = None) -> str:
    io = ", ".join(f"{run} ({len(m)})" for run, m in with_io.items() if m) or "none"
    eio = ", ".join(f"{run} ({len(m)})" for run, m in (with_editor_io or {}).items()
                    if m) or "none"
    reps = (EVIDENCE / "REPS.md").read_text() if (EVIDENCE / "REPS.md").is_file() else ""
    #: The numbers live in REPS.md alone (it applies the re-scores and marks the
    #: cache-seeded runs); a second table built from the raw summaries would not.
    return f"""---
license: other
pretty_name: Veri-Sure frozen pipeline runs
tags:
- verilog
- hardware-verification
- llm-generated
---

# Veri-Sure frozen pipeline runs

Five ChipVerilog modules run end to end through the Veri-Sure
specification-to-checks pipeline (contract, S1 through the oracle stage, the
reference model and the shipped check set), three independent times each, then
scored against the known-good design. The golden design is simulated for
scoring only and is never shown to any model. Runs: {", ".join(runs)}; the
comparison, with which run is which rep, is `REPS.md`, reproduced below.

## Layout

- `<run>/corpora/<module>-ok.tar.gz` -- packed corpus with a manifest of sha256s.
- `<run>/runs/<module>.tar.gz` -- the full run directory, including every model
  prompt and response under `agent_io/`; waveforms excluded. Present for: {io}.
- `<run>/results/<module>/` -- golden-replay scores and the hand-bound audit.
- `<run>/editor/<module>/` -- the RTL Editor job on that corpus: generate, then
  repair against the shipped set, then a ChipVerilog equivalence verdict.
  Results across jobs: `EDITOR-RESULTS.md`; token use and prompt-cache rate:
  `EDITOR-CACHE.md`.
- `<run>/editor-runs/<job>.tar.gz` -- the editor job's directory with every
  model turn (`debug_trajectory.jsonl`); `<module>-<timestamp>` is an attempt
  that did not reach a verdict. Present for: {eio}.
- `<run>/README.md`, `<run>/summary.json` -- each run's table and notes.
- `REPS.md` -- the cross-rep comparison, reproduced below.

The benchmark designs and specifications are from ChipVerilog; see that
project's licence. Repository: `{repo}`.

---

{reps}"""


def main() -> int:
    runs = [a for a in sys.argv[1:] if not a.startswith("--")
            and sys.argv[sys.argv.index(a) - 1] not in ("--repo", "--tarballs")]
    if not runs:
        print(__doc__.strip().splitlines()[2])
        return 2
    missing = [r for r in runs if not (EVIDENCE / r / "summary.json").is_file()]
    if missing:
        print(f"no saved evidence for {missing} under {EVIDENCE}")
        return 2
    repo = _opt("--repo", "polrolnik2/veri-sure-runs")
    tarballs = Path(_opt("--tarballs")) if _opt("--tarballs") else None
    dry = "--dry-run" in sys.argv
    token = os.environ.get("HF_TOKEN")
    if not token and not dry:
        print("HF_TOKEN is not set; a token with write access is required")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        with_io: dict[str, list[str]] = {}
        with_editor_io: dict[str, list[str]] = {}
        for run in runs:
            shutil.copytree(EVIDENCE / run, stage / run)
            for sub, seen in (("runs", with_io), ("editor-runs", with_editor_io)):
                src = tarballs / run / sub if tarballs else None
                seen[run] = sorted(p.name for p in src.glob("*.tar.gz")) if src and src.is_dir() else []
                if seen[run]:
                    (stage / run / sub).mkdir()
                    for name in seen[run]:
                        #: Hard links: the stage is a view, not a second copy.
                        try:
                            os.link(src / name, stage / run / sub / name)
                        except OSError:  # another filesystem
                            shutil.copy(src / name, stage / run / sub / name)
        if (EVIDENCE / "REPS.md").is_file():
            shutil.copy(EVIDENCE / "REPS.md", stage / "REPS.md")
        for name in EDITOR_ROOT:
            if (EVIDENCE / name).is_dir():
                shutil.copytree(EVIDENCE / name, stage / name)
            elif (EVIDENCE / name).is_file():
                shutil.copy(EVIDENCE / name, stage / name)
        (stage / "README.md").write_text(_card(runs, with_io, repo, with_editor_io))
        files = sorted(p for p in stage.rglob("*") if p.is_file())
        size = sum(p.stat().st_size for p in files)
        print(f"staged {len(files)} file(s), {size / 1e6:.0f} MB, for {repo} "
              f"({'public' if '--public' in sys.argv else 'private'})")
        for run in runs:
            print(f"  {run}: model I/O for {len(with_io[run])} module(s), "
                  f"{len(with_editor_io[run])} editor job(s)")
        if dry:
            print("--dry-run: nothing uploaded")
            return 0
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        api.create_repo(repo, repo_type="dataset", private="--public" not in sys.argv,
                        exist_ok=True)
        api.upload_large_folder(repo_id=repo, repo_type="dataset", folder_path=str(stage))
    print(f"https://huggingface.co/datasets/{repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
