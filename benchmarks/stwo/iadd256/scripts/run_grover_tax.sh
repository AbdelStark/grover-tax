#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
load_config

ROOT="$(bench_root)"
GROVER="$(path_from_root "${ROOT}" "${GROVER_TAX_ROOT}")"

if [[ ! -f "${GROVER}/scripts/run_all.sh" ]]; then
  "${SCRIPT_DIR}/setup_external.sh"
  GROVER="${ROOT}/external/grover-tax"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="${ROOT}/results/${STAMP}_grover_tax_run_all.log"

echo "run_grover_tax: repo=${GROVER}"
echo "run_grover_tax: head=$(repo_head_line "${GROVER}")"
echo "run_grover_tax: log=${LOG}"

cd "${GROVER}"
./scripts/run_all.sh 2>&1 | tee "${LOG}"
