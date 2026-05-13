#!/usr/bin/env bash
#
# bin/run_stwo.sh — Stwo (Cairo) prover wrapper.
#
# Contract from `docs/rfcs/RFC-0007-wrapper-contract.md` §"`bin/run_<prover>.sh`":
#
#   bin/run_stwo.sh <fixtures_path> <output_proof_path>
#
# Symmetric with `bin/run_sp1.sh` — same argv shape, same precondition matrix,
# same exit-code semantics, same M7 grammar enforcement. The CI symmetry
# check (#30) asserts the two scripts are structurally aligned.
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — proof emitted, stdout grammar satisfied
#   1 — prover failed (witness rejected, internal error, grammar violation)
#   2 — precondition violated (env var miss, affinity miss, missing fixture, etc.)
#   3 — build error (Stwo prover binary missing / not buildable)

set -euo pipefail

# -- precondition checks ------------------------------------------------------

usage() {
  cat >&2 <<'EOF'
Usage: bin/run_stwo.sh <fixtures_path> <output_proof_path>

Exit codes:
  0  proof emitted, grammar satisfied
  1  prover internal failure
  2  precondition violated; prover not invoked
  3  build error
EOF
}

# 1. Argument count.
if [[ $# -ne 2 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: bin/run_stwo.sh expects 2 args (fixtures_path, output_proof_path), got $#" >&2
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
#    Symmetric with bin/run_sp1.sh — same four caps. The Stwo backend uses
#    Rayon internally; if it ever stops doing so, the precondition is still
#    correct because the *measurement* is single-threaded regardless.
require_env() {
  local var="$1"
  local want="$2"
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

# -- locate the Stwo prover binary --------------------------------------------

# Per RFC-0004 the Stwo prover lives at `stwo-side/target/release/stwo_prove`.
# `STWO_BINARY` overrides for development.
STWO_BINARY_DEFAULT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/stwo-side/target/release/stwo_prove"
STWO_BINARY="${STWO_BINARY:-${STWO_BINARY_DEFAULT}}"

if [[ ! -x "${STWO_BINARY}" ]]; then
  echo "BUILD.STWO_SHA_DRIFT: Stwo prover binary not built at ${STWO_BINARY}." >&2
  echo "Run cargo build --release in stwo-side/. (See RFC-0004.)" >&2
  exit 3
fi

# -- invoke the prover --------------------------------------------------------

TMP_PROOF="${OUTPUT_PROOF_PATH}.partial.$$"
LOG_BUFFER="$(mktemp)"
trap 'rm -f "${TMP_PROOF}" "${LOG_BUFFER}"' EXIT

set +e
"${AFFINITY[@]}" "${STWO_BINARY}" \
  --fixtures "${FIXTURES_PATH}" \
  --output "${TMP_PROOF}" >"${LOG_BUFFER}" 2>&1
PROVER_RC=$?
set -e

cat "${LOG_BUFFER}"

if ! grep -qE '^CONSTRAINTS: [0-9]+$' "${LOG_BUFFER}" \
   || ! grep -qE '^TRACE_ROWS:[[:space:]]+[0-9]+$' "${LOG_BUFFER}"; then
  echo "PROVER.STDOUT_GRAMMAR_VIOLATION: missing CONSTRAINTS: / TRACE_ROWS: line(s) in prover output" >&2
  exit 1
fi

if [[ ${PROVER_RC} -ne 0 ]]; then
  echo "PROVER.WITNESS_REJECTED: stwo prover exited ${PROVER_RC}" >&2
  exit 1
fi

if [[ ! -s "${TMP_PROOF}" ]]; then
  echo "PROVER.WITNESS_REJECTED: stwo prover succeeded but produced no proof bytes" >&2
  exit 1
fi
mv -- "${TMP_PROOF}" "${OUTPUT_PROOF_PATH}"
trap - EXIT
rm -f "${LOG_BUFFER}"

exit 0
