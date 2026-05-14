#!/usr/bin/env bash
#
# measure_setup.sh — one-shot SP1 Groth16 trusted-setup capture (RFC-0008
# §"Setup-cost capture"). Captures M8 (wall-clock) + M9 (key sizes).
#
# Usage:
#   scripts/measure_setup.sh <run_id> [--origin=<text>]
#
# `--origin` defaults to `upstream-trusted-setup-v0.x` and ends up in
# `results/sp1_setup.json` as `groth16_ceremony_origin`. Use
# `--origin=reproduced-locally-non-trusted` for a locally-reproduced setup.
#
# Per RFC-0008 setup is captured *once* per `versions.lock`. The script
# refuses to overwrite an existing `results/sp1_setup.json` whose
# `versions_lock_sha256` matches the live lock — re-running would shadow
# the prior valid record.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/locale_env.sh"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: measure_setup.sh expects <run_id> [--origin=<text>]" >&2
  exit 2
fi

RUN_ID="$1"
ORIGIN="upstream-trusted-setup-v0.x"
if [[ $# -eq 2 ]]; then
  case "$2" in
    --origin=*) ORIGIN="${2#--origin=}" ;;
    *) echo "MEASUREMENT.ENV_VAR_MISS: unknown flag $2" >&2; exit 2 ;;
  esac
fi

if [[ -z "${ORIGIN}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: --origin must be non-empty (S-INV-1)" >&2
  exit 2
fi

# Tools.
if command -v gtime >/dev/null 2>&1; then
  GNU_TIME="gtime"
elif [[ -x /usr/bin/time ]]; then
  GNU_TIME="/usr/bin/time"
else
  echo "MEASUREMENT.ENV_VAR_MISS: GNU time not on PATH" >&2
  exit 5
fi

# SP1 setup binary path. Overridable for tests via SP1_SETUP_BINARY.
SP1_SETUP_BINARY_DEFAULT="${REPO_ROOT}/third_party/sp1/target/release/setup"
SP1_SETUP_BINARY="${SP1_SETUP_BINARY:-${SP1_SETUP_BINARY_DEFAULT}}"

# Output keys land under results/sp1_setup_keys/<run_id>/.
RESULTS_DIR="${REPO_ROOT}/results"
KEYS_DIR="${RESULTS_DIR}/sp1_setup_keys/${RUN_ID}"
mkdir -p "${KEYS_DIR}"

PROVING_KEY="${KEYS_DIR}/pk.bin"
VERIFYING_KEY="${KEYS_DIR}/vk.bin"
TIME_TXT="${KEYS_DIR}/setup.time.txt"

if [[ ! -x "${SP1_SETUP_BINARY}" ]]; then
  echo "BUILD.SP1_PATCH_FAIL: SP1 setup binary not built at ${SP1_SETUP_BINARY}" >&2
  echo "Run \`cd third_party/sp1 && cargo +1.93.0 build --release\` first." >&2
  exit 3
fi

# Compute versions.lock hash for idempotency.
VERSIONS_LOCK="${REPO_ROOT}/versions.lock"
if [[ -f "${VERSIONS_LOCK}" ]]; then
  if command -v shasum >/dev/null 2>&1; then
    LOCK_SHA="$(shasum -a 256 "${VERSIONS_LOCK}" | awk '{print $1}')"
  else
    LOCK_SHA="$(sha256sum "${VERSIONS_LOCK}" | awk '{print $1}')"
  fi
else
  LOCK_SHA="0000000000000000000000000000000000000000000000000000000000000000"
fi

OUT="${RESULTS_DIR}/sp1_setup.json"

# Idempotency: if an existing record matches the current lock SHA, refuse
# to overwrite (S-INV-2).
if [[ -f "${OUT}" ]]; then
  EXISTING_SHA="$(jq -r '.versions_lock_sha256 // ""' "${OUT}")"
  if [[ "${EXISTING_SHA}" == "${LOCK_SHA}" ]]; then
    echo "measure_setup.sh: ${OUT} already records this versions.lock hash; skip (use rm + re-run to redo)"
    exit 0
  fi
fi

# Time the setup. Capture wall / user / sys / RSS via gnu-time -v.
echo "measure_setup.sh: running SP1 Groth16 trusted setup..."
"${GNU_TIME}" -v -o "${TIME_TXT}" \
  "${SP1_SETUP_BINARY}" \
  --proving-key "${PROVING_KEY}" \
  --verifying-key "${VERIFYING_KEY}"

# Parse the time output.
WALL="$(awk '/Elapsed \(wall clock\)/ {print $NF}' "${TIME_TXT}")"
USER_CPU="$(awk '/User time \(seconds\)/ {print $NF}' "${TIME_TXT}")"
SYS_CPU="$(awk '/System time \(seconds\)/ {print $NF}' "${TIME_TXT}")"
PEAK_RSS_KB="$(awk '/Maximum resident set size/ {print $NF}' "${TIME_TXT}")"
PEAK_RSS_MIB="$(awk -v k="${PEAK_RSS_KB}" 'BEGIN { printf "%.2f", k / 1024 }')"

# `wall` from gnu-time looks like `0:42.13` or `1:23:45`; convert to seconds.
WALL_SECONDS="$(echo "${WALL}" | awk -F: '
  NF==2 { print $1 * 60 + $2 }
  NF==3 { print $1 * 3600 + $2 * 60 + $3 }
  NF==1 { print $1 }
')"

# Key sizes.
key_size() {
  local f="$1"
  if stat -f%z "$f" >/dev/null 2>&1; then
    stat -f%z "$f"   # BSD
  else
    stat -c%s "$f"   # GNU
  fi
}
PK_BYTES="$(key_size "${PROVING_KEY}")"
VK_BYTES="$(key_size "${VERIFYING_KEY}")"

# Emit the record. Includes `versions_lock_sha256` for idempotency tracking
# even though it isn't part of the published schema — Python-side
# validation strips it before schema-validate.
RECORD="$(jq -n \
  --argjson schema_version 1 \
  --arg run_id "${RUN_ID}" \
  --argjson wall_clock_s "${WALL_SECONDS}" \
  --argjson user_cpu_s "${USER_CPU}" \
  --argjson sys_cpu_s "${SYS_CPU}" \
  --argjson peak_rss_mib "${PEAK_RSS_MIB}" \
  --argjson proving_key_bytes "${PK_BYTES}" \
  --argjson verifying_key_bytes "${VK_BYTES}" \
  --arg groth16_ceremony_origin "${ORIGIN}" \
  --arg versions_lock_sha256 "${LOCK_SHA}" \
  '{
    schema_version: $schema_version,
    run_id: $run_id,
    wall_clock_s: $wall_clock_s,
    user_cpu_s: $user_cpu_s,
    sys_cpu_s: $sys_cpu_s,
    peak_rss_mib: $peak_rss_mib,
    proving_key_bytes: $proving_key_bytes,
    verifying_key_bytes: $verifying_key_bytes,
    groth16_ceremony_origin: $groth16_ceremony_origin,
    _versions_lock_sha256: $versions_lock_sha256
  }')"

# Atomic write.
TMP="${OUT}.partial.$$"
trap 'rm -f "${TMP}"' EXIT
echo "${RECORD}" > "${TMP}"
mv -- "${TMP}" "${OUT}"
trap - EXIT

# Schema-validate (strips the `_`-prefixed idempotency key first).
jq 'del(._versions_lock_sha256)' "${OUT}" > "${OUT}.canonical"
if ! (cd "${REPO_ROOT}" && uv run python -m grover_tax.validate_schemas \
        --schema setup-v1 "${OUT}.canonical" 2>&1); then
  echo "REPORT.SCHEMA_INVALID: emitted ${OUT} failed setup-v1 schema validation" >&2
  rm -f "${OUT}.canonical"
  exit 6
fi
rm -f "${OUT}.canonical"

echo "measure_setup.sh: wrote ${OUT} (origin: ${ORIGIN})"
exit 0
