#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRATE_DIR="${ROOT}/native-air"
FIXTURE="${FIXTURE:-${ROOT}/../../../fixtures/v0.3-iadd256-k4-n16.json}"
SAMPLES="${SAMPLES:-1 2 4 8 16 32 64 128 256 512}"
RANGE_CHECK="${RANGE_CHECK:-off}"
STORE_COEFFICIENTS="${STORE_COEFFICIENTS:-0}"
LOW_MEMORY="${LOW_MEMORY:-0}"
CHECK_KMX="${CHECK_KMX:-0}"
KMX_CHECK_SAMPLES="${KMX_CHECK_SAMPLES:-64}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${ROOT}/results"
JSONL="${OUT_DIR}/${STAMP}_native_iadd_air.jsonl"
LOG="${OUT_DIR}/${STAMP}_native_iadd_air.log"

mkdir -p "${OUT_DIR}"

EXTRA_ARGS=(--range-check "${RANGE_CHECK}")
if [[ "${STORE_COEFFICIENTS}" == "1" ]]; then
  EXTRA_ARGS+=(--store-coefficients)
fi
if [[ "${LOW_MEMORY}" == "1" ]]; then
  EXTRA_ARGS+=(--low-memory)
fi
if [[ "${CHECK_KMX}" == "1" ]]; then
  EXTRA_ARGS+=(--check-kmx --kmx-check-samples "${KMX_CHECK_SAMPLES}")
fi

(
  cd "${CRATE_DIR}"
  cargo +nightly-2025-07-14 build --release
  for samples in ${SAMPLES}; do
    target/release/native-iadd-air \
      --fixture "${FIXTURE}" \
      --samples "${samples}" \
      "${EXTRA_ARGS[@]}"
  done
) > >(tee -a "${JSONL}") 2> >(tee -a "${LOG}" >&2)

printf 'wrote %s\n' "${JSONL}"
printf 'wrote %s\n' "${LOG}"
