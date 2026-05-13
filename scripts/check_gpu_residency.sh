#!/usr/bin/env bash
#
# check_gpu_residency.sh — cross-platform GPU residency check (RFC-0009).
#
# `scripts/measure.sh` (#32) runs this *before* and *after* every hyperfine
# series. Non-zero GPU residency mid-run invalidates the just-collected
# samples: a kernel-scheduled GPU workload steals memory bandwidth and
# induces frequency thermal throttling that biases CPU-side timings.
#
# Platform matrix:
#
#   * macOS, Apple Silicon:
#       `sudo powermetrics --samplers gpu_power -n 1 -i 1000`
#       Parses the "GPU Power: <float> mW" line. Threshold 0.5 mW.
#
#   * Linux, NVIDIA:
#       `nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits`
#       Returns watts. Threshold 1 W.
#
#   * Linux, AMD:
#       `rocm-smi` (parses `Average Power` line). Threshold 1 W.
#
#   * No GPU detected (no taskmaster / no nvidia-smi / no rocm-smi):
#       prints "no GPU detected" to stderr and exits 0.
#
# Exit codes:
#   0 — residency below threshold, *or* no GPU detected.
#   1 — residency exceeded threshold (`MEASUREMENT.GPU_RESIDENT`).
#   2 — unsupported platform / probe failed.
#
# The script writes one structured line to stdout:
#     gpu_residency platform=<darwin|linux> probe=<probe> power=<value><unit> threshold=<value><unit>
# so `measure.sh` can grep it into the run record.
#
# Setup note: on macOS, `sudo powermetrics` requires passwordless sudo for
# the operator. Document the `/etc/sudoers.d/powermetrics` setup in BUILD.md
# (issue #26).

set -euo pipefail

# Override hooks for tests — point at a stub that emits a known number.
# The defaults are the real tools; the tests inject `MACOS_POWERMETRICS_CMD`,
# `LINUX_NVIDIA_SMI_CMD`, `LINUX_ROCM_SMI_CMD`.
MACOS_POWERMETRICS_CMD="${MACOS_POWERMETRICS_CMD:-sudo -n powermetrics --samplers gpu_power -n 1 -i 1000}"
LINUX_NVIDIA_SMI_CMD="${LINUX_NVIDIA_SMI_CMD:-nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits}"
LINUX_ROCM_SMI_CMD="${LINUX_ROCM_SMI_CMD:-rocm-smi --showpower}"

# Thresholds in milliwatts (consistent unit across platforms).
THRESHOLD_MACOS_MW="${THRESHOLD_MACOS_MW:-500}"   # 0.5 W
THRESHOLD_LINUX_MW="${THRESHOLD_LINUX_MW:-1000}"  # 1 W

# `printf %.0f` would round 0.4 down on bash + dash; we always work in mW as
# an integer comparison via awk.
compare_mw() {
  # $1 = current_mw (may be decimal), $2 = threshold_mw (integer).
  # awk returns 0 / 1; we flip to the script's semantics (0 OK, 1 over).
  if awk -v c="$1" -v t="$2" 'BEGIN { exit (c <= t) ? 0 : 1 }'; then
    return 0
  else
    return 1
  fi
}

emit_line() {
  printf 'gpu_residency platform=%s probe=%s power=%smW threshold=%smW\n' \
    "$1" "$2" "$3" "$4"
}

# -- macOS path ---------------------------------------------------------------

check_macos() {
  # Use eval so the override env var can contain spaces. The default `sudo -n`
  # never prompts; if the operator hasn't set up passwordless sudo, the
  # command fails and we treat it as "probe failed".
  local raw
  if ! raw="$(eval "${MACOS_POWERMETRICS_CMD}" 2>/dev/null)"; then
    echo "MEASUREMENT.GPU_RESIDENT: powermetrics probe failed (passwordless sudo not configured?)" >&2
    exit 2
  fi

  # The line we want looks like:    "GPU Power: 0.4 mW"
  # Some hosts emit "GPU Active Power:" — accept either.
  local mw
  mw="$(echo "${raw}" | awk '
    /GPU (Active )?Power:[[:space:]]+/ {
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^[0-9.]+$/) { val = $i }
        if ($i == "mW") { print val; exit }
        if ($i == "W")  { printf "%s\n", val * 1000; exit }
      }
    }
  ')"

  if [[ -z "${mw}" ]]; then
    echo "MEASUREMENT.GPU_RESIDENT: could not parse 'GPU Power' from powermetrics output" >&2
    exit 2
  fi

  emit_line darwin powermetrics "${mw}" "${THRESHOLD_MACOS_MW}"

  if compare_mw "${mw}" "${THRESHOLD_MACOS_MW}"; then
    exit 0
  fi
  echo "MEASUREMENT.GPU_RESIDENT: macOS GPU power ${mw} mW above threshold ${THRESHOLD_MACOS_MW} mW" >&2
  exit 1
}

# -- Linux NVIDIA path --------------------------------------------------------

check_linux_nvidia() {
  local raw watts mw
  if ! raw="$(eval "${LINUX_NVIDIA_SMI_CMD}" 2>/dev/null | head -n1 | tr -d ' ')"; then
    echo "MEASUREMENT.GPU_RESIDENT: nvidia-smi probe failed" >&2
    exit 2
  fi
  if [[ -z "${raw}" ]]; then
    echo "MEASUREMENT.GPU_RESIDENT: nvidia-smi produced no output" >&2
    exit 2
  fi
  watts="${raw}"
  mw="$(awk -v w="${watts}" 'BEGIN { printf "%g", w * 1000 }')"

  emit_line linux nvidia-smi "${mw}" "${THRESHOLD_LINUX_MW}"

  if compare_mw "${mw}" "${THRESHOLD_LINUX_MW}"; then
    exit 0
  fi
  echo "MEASUREMENT.GPU_RESIDENT: Linux NVIDIA GPU power ${watts} W above threshold $(awk "BEGIN { print ${THRESHOLD_LINUX_MW} / 1000 }") W" >&2
  exit 1
}

# -- Linux AMD path -----------------------------------------------------------

check_linux_amd() {
  local raw watts mw
  if ! raw="$(eval "${LINUX_ROCM_SMI_CMD}" 2>/dev/null)"; then
    echo "MEASUREMENT.GPU_RESIDENT: rocm-smi probe failed" >&2
    exit 2
  fi
  watts="$(echo "${raw}" | awk '/Average Power|GPU Power/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9.]+$/) { print $i; exit } }')"
  if [[ -z "${watts}" ]]; then
    echo "MEASUREMENT.GPU_RESIDENT: could not parse rocm-smi output" >&2
    exit 2
  fi
  mw="$(awk -v w="${watts}" 'BEGIN { printf "%g", w * 1000 }')"
  emit_line linux rocm-smi "${mw}" "${THRESHOLD_LINUX_MW}"
  if compare_mw "${mw}" "${THRESHOLD_LINUX_MW}"; then
    exit 0
  fi
  echo "MEASUREMENT.GPU_RESIDENT: Linux AMD GPU power ${watts} W above threshold $(awk "BEGIN { print ${THRESHOLD_LINUX_MW} / 1000 }") W" >&2
  exit 1
}

# -- dispatcher ---------------------------------------------------------------

case "$(uname)" in
  Darwin)
    check_macos
    ;;
  Linux)
    if command -v nvidia-smi >/dev/null 2>&1; then
      check_linux_nvidia
    elif command -v rocm-smi >/dev/null 2>&1; then
      check_linux_amd
    else
      echo "no GPU detected (neither nvidia-smi nor rocm-smi on PATH)" >&2
      exit 0
    fi
    ;;
  *)
    echo "MEASUREMENT.GPU_RESIDENT: unsupported platform $(uname)" >&2
    exit 2
    ;;
esac
