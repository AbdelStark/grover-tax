#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
load_config

ROOT="$(bench_root)"
STWO_ABS="$(abs_path_from_root "${ROOT}" "${STWO_ROOT}")"
STWO_CAIRO_ABS="$(abs_path_from_root "${ROOT}" "${STWO_CAIRO_ROOT}")"
PROVER_DIR="${STWO_CAIRO_ABS}/stwo_cairo_prover"

echo "build_gpu_bench: stwo       $(repo_branch_line "${STWO_ABS}")"
echo "build_gpu_bench: stwo       $(repo_head_line "${STWO_ABS}")"
echo "build_gpu_bench: stwo-cairo $(repo_branch_line "${STWO_CAIRO_ABS}")"
echo "build_gpu_bench: stwo-cairo $(repo_head_line "${STWO_CAIRO_ABS}")"

if ! git -C "${STWO_ABS}" status --short --branch | head -1 | grep -q 'perf-optimizations'; then
  echo "warning: ${STWO_ABS} is not on a branch named perf-optimizations" >&2
fi
if ! git -C "${STWO_CAIRO_ABS}" status --short --branch | head -1 | grep -q 'generic-backend'; then
  echo "warning: ${STWO_CAIRO_ABS} is not on a branch named generic-backend" >&2
fi

cd "${PROVER_DIR}"
RUSTFLAGS="${RUSTFLAGS:--C target-cpu=native -C opt-level=3}" \
  cargo build --release -p stwo-cairo-prover --bin gpu_bench

echo "build_gpu_bench: ${PROVER_DIR}/target/release/gpu_bench"
