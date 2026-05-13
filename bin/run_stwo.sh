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

# Load the shared precondition + grammar helpers.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/wrapper_lib.sh"

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
require_env CUDA_VISIBLE_DEVICES ""
require_env RAYON_NUM_THREADS 1
require_env TOKIO_WORKER_THREADS 1
require_env OMP_NUM_THREADS 1

# 4. Affinity prefix (RFC-0007 §"Preconditions" step 4 / RFC-0009).
read -ra AFFINITY <<< "$(resolve_affinity)"

# -- locate the Stwo prover binary --------------------------------------------

# Per RFC-0004 the Stwo prover lives at `stwo-side/target/release/stwo_prove`.
# `STWO_BINARY` overrides for development.
REPO_ROOT_FOR_BIN="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Cargo workspaces emit binaries at `<workspace-root>/target/release/`, not at
# `<workspace-root>/<member>/target/release/`. stwo-side joined the workspace
# under issue #19, so the resolved binary lives at the workspace target dir.
STWO_BINARY_DEFAULT="${REPO_ROOT_FOR_BIN}/target/release/stwo_prove"
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

# Exactly one CONSTRAINTS: and one TRACE_ROWS: line (RFC-0007 §"Stdout").
enforce_proverlog_grammar "${LOG_BUFFER}"

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
