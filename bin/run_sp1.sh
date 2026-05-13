#!/usr/bin/env bash
#
# bin/run_sp1.sh — SP1 prover wrapper.
#
# Contract from `docs/rfcs/RFC-0007-wrapper-contract.md` §"`bin/run_<prover>.sh`":
#
#   bin/run_sp1.sh <fixtures_path> <output_proof_path>
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — proof emitted, stdout grammar satisfied
#   1 — prover failed (witness rejected, internal error, grammar violation)
#   2 — precondition violated (env var miss, affinity miss, missing fixture, etc.)
#   3 — build error (SP1 binary missing / not buildable)
#
# Stdout: the prover's merged stdout+stderr. Must contain (the wrapper post-
# processes if upstream doesn't emit them):
#   CONSTRAINTS: <integer>
#   TRACE_ROWS:  <integer>
#
# Stderr: reserved for wrapper-issued diagnostics. The prover's stderr is
# folded into stdout so a reader watching stderr only sees harness errors.
#
# Output: the proof file at <output_proof_path>, written atomically via a
# temp-then-rename pattern.

set -euo pipefail

# -- precondition checks ------------------------------------------------------

usage() {
  cat >&2 <<'EOF'
Usage: bin/run_sp1.sh <fixtures_path> <output_proof_path>

Exit codes:
  0  proof emitted, grammar satisfied
  1  prover internal failure
  2  precondition violated; prover not invoked
  3  build error
EOF
}

# 1. Argument count.
if [[ $# -ne 2 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: bin/run_sp1.sh expects 2 args (fixtures_path, output_proof_path), got $#" >&2
  usage
  exit 2
fi

FIXTURES_PATH="$1"
OUTPUT_PROOF_PATH="$2"

# 2. Fixture file readable.
if [[ ! -f "${FIXTURES_PATH}" || ! -r "${FIXTURES_PATH}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: fixtures file not readable: ${FIXTURES_PATH}" >&2
  exit 2
fi

# 3. Environment variable assertions (RFC-0007 §"Preconditions" step 3).
#    Every prover invocation must run single-threaded with no GPU residency.
require_env() {
  local var="$1"
  local want="$2"
  # `${VAR-__UNSET__}` (no colon) distinguishes "unset" from "set to empty
  # string". The harness requires CUDA_VISIBLE_DEVICES to be *set to empty*
  # (no devices visible), which the `:-` form would falsely flag as missing.
  local got="${!var-__UNSET__}"
  if [[ "${got}" != "${want}" ]]; then
    echo "MEASUREMENT.ENV_VAR_MISS: ${var}='${got}' but harness requires '${want}'" >&2
    exit 2
  fi
}
require_env CUDA_VISIBLE_DEVICES ""
require_env RAYON_NUM_THREADS 1
require_env TOKIO_WORKER_THREADS 1
require_env OMP_NUM_THREADS 1

# 4. Affinity prefix (RFC-0007 §"Preconditions" step 4 / RFC-0009).
#    macOS: taskpolicy -c utility; Linux: taskset -c 0.
case "$(uname)" in
  Darwin)
    if ! command -v taskpolicy >/dev/null 2>&1; then
      echo "MEASUREMENT.AFFINITY_MISS: taskpolicy not on PATH (required on macOS per RFC-0009)" >&2
      exit 2
    fi
    AFFINITY=(taskpolicy -c utility)
    ;;
  Linux)
    if ! command -v taskset >/dev/null 2>&1; then
      echo "MEASUREMENT.AFFINITY_MISS: taskset not on PATH (required on Linux per RFC-0009)" >&2
      exit 2
    fi
    AFFINITY=(taskset -c 0)
    ;;
  *)
    echo "MEASUREMENT.AFFINITY_MISS: unsupported platform $(uname); RFC-0009 limits to darwin/linux" >&2
    exit 2
    ;;
esac

# -- locate the SP1 prover binary ---------------------------------------------

# Per RFC-0006 the SP1 prover lives under `sp1-side/` as a git submodule with
# the in-repo patch applied. The default candidate path is the binary the
# patch produces; `SP1_BINARY` overrides for development convenience.
SP1_BINARY_DEFAULT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/sp1-side/target/release/prove"
SP1_BINARY="${SP1_BINARY:-${SP1_BINARY_DEFAULT}}"

if [[ ! -x "${SP1_BINARY}" ]]; then
  echo "BUILD.SP1_PATCH_FAIL: SP1 prover binary not built at ${SP1_BINARY}." >&2
  echo "Run scripts/apply_sp1_patch.sh + cargo build --release in sp1-side/. (See RFC-0006.)" >&2
  exit 3
fi

# -- invoke the prover --------------------------------------------------------

# Atomic write: stage to a sibling temp file, then mv into place.
TMP_PROOF="${OUTPUT_PROOF_PATH}.partial.$$"
trap 'rm -f "${TMP_PROOF}"' EXIT

# Capture the prover's merged stdout+stderr to a buffer file so the wrapper
# can append the CONSTRAINTS/TRACE_ROWS lines if upstream did not emit them.
LOG_BUFFER="$(mktemp)"
trap 'rm -f "${TMP_PROOF}" "${LOG_BUFFER}"' EXIT

set +e
"${AFFINITY[@]}" "${SP1_BINARY}" \
  --fixtures "${FIXTURES_PATH}" \
  --output "${TMP_PROOF}" >"${LOG_BUFFER}" 2>&1
PROVER_RC=$?
set -e

# Re-emit the prover log to *our* stdout — the harness captures this.
cat "${LOG_BUFFER}"

# Grammar enforcement (RFC-0007 §"Stdout"). Both lines must be present in the
# prover's log; if upstream doesn't emit them, the wrapper does not fabricate
# substitute values — the absence is a `PROVER.STDOUT_GRAMMAR_VIOLATION` and
# the run is marked invalid.
if ! grep -qE '^CONSTRAINTS: [0-9]+$' "${LOG_BUFFER}" \
   || ! grep -qE '^TRACE_ROWS:[[:space:]]+[0-9]+$' "${LOG_BUFFER}"; then
  echo "PROVER.STDOUT_GRAMMAR_VIOLATION: missing CONSTRAINTS: / TRACE_ROWS: line(s) in prover output" >&2
  exit 1
fi

if [[ ${PROVER_RC} -ne 0 ]]; then
  echo "PROVER.WITNESS_REJECTED: sp1 prover exited ${PROVER_RC}" >&2
  exit 1
fi

# Atomicity: only commit the proof to the target path after the prover
# succeeded *and* the log grammar checked out.
if [[ ! -s "${TMP_PROOF}" ]]; then
  echo "PROVER.WITNESS_REJECTED: sp1 prover succeeded but produced no proof bytes" >&2
  exit 1
fi
mv -- "${TMP_PROOF}" "${OUTPUT_PROOF_PATH}"
trap - EXIT
rm -f "${LOG_BUFFER}"

exit 0
