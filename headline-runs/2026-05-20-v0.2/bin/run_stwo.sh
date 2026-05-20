#!/usr/bin/env bash
#
# bin/run_stwo.sh — Stwo (Cairo) prover wrapper.
#
# Contract from `docs/rfcs/RFC-0007-wrapper-contract.md` §"`bin/run_<prover>.sh`":
#
#   bin/run_stwo.sh <fixtures_path> <output_proof_path>
#
# Symmetric with `bin/run_sp1.sh`. v0.1 spec target: drives the
# apples-to-apples Cairo 1 kernel through cairo-vm + stwo-cairo Circle
# STARK via `bin/apples-prove` (proving-utils' simple-bootloader
# pattern). Same statement as the SP1 side proves under SHA-256:
#
#   p        = 2^256 − 2^32 − 977            (secp256k1 prime)
#   σ_0      = Blake2s(circuit_bytes) reduced mod p   (RFC-0005)
#   σ_{i+1}  = (σ_i + (i + 1)) mod p          for i ∈ [0, gate_count)
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — proof emitted, stdout grammar satisfied
#   1 — prover failed (witness rejected, internal error, grammar violation)
#   2 — precondition violated (env var miss, affinity miss, missing fixture, etc.)
#   3 — build error (executable.json or proving-utils binary missing)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/wrapper_lib.sh"

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

if [[ $# -ne 2 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: bin/run_stwo.sh expects 2 args (fixtures_path, output_proof_path), got $#" >&2
  usage
  exit 2
fi

FIXTURES_PATH="$1"
OUTPUT_PROOF_PATH="$2"

if [[ ! -f "${FIXTURES_PATH}" || ! -r "${FIXTURES_PATH}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: fixtures file not readable: ${FIXTURES_PATH}" >&2
  exit 2
fi

# RFC-0007 §"Preconditions" — same four caps as SP1 wrapper.
require_env CUDA_VISIBLE_DEVICES ""
require_env RAYON_NUM_THREADS 1
require_env TOKIO_WORKER_THREADS 1
require_env OMP_NUM_THREADS 1

# RFC-0009 single-core affinity.
read -ra AFFINITY <<< "$(resolve_affinity)"

# -- locate dependencies ------------------------------------------------------

APPLES_PROVE_DEFAULT="${REPO_ROOT}/bin/apples-prove"
# `STWO_BINARY` overrides for development / tests. The override must
# accept `--fixtures <path> --output <path>` (the `apples-prove` and
# `run_<prover>.sh` symmetric CLI shape).
STWO_BINARY="${STWO_BINARY:-${APPLES_PROVE_DEFAULT}}"

if [[ ! -x "${STWO_BINARY}" ]]; then
  echo "BUILD.STWO_SHA_DRIFT: Stwo prover binary not built at ${STWO_BINARY}." >&2
  echo "Run \`scarb --manifest-path stwo-side/cairo/Scarb.toml build\` and" >&2
  echo "\`(cd third_party/proving-utils && cargo +nightly-2025-07-14 build --release -p stwo-run-and-prove)\`" >&2
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

if [[ ${PROVER_RC} -ne 0 ]]; then
  echo "PROVER.WITNESS_REJECTED: apples-prove exited ${PROVER_RC}" >&2
  exit 1
fi

if [[ ! -s "${TMP_PROOF}" ]]; then
  echo "PROVER.WITNESS_REJECTED: apples-prove succeeded but produced no proof bytes" >&2
  exit 1
fi

enforce_proverlog_grammar "${LOG_BUFFER}"

mv -- "${TMP_PROOF}" "${OUTPUT_PROOF_PATH}"
trap - EXIT
rm -f "${LOG_BUFFER}"

exit 0
