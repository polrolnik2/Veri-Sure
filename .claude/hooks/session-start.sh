#!/bin/bash
# SessionStart hook: bring a fresh Claude Code on the web container up to the point
# where Veri-Sure's tests, the simulation loop, and the ChipVerilog benchmark all run.
#
# Veri-Sure is not a pure-Python project: eda_agent/sim_reviewer.py hard-fails via
# _require_executable() without verilator, boolean_proofer needs SymbiYosys + a solver,
# and benchmarks/chipverilog needs iverilog/vvp/yosys. Containers are ephemeral, so
# without this hook every web session starts unable to simulate anything.
set -euo pipefail

# Local machines are expected to have their own toolchain (see README).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_DIR"

log() { echo "[session-start] $*"; }

# SymbiYosys is versioned in lockstep with yosys; keep this matching the yosys
# that apt installs, or sby fails at the read_verilog stage.
YOSYS_TAG="yosys-0.33"

# ---------------------------------------------------------------- apt packages
# iverilog+vvp: ChipVerilog compile gate and simulation flow
# yosys:        ChipVerilog equivalence flow, and SymbiYosys' backend
# verilator:    Veri-Sure's own simulation oracle (sim_reviewer.py)
# z3:           SMT solver for SymbiYosys
APT_PKGS=(iverilog yosys verilator z3 build-essential)
MISSING_APT=()
for cmd in iverilog yosys verilator z3; do
  command -v "$cmd" >/dev/null 2>&1 || MISSING_APT+=("$cmd")
done

if [ ${#MISSING_APT[@]} -gt 0 ]; then
  log "installing EDA toolchain (missing: ${MISSING_APT[*]})"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq "${APT_PKGS[@]}"
else
  log "EDA toolchain already present"
fi

# ------------------------------------------------------------------ SymbiYosys
# Not packaged in apt and not on PyPI, so it is built from source.
if command -v sby >/dev/null 2>&1; then
  log "sby already present"
else
  log "installing SymbiYosys ($YOSYS_TAG)"
  SBY_SRC="$(mktemp -d)"
  git clone --quiet --depth 1 --branch "$YOSYS_TAG" https://github.com/YosysHQ/sby.git "$SBY_SRC/sby" \
    || git clone --quiet --depth 1 https://github.com/YosysHQ/sby.git "$SBY_SRC/sby"
  make -C "$SBY_SRC/sby" install >/dev/null
  rm -rf "$SBY_SRC"
fi

# --------------------------------------------------------------- Python deps
# Installed into a venv rather than the system interpreter. Several of this
# image's Debian-managed packages (PyJWT, cryptography) have no RECORD file, so
# pip cannot upgrade them and `pip install -r requirements.txt` aborts partway --
# leaving a half-installed tree that imports in confusing ways.
VENV="$PROJECT_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  log "creating venv"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --disable-pip-version-check --upgrade pip
fi

log "installing Python dependencies"
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r requirements.txt

# Put the venv ahead of the system interpreter for the rest of the session, so
# `python`/`pytest` resolve to it without an explicit activate.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$VENV/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  echo "export VIRTUAL_ENV=\"$VENV\"" >> "$CLAUDE_ENV_FILE"
fi

# ------------------------------------------------------------------- verify
FAILED=0
for cmd in iverilog vvp yosys verilator sby z3; do
  if command -v "$cmd" >/dev/null 2>&1; then
    log "  ok   $cmd"
  else
    log "  FAIL $cmd not on PATH"
    FAILED=1
  fi
done

"$VENV/bin/python" - <<'PY' || FAILED=1
import sys

# Import rather than find_spec: agentscope resolves an unpinned `mcp` and a bad
# resolve fails at import time, not at spec-lookup time. Only a real import
# catches that.
failed = []
for m in ("agentscope", "pydantic", "tqdm", "tree_sitter",
          "tree_sitter_verilog", "vcdvcd", "pytest"):
    try:
        __import__(m)
    except Exception as exc:  # noqa: BLE001
        failed.append(f"{m} ({type(exc).__name__}: {exc})")

if failed:
    print("[session-start]   FAIL python imports:")
    for f in failed:
        print(f"[session-start]        {f}")
    sys.exit(1)
print("[session-start]   ok   python dependencies")
PY

if [ "$FAILED" -ne 0 ]; then
  log "setup incomplete — simulation or formal steps will fail"
  exit 1
fi

log "ready: pytest tests/ and benchmarks/chipverilog both runnable"
