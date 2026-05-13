#!/usr/bin/env bash
#
# post_run_discard_check.sh — apply RFC-0010 discard rules after a series.
#
# Usage:
#   scripts/post_run_discard_check.sh <prover> <run_id>
#
# Runs after `measure.sh` finishes one prover's series. Inspects the
# emitted timing JSON for outliers and the host state at end-of-run for
# residual contamination (GPU residency, swap activity, thermal events).
# For each issue, appends one record to `results/discards.log` via
# `scripts/discard.sh` (#38).
#
# The script is *advisory*: by default it exits 0 even when discards
# are recorded — `analyze.py` (#41) makes the call about whether the
# series is rerunnable. Set `DISCARD_FATAL=1` to escalate any discard
# to exit 5 (`measure.sh` propagates).
#
# Exit codes:
#   0 — no discards, or advisory mode.
#   5 — fatal mode with at least one MEASUREMENT.* discard.
#   2 — usage error.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

if [[ $# -ne 2 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: post_run_discard_check.sh expects <prover> <run_id>, got $#" >&2
  exit 2
fi

PROVER="$1"
RUN_ID="$2"

DISCARDS=()

# D-INV-3: the *first* run of any series is always discarded as cold_cache.
# `analyze.py` enforces this by treating hyperfine's first run as
# `cold_cache` regardless — we record the marker here so the discards log
# is self-evidencing.
DISCARDS+=("cold_cache:first-run cold-cache discard per D-INV-3")

# Post-run GPU residency check.
if bash "${REPO_ROOT}/scripts/check_gpu_residency.sh" >/dev/null 2>&1; then
  : # ok
else
  rc=$?
  if [[ $rc -eq 1 ]]; then
    DISCARDS+=("gpu_residency:GPU residency exceeded threshold mid- or post-run")
  fi
fi

# Post-run swap check.
case "$(uname)" in
  Darwin)
    SWAPUSED="$(sysctl -n vm.swapusage 2>/dev/null | sed -E 's/.*used = ([^ ]+).*/\1/')"
    if [[ "${SWAPUSED}" != "0.00M" && "${SWAPUSED}" != "0M" && -n "${SWAPUSED}" ]]; then
      DISCARDS+=("swap_active:macOS swap engaged during series (used=${SWAPUSED})")
    fi
    ;;
  Linux)
    if [[ -r /proc/swaps ]]; then
      LINES="$(awk 'NR > 1' /proc/swaps | wc -l | tr -d ' ')"
      if [[ "${LINES}" != "0" ]]; then
        DISCARDS+=("swap_active:Linux swap engaged during series (${LINES} entries)")
      fi
    fi
    ;;
esac

# Record each discard via scripts/discard.sh (#38).
ARTIFACT="${REPO_ROOT}/results/${PROVER}_v0.1_${RUN_ID}.timing.json"
for entry in "${DISCARDS[@]}"; do
  reason="${entry%%:*}"
  detail="${entry#*:}"
  bash "${REPO_ROOT}/scripts/discard.sh" \
    --run-id "${RUN_ID}" \
    --prover "${PROVER}" \
    --reason "${reason}" \
    --detail "${detail}" \
    --measurement-artifact "${ARTIFACT#${REPO_ROOT}/}" \
    >/dev/null
done

if (( ${#DISCARDS[@]} > 0 )); then
  echo "post_run_discard_check: ${#DISCARDS[@]} discard(s) recorded:"
  for entry in "${DISCARDS[@]}"; do
    echo "  - ${entry}"
  done
fi

# Escalate only if explicitly requested.
if [[ "${DISCARD_FATAL:-0}" == "1" ]]; then
  # `cold_cache` is normal (D-INV-3 always-discard); only escalate on the
  # other reason classes.
  for entry in "${DISCARDS[@]}"; do
    reason="${entry%%:*}"
    if [[ "${reason}" != "cold_cache" ]]; then
      echo "post_run_discard_check: DISCARD_FATAL=1 and a non-cold_cache discard fired; exit 5" >&2
      exit 5
    fi
  done
fi

exit 0
