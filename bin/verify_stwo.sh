#!/usr/bin/env bash
#
# bin/verify_stwo.sh — Stwo (Cairo) verifier wrapper.
#
# Contract from `docs/rfcs/RFC-0007-wrapper-contract.md` §"`bin/verify_<prover>.sh`":
#
#   bin/verify_stwo.sh <proof_path>
#
# Symmetric with `bin/verify_sp1.sh`. Reads `fixtures/v0.1.json` from a fixed
# relative path (the cwd).
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — proof valid against the fixture; stdout is empty
#   1 — proof rejected (tampered or never valid); diagnostic on stderr
#   2 — harness-side precondition failure (missing args, missing files)

set -euo pipefail

FIXTURE_RELATIVE_PATH="fixtures/v0.1.json"

usage() {
  cat >&2 <<'EOF'
Usage: bin/verify_stwo.sh <proof_path>

Reads `fixtures/v0.1.json` from the current working directory.

Exit codes:
  0  proof valid; stdout empty
  1  proof rejected; diagnostic on stderr
  2  precondition violation (missing file, wrong argv shape)
EOF
}

if [[ $# -ne 1 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: bin/verify_stwo.sh expects 1 arg (proof_path), got $#" >&2
  usage
  exit 2
fi

PROOF_PATH="$1"

if [[ ! -f "${PROOF_PATH}" || ! -r "${PROOF_PATH}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: proof not readable: ${PROOF_PATH}" >&2
  exit 2
fi

if [[ ! -f "${FIXTURE_RELATIVE_PATH}" || ! -r "${FIXTURE_RELATIVE_PATH}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: ${FIXTURE_RELATIVE_PATH} not readable from $(pwd)" >&2
  exit 2
fi

STWO_VERIFIER_DEFAULT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/stwo-side/target/release/stwo_verify"
STWO_VERIFIER="${STWO_VERIFIER:-${STWO_VERIFIER_DEFAULT}}"

if [[ ! -x "${STWO_VERIFIER}" ]]; then
  echo "BUILD.STWO_SHA_DRIFT: Stwo verifier binary not built at ${STWO_VERIFIER}. (See RFC-0004.)" >&2
  exit 2
fi

set +e
"${STWO_VERIFIER}" --fixtures "${FIXTURE_RELATIVE_PATH}" --proof "${PROOF_PATH}" >/dev/null 2>/tmp/verify_stwo.err.$$
VERIFIER_RC=$?
set -e

if [[ ${VERIFIER_RC} -eq 0 ]]; then
  rm -f /tmp/verify_stwo.err.$$
  exit 0
fi

cat /tmp/verify_stwo.err.$$ >&2
rm -f /tmp/verify_stwo.err.$$
echo "PROVER.VERIFIER_REJECTED: stwo verifier exited ${VERIFIER_RC} on ${PROOF_PATH}" >&2
exit 1
