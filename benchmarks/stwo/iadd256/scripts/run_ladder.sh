#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
load_config

ROOT="$(bench_root)"
WORKLOAD="${1:-iadd256}"

case "${WORKLOAD}" in
  iadd256)
    DEFAULT_NS="${IADD_NS:-1 10 100 1000 2000 4000 8000}"
    ;;
  ec)
    DEFAULT_NS="${EC_NS:-256 1024}"
    ;;
  *)
    echo "usage: $0 [iadd256|ec]" >&2
    exit 2
    ;;
esac

BACKENDS="${BACKENDS:-cuda simd}"
NS="${NS:-${DEFAULT_NS}}"
REPS="${REPS:-3}"

"${SCRIPT_DIR}/compile_workload.sh" "${WORKLOAD}"
"${SCRIPT_DIR}/build_gpu_bench.sh"

STWO_CAIRO_ABS="$(abs_path_from_root "${ROOT}" "${STWO_CAIRO_ROOT}")"
BIN="${STWO_CAIRO_ABS}/stwo_cairo_prover/target/release/gpu_bench"
PROGRAM="${ROOT}/build/${WORKLOAD}/compiled.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${ROOT}/results/${STAMP}_${WORKLOAD}.jsonl"
LOG="${ROOT}/results/${STAMP}_${WORKLOAD}.log"

echo "run_ladder: workload=${WORKLOAD}"
echo "run_ladder: program=${PROGRAM}"
echo "run_ladder: backends=${BACKENDS}"
echo "run_ladder: ns=${NS}"
echo "run_ladder: reps=${REPS}"
echo "run_ladder: jsonl=${OUT}"
echo "run_ladder: log=${LOG}"

for backend in ${BACKENDS}; do
  for n in ${NS}; do
    echo "run_ladder: backend=${backend} n=${n}" | tee -a "${LOG}" >&2
    "${BIN}" \
      --program "${PROGRAM}" \
      --iterations "${n}" \
      --backend "${backend}" \
      --reps "${REPS}" \
      2>>"${LOG}" | tee -a "${OUT}"
  done
done

"${ROOT}/scripts/summarize_jsonl.py" "${OUT}" > "${OUT%.jsonl}.summary.md"
echo "run_ladder: summary=${OUT%.jsonl}.summary.md"
