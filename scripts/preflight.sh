#!/usr/bin/env bash
#
# preflight.sh — assert every measurement precondition before the run series.
#
# Per RFC-0010 §"`preflight.sh`" the script:
#
#   * detects the host platform (darwin / linux);
#   * runs every applicable environmental check;
#   * records prior state to /tmp/grover-tax-preflight-state.json so
#     `cleanup.sh` can restore it.
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — every check passed.
#   5 — `measure.sh`-side precondition failed (one of:
#       `MEASUREMENT.ENV_VAR_MISS`, `MEASUREMENT.AFFINITY_MISS`,
#       `MEASUREMENT.AC_POWER_MISS`, `MEASUREMENT.LOWPOWER_ENABLED`,
#       `MEASUREMENT.GOVERNOR_MISS`, `MEASUREMENT.SWAP_ACTIVE`,
#       `MEASUREMENT.GPU_RESIDENT`, `MEASUREMENT.VERSIONS_DRIFT`).
#   2 — usage / probe error.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/locale_env.sh"

# State file path — overridable for tests.
PREFLIGHT_STATE_PATH="${PREFLIGHT_STATE_PATH:-/tmp/grover-tax-preflight-state.json}"

# Skip-driver hooks. Each can be set to "1" to bypass that check (used by
# tests and by `run_all.sh --skip` flags). The defaults run every check.
SKIP_AC_POWER="${SKIP_AC_POWER:-0}"
SKIP_LOWPOWER="${SKIP_LOWPOWER:-0}"
SKIP_GOVERNOR="${SKIP_GOVERNOR:-0}"
SKIP_SWAP="${SKIP_SWAP:-0}"
SKIP_ENV_CAPS="${SKIP_ENV_CAPS:-0}"
SKIP_VERSIONS_DRIFT="${SKIP_VERSIONS_DRIFT:-0}"
SKIP_GPU_RESIDENCY="${SKIP_GPU_RESIDENCY:-0}"

VIOLATIONS=()
PRIOR_STATE_JSON='{"platform":""}'

record_prior_state() {
  # Append a key→value pair to PRIOR_STATE_JSON via jq.
  PRIOR_STATE_JSON="$(jq -c --arg k "$1" --arg v "$2" '. + {($k): $v}' <<< "${PRIOR_STATE_JSON}")"
}

violation() {
  VIOLATIONS+=("$1")
}

PLATFORM="$(uname | tr '[:upper:]' '[:lower:]')"
record_prior_state platform "${PLATFORM}"

# -- env caps (all platforms) ------------------------------------------------

check_env_caps() {
  if [[ "${SKIP_ENV_CAPS}" == "1" ]]; then return; fi
  local var want got
  for pair in 'CUDA_VISIBLE_DEVICES=' 'RAYON_NUM_THREADS=1' 'TOKIO_WORKER_THREADS=1' 'OMP_NUM_THREADS=1'; do
    var="${pair%%=*}"
    want="${pair#*=}"
    got="${!var-__UNSET__}"
    if [[ "${got}" != "${want}" ]]; then
      violation "MEASUREMENT.ENV_VAR_MISS: ${var}='${got}' but harness requires '${want}'"
    fi
  done
}

# -- versions.lock drift -----------------------------------------------------

check_versions_drift() {
  if [[ "${SKIP_VERSIONS_DRIFT}" == "1" ]]; then return; fi
  if [[ ! -f "${REPO_ROOT}/versions.lock" ]]; then
    # Pre-#7: no committed lock yet. Treat as soft warning, not violation.
    echo "preflight: versions.lock not yet committed (#7 pending); skipping drift check" >&2
    return
  fi
  local actual expected
  actual="$(DRY=1 bash "${REPO_ROOT}/scripts/lock_versions.sh")"
  expected="$(cat "${REPO_ROOT}/versions.lock")"
  if [[ "$(jq 'del(.generated_at, .generator_commit)' <<<"${actual}")" \
        != "$(jq 'del(.generated_at, .generator_commit)' <<<"${expected}")" ]]; then
    violation "MEASUREMENT.VERSIONS_DRIFT: live toolchain differs from versions.lock"
  fi
}

# -- GPU residency -----------------------------------------------------------

check_gpu_residency() {
  if [[ "${SKIP_GPU_RESIDENCY}" == "1" ]]; then return; fi
  if ! bash "${REPO_ROOT}/scripts/check_gpu_residency.sh" >/dev/null 2>&1; then
    local rc=$?
    if [[ $rc -eq 1 ]]; then
      violation "MEASUREMENT.GPU_RESIDENT: GPU is in use; see check_gpu_residency.sh"
    fi
    # rc=2 means "probe failed" (no passwordless sudo on macOS); treat as a
    # soft skip per RFC-0009 §"GPU residency check" notes.
  fi
}

# -- swap --------------------------------------------------------------------

check_swap() {
  if [[ "${SKIP_SWAP}" == "1" ]]; then return; fi
  if [[ "${PLATFORM}" == "darwin" ]]; then
    local swapused
    swapused="$(sysctl -n vm.swapusage 2>/dev/null | sed -E 's/.*used = ([^ ]+).*/\1/')"
    record_prior_state swapused "${swapused}"
    if [[ "${swapused}" != "0.00M" && "${swapused}" != "0M" && "${swapused}" != "" ]]; then
      violation "MEASUREMENT.SWAP_ACTIVE: macOS swap in use (${swapused})"
    fi
  elif [[ "${PLATFORM}" == "linux" ]]; then
    if [[ -r /proc/swaps ]]; then
      local lines
      lines="$(awk 'NR > 1' /proc/swaps | wc -l | tr -d ' ')"
      record_prior_state swap_lines "${lines}"
      if [[ "${lines}" != "0" ]]; then
        violation "MEASUREMENT.SWAP_ACTIVE: Linux swap is active (${lines} entries in /proc/swaps)"
      fi
    fi
  fi
}

# -- AC power (macOS) --------------------------------------------------------

check_ac_power() {
  if [[ "${SKIP_AC_POWER}" == "1" || "${PLATFORM}" != "darwin" ]]; then return; fi
  local ps_out
  ps_out="$(pmset -g ps 2>/dev/null || true)"
  record_prior_state pmset_ps "${ps_out}"
  if [[ "${ps_out}" != *"AC Power"* ]]; then
    violation "MEASUREMENT.AC_POWER_MISS: macOS not on AC power"
  fi
}

# -- Low-power mode (macOS) --------------------------------------------------

check_lowpower() {
  if [[ "${SKIP_LOWPOWER}" == "1" || "${PLATFORM}" != "darwin" ]]; then return; fi
  local lp
  lp="$(pmset -g 2>/dev/null | awk '/lowpowermode/ {print $2}' | head -n1)"
  record_prior_state lowpowermode "${lp}"
  if [[ "${lp}" == "1" ]]; then
    violation "MEASUREMENT.LOWPOWER_ENABLED: macOS low-power mode is on"
  fi
}

# -- Governor / no_turbo (Linux) ---------------------------------------------

check_governor() {
  if [[ "${SKIP_GOVERNOR}" == "1" || "${PLATFORM}" != "linux" ]]; then return; fi
  local gov no_turbo
  gov="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
  no_turbo="$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo unknown)"
  record_prior_state scaling_governor "${gov}"
  record_prior_state no_turbo "${no_turbo}"
  if [[ "${gov}" != "performance" ]]; then
    violation "MEASUREMENT.GOVERNOR_MISS: scaling_governor=${gov}, want performance"
  fi
  if [[ "${no_turbo}" != "1" && "${no_turbo}" != "unknown" ]]; then
    violation "MEASUREMENT.GOVERNOR_MISS: intel_pstate/no_turbo=${no_turbo}, want 1"
  fi
}

# -- main -------------------------------------------------------------------

check_env_caps
check_versions_drift
check_swap
check_ac_power
check_lowpower
check_governor
check_gpu_residency

# Persist prior state so cleanup.sh can restore it.
mkdir -p "$(dirname -- "${PREFLIGHT_STATE_PATH}")"
echo "${PRIOR_STATE_JSON}" > "${PREFLIGHT_STATE_PATH}"

if (( ${#VIOLATIONS[@]} > 0 )); then
  echo "preflight: ${#VIOLATIONS[@]} precondition violation(s):" >&2
  for v in "${VIOLATIONS[@]}"; do
    echo "  - ${v}" >&2
  done
  exit 5
fi

echo "preflight: ${PLATFORM} clean — state recorded at ${PREFLIGHT_STATE_PATH}"
exit 0
