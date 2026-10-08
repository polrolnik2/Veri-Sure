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

# ------------------------------------------------- Verilator >= 5.036 (source)
# cocotb 2.x hard-gates on 5.036 (VLT_MIN in its Makefile.verilator) and apt
# ships 5.020, so specflow's cocotb suites cannot run on the packaged build.
# Installed to /usr/local/bin so it shadows apt's copy on PATH.
#
# This build takes ~15 min. It runs at most once per container image, because
# the image is cached after the hook completes -- but the version guard below is
# what keeps it from re-running every session.
VERILATOR_TAG="v5.038"
vl_version() { "$1" --version 2>/dev/null | sed -n 's/^Verilator \([0-9.]*\).*/\1/p'; }
vl_ok() {
  local v; v="$(vl_version "$1")"
  [ -n "$v" ] && [ "$(printf '%s\n5.036\n' "$v" | sort -V | head -1)" = "5.036" ]
}

if vl_ok /usr/local/bin/verilator; then
  log "verilator $(vl_version /usr/local/bin/verilator) already present"
else
  log "building Verilator $VERILATOR_TAG (cocotb needs >= 5.036, apt has $(vl_version "$(command -v verilator)"))"
  apt-get install -y -qq git perl make autoconf g++ flex bison libfl2 libfl-dev \
    zlib1g-dev ccache help2man
  VL_SRC="$(mktemp -d)"
  git clone --quiet --depth 1 --branch "$VERILATOR_TAG" \
    https://github.com/verilator/verilator.git "$VL_SRC/verilator"
  ( cd "$VL_SRC/verilator" && autoconf && ./configure && make -j"$(nproc)" && make install ) >/dev/null
  rm -rf "$VL_SRC"
fi

# -------------------------------------------------------- mutation qualification
# mcy drives Gate G8. Its `make install` builds a Qt5 GUI we do not need, so the
# CLI parts are installed by hand. gawk is required by mcy's test_eq.sh (mawk
# will not do), and a modern z3 is not optional: on a 64-bit popcount
# equivalence, Debian's boolector (2012) failed instantly and apt's z3 4.8.12
# broke its pipe after 107 s, while z3-solver 5.1.0 solved it in 2 s.
if command -v mcy >/dev/null 2>&1; then
  log "mcy already present"
else
  log "installing mcy (CLI only, no Qt GUI)"
  apt-get install -y -qq gawk
  MCY_SRC="$(mktemp -d)"
  git clone --quiet --depth 1 https://github.com/YosysHQ/mcy.git "$MCY_SRC/mcy"
  install "$MCY_SRC/mcy/mcy.py" /usr/local/bin/mcy
  install "$MCY_SRC/mcy/mcy-dash.py" /usr/local/bin/mcy-dash
  mkdir -p /usr/local/share/mcy
  cp -r "$MCY_SRC/mcy/scripts" "$MCY_SRC/mcy/dash" /usr/local/share/mcy/
  rm -rf "$MCY_SRC"
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

# A modern z3 for sby/mcy. apt's 4.8.12 is from 2021 and times out on
# equivalence queries mcy issues routinely. Symlinked into /usr/local/bin so it
# shadows the apt copy for every consumer, not just this venv.
if [ ! -e /usr/local/bin/z3 ] || ! /usr/local/bin/z3 --version 2>/dev/null | grep -qE 'version (5|[6-9])'; then
  log "installing modern z3"
  "$VENV/bin/pip" install --quiet --disable-pip-version-check z3-solver
  if [ -x "$VENV/bin/z3" ]; then
    ln -sf "$VENV/bin/z3" /usr/local/bin/z3
  fi
fi

# Put the venv ahead of the system interpreter for the rest of the session, so
# `python`/`pytest` resolve to it without an explicit activate.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$VENV/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  echo "export VIRTUAL_ENV=\"$VENV\"" >> "$CLAUDE_ENV_FILE"
fi

# ------------------------------------------------------------------- verify
FAILED=0
for cmd in iverilog vvp yosys verilator verilator_coverage sby z3 mcy gawk; do
  if command -v "$cmd" >/dev/null 2>&1; then
    log "  ok   $cmd"
  else
    log "  FAIL $cmd not on PATH"
    FAILED=1
  fi
done

# Version guard, not just presence: cocotb refuses Verilator < 5.036 outright,
# so a stale apt build passes the check above and then fails at build time.
if vl_ok "$(command -v verilator)"; then
  log "  ok   verilator $(vl_version "$(command -v verilator)") >= 5.036"
else
  log "  FAIL verilator on PATH is $(vl_version "$(command -v verilator)"); cocotb needs >= 5.036"
  FAILED=1
fi

# The linter is verified by path, not just presence. `ruff` was previously
# resolvable only because the base image shipped one at /root/.local/bin, so a
# change to the image would have broken linting with nothing in the repo to
# explain why. requirements.txt now pins it, and this checks that the pinned
# copy is the one PATH will find.
if [ -x "$VENV/bin/ruff" ]; then
  log "  ok   ruff $("$VENV/bin/ruff" --version | awk '{print $2}') (venv)"
else
  log "  FAIL ruff missing from $VENV; requirements.txt should install it"
  FAILED=1
fi

"$VENV/bin/python" - <<'PY' || FAILED=1
import sys

# Import rather than find_spec: agentscope resolves an unpinned `mcp` and a bad
# resolve fails at import time, not at spec-lookup time. Only a real import
# catches that.
failed = []
for m in ("agentscope", "pydantic", "tqdm", "tree_sitter",
          "tree_sitter_verilog", "vcdvcd", "pytest", "cocotb"):
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

log "ready: pytest tests/, ruff check, and benchmarks/chipverilog all runnable"
