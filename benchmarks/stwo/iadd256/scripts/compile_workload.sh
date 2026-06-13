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
    SRC="${ROOT}/cairo/iadd256_loop.cairo"
    OUT="${ROOT}/build/iadd256/compiled.json"
    ;;
  ec)
    STWO_CAIRO_ABS="$(abs_path_from_root "${ROOT}" "${STWO_CAIRO_ROOT}")"
    SRC="${STWO_CAIRO_ABS}/gpu_benchmarks/ec/ec_add.cairo"
    OUT="${ROOT}/build/ec/compiled.json"
    ;;
  *)
    echo "usage: $0 [iadd256|ec]" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname -- "${OUT}")"

echo "compile_workload: ${WORKLOAD}"
echo "  source: ${SRC}"
echo "  output: ${OUT}"

cairo-compile --proof_mode "${SRC}" --output "${OUT}"
jq -e . "${OUT}" >/dev/null

echo "compile_workload: wrote ${OUT}"
