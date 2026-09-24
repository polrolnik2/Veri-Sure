"""Publish the frozen runs to a Hugging Face dataset repository.

    HF_TOKEN=... e7_hf_upload.py <runs-root> [--repo OWNER/NAME] [--public]

Everything a run left behind, per module, so a run can be re-scored and re-read
without this container:

    corpora/<module>-ok.tar.gz      the packed corpus (`e6_pack_corpus.py`):
                                    contract, requirements, normalized forms,
                                    testplan, stimulus, coverage, probes, the
                                    oracle set WITH its corpus, the shipped set,
                                    the population, the reference model, the
                                    scorecard, and a sha256 of every file
    runs/<module>.tar.gz            the whole run directory, model I/O included
                                    (`agent_io/`: every prompt and response),
                                    waveforms (`*.vcd`) excluded for size
    results/<module>/*.json         golden-replay score and RTL Editor summary
    README.md                       a dataset card with the results table

**PRIVATE UNLESS `--public`.** Publishing a research artifact is the owner's
decision; a private repository can be made public from its settings page, and a
public one cannot be un-published.

Needs a token with WRITE access in `HF_TOKEN`. The Hugging Face connector
available to an agent session is read-only (ls/cat/search), so it cannot do this.
"""
from __future__ import annotations

import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path


def _opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _card(root: Path, modules: list[str], repo: str) -> str:
    rows = []
    for m in modules:
        res = root / "results" / m
        sc = res / "score.json"
        ed = res / "editor_summary.json"
        gr = res / "chipverilog.json"
        s = json.loads(sc.read_text()) if sc.is_file() else {}
        e = json.loads(ed.read_text()) if ed.is_file() else {}
        g = json.loads(gr.read_text()) if gr.is_file() else {}
        fin = (e.get("final") or {})

        def pct(x):
            return "n/a" if x is None else f"{100 * x:.1f}%"
        audit = (f"{s.get('audit_convicted')}/{s.get('audit_judges')}"
                 if s.get("audit_judges") is not None else "n/a")
        rows.append(
            f"| {m} | {s.get('bodies', 'n/a')} | {pct(s.get('span'))} | "
            f"{pct(s.get('blindness'))} | {audit} | "
            f"{fin.get('pass', 'n/a')}/{fin.get('requirements', 'n/a')} | "
            f"{g.get('status', 'n/a')} |")
    table = "\n".join(rows)
    return f"""---
license: other
pretty_name: Veri-Sure frozen pipeline runs
tags:
- verilog
- hardware-verification
- llm-generated
---

# Veri-Sure frozen pipeline runs

Five ChipVerilog modules, each run through the Veri-Sure specification-to-checks
pipeline from scratch (contract, S1 through the oracle stage, the reference model
and the shipped check set), then used as the testbench for an RTL Editor loop
that generates and repairs RTL against it.

| module | shipped bodies | span | blindness | audit (golden) | editor: requirements passing | ChipVerilog verdict |
|---|---|---|---|---|---|---|
{table}

- **span**: share of behavioural requirements with at least one shipped check.
- **blindness**: share of disagreement cells among 7 spec-derived designs that no
  shipped check separates.
- **audit**: requirements whose shipped checks convict the known-good design,
  over those that can be judged on it. The golden design is simulated for this
  column only and is never shown to any model.

## Layout

- `corpora/<module>-ok.tar.gz` -- packed corpus with a `MANIFEST.json` of sha256s.
- `runs/<module>.tar.gz` -- the full run directory, including every model prompt
  and response under `agent_io/`; waveforms excluded.
- `results/<module>/` -- golden-replay score, RTL Editor summary, ChipVerilog verdict.

The benchmark designs and specifications are from ChipVerilog; see that
project's licence. Repository: `{repo}`.
"""


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")
            and sys.argv[sys.argv.index(a) - 1] != "--repo"]
    if not args:
        print(__doc__.strip().splitlines()[2])
        return 2
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("HF_TOKEN is not set; a token with write access is required")
        return 1
    from huggingface_hub import HfApi

    root = Path(args[0])
    repo = _opt("--repo", "polrolnik2/veri-sure-runs")
    api = HfApi(token=token)
    api.create_repo(repo, repo_type="dataset", private="--public" not in sys.argv,
                    exist_ok=True)
    modules = sorted(p.name for p in root.iterdir()
                     if p.is_dir() and (p / "specflow").is_dir())
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        (stage / "runs").mkdir()
        for m in modules:
            with tarfile.open(stage / "runs" / f"{m}.tar.gz", "w:gz") as tf:
                tf.add(root / m, arcname=m,
                       filter=lambda ti: None if ti.name.endswith(".vcd") else ti)
            print(f"packed runs/{m}.tar.gz", flush=True)
        (stage / "README.md").write_text(_card(root, modules, repo))
        api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=str(stage),
                          commit_message="frozen runs")
    for sub in ("corpora", "results"):
        if (root / sub).is_dir():
            api.upload_folder(repo_id=repo, repo_type="dataset",
                              folder_path=str(root / sub), path_in_repo=sub,
                              commit_message=f"{sub}")
    print(f"https://huggingface.co/datasets/{repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
