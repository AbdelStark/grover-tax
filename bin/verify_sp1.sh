#!/usr/bin/env bash
#
# bin/verify_sp1.sh — SP1 verifier wrapper.
#
# Contract from `docs/rfcs/RFC-0007-wrapper-contract.md` §"`bin/verify_<prover>.sh`":
#
#   bin/verify_sp1.sh <proof_path>
#
# Reads `fixtures/v0.1.json` from a fixed relative path (the cwd).
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — proof valid against the fixture; stdout is empty
#   1 — proof rejected (tampered or never valid); diagnostic on stderr
#   2 — harness-side precondition failure (missing args, missing files)

set -euo pipefail

FIXTURE_RELATIVE_PATH="fixtures/v0.1.json"

usage() {
  cat >&2 <<'EOF'
Usage: bin/verify_sp1.sh <proof_path>

Reads `fixtures/v0.1.json` from the current working directory.

Exit codes:
  0  proof valid; stdout empty
  1  proof rejected; diagnostic on stderr
  2  precondition violation (missing file, wrong argv shape)
EOF
}

# 1. Argument count.
if [[ $# -ne 1 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: bin/verify_sp1.sh expects 1 arg (proof_path), got $#" >&2
  usage
  exit 2
fi

PROOF_PATH="$1"

# 2. Proof file readable.
if [[ ! -f "${PROOF_PATH}" || ! -r "${PROOF_PATH}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: proof not readable: ${PROOF_PATH}" >&2
  exit 2
fi

# 3. Fixture readable from the fixed relative path.
if [[ ! -f "${FIXTURE_RELATIVE_PATH}" || ! -r "${FIXTURE_RELATIVE_PATH}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: ${FIXTURE_RELATIVE_PATH} not readable from $(pwd)" >&2
  exit 2
fi

# -- locate the SP1 verifier binary -------------------------------------------

SP1_VERIFIER_DEFAULT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/third_party/sp1/target/release/verifier"
SP1_VERIFIER="${SP1_VERIFIER:-${SP1_VERIFIER_DEFAULT}}"

if [[ ! -x "${SP1_VERIFIER}" ]]; then
  echo "BUILD.SP1_PATCH_FAIL: SP1 verifier binary not built at ${SP1_VERIFIER}. (See RFC-0006.)" >&2
  exit 2
fi

# -- invoke the verifier ------------------------------------------------------

set +e
"${SP1_VERIFIER}" --fixtures "${FIXTURE_RELATIVE_PATH}" --proof "${PROOF_PATH}" >/dev/null 2>/tmp/verify_sp1.err.$$
VERIFIER_RC=$?
set -e

if [[ ${VERIFIER_RC} -eq 0 ]]; then
  # Success path: stdout is empty (RFC-0007 §"Stdout / stderr").
  rm -f /tmp/verify_sp1.err.$$
  exit 0
fi

# Failure path: emit the verifier's stderr verbatim so the operator can see
# the diagnostic, then exit 1.
cat /tmp/verify_sp1.err.$$ >&2
rm -f /tmp/verify_sp1.err.$$
echo "PROVER.VERIFIER_REJECTED: sp1 verifier exited ${VERIFIER_RC} on ${PROOF_PATH}" >&2
exit 1
