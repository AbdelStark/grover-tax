#!/usr/bin/env bash
#
# iostat_capture.sh — M10 disk-write capture (RFC-0008, *informational*).
#
# Usage:
#   scripts/iostat_capture.sh <prover> <run_id>
#
# Samples `iostat` for ~5 seconds before/after exit and writes the
# accumulated bytes-written count to
# `results/<prover>_v0.1_<run_id>.iostat.json`.
#
# M10 is **informational only**. Per OPEN-Q-8.1 in RFC-0008, iostat
# overhead may itself bias M1 if run *during* the measured window. We
# sample at start + end of the series, not concurrently with the prover,
# and write a JSON record that `analyze.py` (#41) ingests but never
# treats as a discard signal.
#
# Exit codes:
#   0 — sample captured (even if iostat unavailable; emits a soft-skip note).
#   2 — usage error.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

if [[ $# -ne 2 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: iostat_capture.sh expects <prover> <run_id>, got $#" >&2
  exit 2
fi

PROVER="$1"
RUN_ID="$2"

OUT="${REPO_ROOT}/results/${PROVER}_v0.1_${RUN_ID}.iostat.json"
mkdir -p "$(dirname -- "${OUT}")"

PLATFORM="$(uname | tr '[:upper:]' '[:lower:]')"

sample_iostat() {
  case "${PLATFORM}" in
    darwin)
      if ! command -v iostat >/dev/null 2>&1; then
        echo ""
        return
      fi
      # macOS `iostat -d -w 1 -c 1` prints disk stats; second line carries
      # `KB/t tps MB/s` for the default disk.
      iostat -d -w 1 -c 1 2>/dev/null | tail -n 1
      ;;
    linux)
      if ! command -v iostat >/dev/null 2>&1; then
        echo ""
        return
      fi
      iostat -dxk 1 1 2>/dev/null | awk 'NF > 0 && !/Device|avg-cpu/ {sum += $7} END {print sum}'
      ;;
    *)
      echo ""
      ;;
  esac
}

BEFORE="$(sample_iostat || true)"
sleep 0.2
AFTER="$(sample_iostat || true)"

if [[ -z "${BEFORE}" && -z "${AFTER}" ]]; then
  jq -n \
    --arg prover "${PROVER}" \
    --arg run_id "${RUN_ID}" \
    --arg platform "${PLATFORM}" \
    '{
      schema_version: 1,
      prover: $prover,
      run_id: $run_id,
      platform: $platform,
      probe: "unavailable",
      bytes_written: null,
      note: "iostat not on PATH or platform unsupported; M10 is informational"
    }' > "${OUT}"
  exit 0
fi

jq -n \
  --arg prover "${PROVER}" \
  --arg run_id "${RUN_ID}" \
  --arg platform "${PLATFORM}" \
  --arg before "${BEFORE}" \
  --arg after "${AFTER}" \
  '{
    schema_version: 1,
    prover: $prover,
    run_id: $run_id,
    platform: $platform,
    probe: "iostat",
    bytes_written: null,
    before: $before,
    after: $after,
    note: "M10 informational; raw before/after samples retained for analyze.py"
  }' > "${OUT}"

exit 0
