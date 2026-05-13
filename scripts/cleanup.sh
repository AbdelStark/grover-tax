#!/usr/bin/env bash
#
# cleanup.sh — restore the host state recorded by `preflight.sh`.
#
# Reads `${PREFLIGHT_STATE_PATH:-/tmp/grover-tax-preflight-state.json}`
# and reverses any state changes the operator made before the measured
# series. Today the script restores nothing automatically — `preflight.sh`
# doesn't *change* state, only asserts that the operator has set it
# correctly. `cleanup.sh` removes the state file and logs what *would*
# need restoring on a future host where preflight does flip switches.
#
# Future-facing: if a later RFC adds host-state changes (e.g. setting
# `scaling_governor=performance` programmatically), the restore step
# lands here.
#
# Exit codes:
#   0 — cleanup completed (or no state file to clean).
#   2 — usage / probe error.

set -euo pipefail

PREFLIGHT_STATE_PATH="${PREFLIGHT_STATE_PATH:-/tmp/grover-tax-preflight-state.json}"

if [[ ! -f "${PREFLIGHT_STATE_PATH}" ]]; then
  echo "cleanup: no state file at ${PREFLIGHT_STATE_PATH}; nothing to restore"
  exit 0
fi

PLATFORM="$(jq -r '.platform // ""' "${PREFLIGHT_STATE_PATH}")"
echo "cleanup: restoring state for ${PLATFORM} (recorded by preflight)"

# Today we log the recorded prior state for the operator to compare against
# the live state. A real host-state restore (low-power mode, governor,
# swap) would happen here.
echo "  recorded state:"
jq -r 'to_entries[] | "    \(.key): \(.value)"' "${PREFLIGHT_STATE_PATH}"

rm -f "${PREFLIGHT_STATE_PATH}"
echo "cleanup: state file removed"
exit 0
