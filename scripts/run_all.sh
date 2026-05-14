#!/usr/bin/env bash
#
# run_all.sh — top-level orchestrator (RFC-0010 / RFC-0011).
#
# Usage:
#   scripts/run_all.sh [--day 1|2] [--skip-build] [--skip-measure] [--cooldown-seconds N]
#
# Produces `RESULTS.md` (via `uv run analyze`) from a clean clone on the
# reference rig. Aborts on any precondition failure; restores host state
# on every exit path via a trap-installed cleanup.sh.
#
# Exit codes mirror the rest of the harness (`docs/spec/04-error-model.md`):
#   0 — success, RESULTS.md produced.
#   1 — prover internal failure (propagated from `bin/run_<prover>.sh`).
#   2 — usage / argv error or working-tree dirty.
#   3 — `BUILD.*` (submodule init / SP1 patch apply / cargo build).
#   4 — `FIXTURE.*` (gen-fixtures drift, schema invalid).
#   5 — `MEASUREMENT.*` (preflight, versions drift, license, GPU residency,
#       discard escalation).
#   6 — `REPORT.*` (analyze.py / plot.py).

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/locale_env.sh"

# -- argv parsing -----------------------------------------------------------

DAY=1
SKIP_BUILD=0
SKIP_MEASURE=0
COOLDOWN_SECONDS=300  # RFC-0010 §"Thermal protocol" — 5-minute cool-down between provers.

usage() {
  cat >&2 <<'EOF'
Usage: scripts/run_all.sh [--day 1|2] [--skip-build] [--skip-measure] [--cooldown-seconds N]

Options:
  --day 1            run sp1 then stwo (default)
  --day 2            run stwo then sp1 (RFC-0010 §"Day-1/Day-2 stability gate")
  --skip-build       reuse cached prover binaries; skip cargo build
  --skip-measure     stop after build + setup; skip the timed series
  --cooldown-seconds N  override the inter-prover cool-down (default 300)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --day) DAY="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --skip-measure) SKIP_MEASURE=1; shift ;;
    --cooldown-seconds) COOLDOWN_SECONDS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "run_all.sh: unknown flag $1" >&2; usage; exit 2 ;;
  esac
done

case "${DAY}" in
  1|2) ;;
  *) echo "run_all.sh: --day must be 1 or 2, got '${DAY}'" >&2; exit 2 ;;
esac

cd "${REPO_ROOT}"

# -- working-tree clean check ----------------------------------------------

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "MEASUREMENT.ENV_VAR_MISS: working tree is dirty — refusing to start a measured run" >&2
  git status --short >&2
  exit 2
fi

# -- env caps (the prover wrappers will recheck, but failing here is friendlier) --

export CUDA_VISIBLE_DEVICES=""
export RAYON_NUM_THREADS=1
export TOKIO_WORKER_THREADS=1
export OMP_NUM_THREADS=1

# -- cleanup trap -----------------------------------------------------------

trap 'bash "${REPO_ROOT}/scripts/cleanup.sh" || true' EXIT INT TERM

# -- per-step orchestration -------------------------------------------------

RUN_ID="$(date -u +%s)-$(git rev-parse --short HEAD)"
echo "run_all.sh: day=${DAY} run_id=${RUN_ID}"

# 1. Submodules.
bash "${REPO_ROOT}/scripts/init_submodules.sh"

# 2. Python deps.
uv sync --frozen >/dev/null

# 3. Versions-lock drift gate (soft-skip until #7 commits an initial lock).
if [[ -f "${REPO_ROOT}/versions.lock" ]]; then
  ACTUAL="$(DRY=1 bash "${REPO_ROOT}/scripts/lock_versions.sh")"
  EXPECTED="$(cat "${REPO_ROOT}/versions.lock")"
  if [[ "$(jq 'del(.generated_at, .generator_commit)' <<<"${ACTUAL}")" \
        != "$(jq 'del(.generated_at, .generator_commit)' <<<"${EXPECTED}")" ]]; then
    echo "MEASUREMENT.VERSIONS_DRIFT: live toolchain differs from versions.lock" >&2
    exit 5
  fi
else
  echo "run_all.sh: versions.lock not yet committed (#7 pending); skipping drift gate"
fi

# 4. License check.
bash "${REPO_ROOT}/scripts/check_licenses.sh"

# 5. Build both prover sides.
if [[ "${SKIP_BUILD}" != "1" ]]; then
  # Stwo-side uses nightly-2025-07-14 (stwo's own pinned toolchain).
  (cd "${REPO_ROOT}" && cargo +nightly-2025-07-14 build --release -p stwo-side)
  # SP1 prover lives at third_party/sp1/ as a vendored copy with its
  # own rust-toolchain (1.93.0).
  if [[ -f "${REPO_ROOT}/third_party/sp1/Cargo.toml" ]]; then
    (cd "${REPO_ROOT}/third_party/sp1" && cargo build --release)
  fi
fi

# 6. Generate / verify fixture.
if [[ -f "${REPO_ROOT}/fixtures/v0.1.json" ]]; then
  uv run gen-fixtures --check
else
  uv run gen-fixtures
fi

# 7. Preflight.
bash "${REPO_ROOT}/scripts/preflight.sh"

if [[ "${SKIP_MEASURE}" == "1" ]]; then
  echo "run_all.sh: --skip-measure set; stopping after preflight"
  exit 0
fi

# 8. SP1 trusted-setup capture (one-shot per versions.lock).
if [[ -x "${REPO_ROOT}/scripts/measure_setup.sh" ]]; then
  bash "${REPO_ROOT}/scripts/measure_setup.sh" "${RUN_ID}" || true
fi

# 9. Measured run series, in the order determined by `--day`.
order=()
if [[ "${DAY}" == "1" ]]; then
  order=(sp1 stwo)
else
  order=(stwo sp1)
fi

for prover in "${order[@]}"; do
  echo "run_all.sh: measuring ${prover}"
  SKIP_PREFLIGHT=1 bash "${REPO_ROOT}/scripts/measure.sh" "${prover}" "${RUN_ID}"
  if [[ "${prover}" != "${order[-1]}" ]]; then
    echo "run_all.sh: cool-down ${COOLDOWN_SECONDS}s before next prover (RFC-0010 §thermal protocol)"
    sleep "${COOLDOWN_SECONDS}"
  fi
done

# 10. Analyze + plot. Soft-skip until #41 / #43 land.
if uv run python -c "import grover_tax.analyze" 2>/dev/null; then
  uv run analyze
else
  echo "run_all.sh: grover_tax.analyze not yet implemented (#41 pending); skipping report"
fi
if uv run python -c "import grover_tax.plot" 2>/dev/null; then
  uv run plot
fi

echo "run_all.sh: day-${DAY} complete; run_id=${RUN_ID}"
exit 0
