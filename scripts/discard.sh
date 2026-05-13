#!/usr/bin/env bash
#
# discard.sh — append one record to `results/discards.log`.
#
# Companion to `grover_tax.discards.append_discard`. Lets bash-side harness
# scripts emit a discard record without spawning Python. Constructs the JSON
# with `jq` (which `versions.lock` will record under the host toolchain
# matrix once #6 lands) and appends through a `flock` on the log file so
# concurrent writers from Python and bash interleave at line boundaries.
#
# Usage:
#   scripts/discard.sh \
#     --run-id 1715610912-abcd123 \
#     --prover sp1 \
#     --reason thermal \
#     --detail "P-core T = 97C above 95C threshold" \
#     --measurement-artifact results/sp1_v0.1_1715610912-abcd123.timing.json
#
# Exit codes:
#   0  — record appended
#   2  — usage error (missing required flag, unknown flag, invalid value)
#
# The `reason` value is validated against the same enum as the Python
# writer; anything else exits 2 *without* writing.

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/discard.sh --run-id ID --prover sp1|stwo --reason REASON \
                          --detail "free-form text" \
                          --measurement-artifact PATH \
                          [--log-path PATH]

REASON must be one of:
  thermal | gpu_residency | swap_active | cold_cache | env_var_miss | other
EOF
}

# Defaults (resolved against repo root, not $PWD).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
LOG_PATH_DEFAULT="${REPO_ROOT}/results/discards.log"

RUN_ID=""
PROVER=""
REASON=""
DETAIL=""
ARTIFACT=""
LOG_PATH="${LOG_PATH_DEFAULT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)                RUN_ID="$2"; shift 2 ;;
    --prover)                PROVER="$2"; shift 2 ;;
    --reason)                REASON="$2"; shift 2 ;;
    --detail)                DETAIL="$2"; shift 2 ;;
    --measurement-artifact)  ARTIFACT="$2"; shift 2 ;;
    --log-path)              LOG_PATH="$2"; shift 2 ;;
    -h|--help)               usage; exit 0 ;;
    *)                       echo "discard.sh: unknown flag: $1" >&2; usage; exit 2 ;;
  esac
done

# Required flags.
for var in RUN_ID PROVER REASON DETAIL ARTIFACT; do
  if [[ -z "${!var}" ]]; then
    echo "discard.sh: --${var,,} is required" >&2
    usage
    exit 2
  fi
done

# Enum validation — must agree with grover_tax.discards.DiscardReason.
case "${REASON}" in
  thermal|gpu_residency|swap_active|cold_cache|env_var_miss|other) ;;
  *) echo "discard.sh: reason '${REASON}' not in enum" >&2; usage; exit 2 ;;
esac

case "${PROVER}" in
  sp1|stwo) ;;
  *) echo "discard.sh: prover must be 'sp1' or 'stwo', got '${PROVER}'" >&2; exit 2 ;;
esac

# Build the record with `jq` so we never hand-format JSON.
RECORD=$(
  jq -c -n \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg run_id "${RUN_ID}" \
    --arg prover "${PROVER}" \
    --arg reason "${REASON}" \
    --arg detail "${DETAIL}" \
    --arg measurement_artifact "${ARTIFACT}" \
    '{ts: $ts, run_id: $run_id, prover: $prover, reason: $reason, detail: $detail, measurement_artifact: $measurement_artifact}'
)

mkdir -p "$(dirname -- "${LOG_PATH}")"

# Serialise concurrent writers (Python's `fcntl.flock` + other bash callers).
# `flock` from util-linux is portable on Linux; macOS does not ship it by
# default, so the script falls back to an atomic `mkdir`-based spinlock when
# `flock` is unavailable. Both lock the same well-known path next to the log
# file, so cross-tool exclusion holds.
LOCK_DIR="${LOG_PATH}.lock.d"

if command -v flock >/dev/null 2>&1; then
  exec 9>>"${LOG_PATH}"
  flock -x -w 30 9
  printf '%s\n' "${RECORD}" >&9
  flock -u 9
  exec 9>&-
else
  # macOS fallback. The `mkdir` syscall is atomic; `trap` releases the lock
  # on every exit path including signals.
  end=$(( SECONDS + 30 ))
  while ! mkdir "${LOCK_DIR}" 2>/dev/null; do
    if (( SECONDS >= end )); then
      echo "discard.sh: lock timeout after 30s on ${LOCK_DIR}" >&2
      exit 2
    fi
    sleep 0.05
  done
  trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT
  printf '%s\n' "${RECORD}" >>"${LOG_PATH}"
  rmdir "${LOCK_DIR}"
  trap - EXIT
fi
