#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
load_config

ROOT="$(bench_root)"
EXTERNAL="${ROOT}/external"
mkdir -p "${EXTERNAL}"

clone_or_update() {
  local url="$1"
  local ref="$2"
  local dir="$3"

  if [[ ! -d "${dir}/.git" ]]; then
    echo "setup_external: cloning ${url} -> ${dir}"
    git clone --branch "${ref}" "${url}" "${dir}"
    return
  fi

  echo "setup_external: updating ${dir}"
  if [[ -n "$(git -C "${dir}" status --porcelain)" ]]; then
    echo "setup_external: ${dir} has local changes; fetching only" >&2
    git -C "${dir}" fetch origin "${ref}"
    return
  fi

  git -C "${dir}" fetch origin "${ref}"
  git -C "${dir}" switch "${ref}" 2>/dev/null || git -C "${dir}" checkout "${ref}"
  git -C "${dir}" merge --ff-only "origin/${ref}" 2>/dev/null || true
}

GROVER_LOCAL="$(path_from_root "${ROOT}" "${GROVER_TAX_ROOT}")"
if [[ -f "${GROVER_LOCAL}/scripts/run_all.sh" ]]; then
  GROVER="${GROVER_LOCAL}"
  echo "setup_external: using grover-tax checkout at ${GROVER}"
else
  GROVER="${EXTERNAL}/grover-tax"
  clone_or_update "${GROVER_TAX_URL}" "${GROVER_TAX_REF}" "${GROVER}"
fi
clone_or_update "${ZKP_ECC_URL}" "${ZKP_ECC_REF}" "${EXTERNAL}/zkp_ecc"

echo "setup_external: grover-tax $(repo_head_line "${GROVER}")"
echo "setup_external: zkp_ecc    $(repo_head_line "${EXTERNAL}/zkp_ecc")"
