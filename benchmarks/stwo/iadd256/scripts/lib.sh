#!/usr/bin/env bash
set -euo pipefail

script_dir() {
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd
}

bench_root() {
  cd -- "$(script_dir)/.." >/dev/null 2>&1 && pwd
}

load_config() {
  local root
  root="$(bench_root)"
  if [[ -f "${root}/config.env" ]]; then
    # shellcheck source=/dev/null
    source "${root}/config.env"
  fi
  STWO_ROOT="${STWO_ROOT:-../../../../stwo}"
  STWO_CAIRO_ROOT="${STWO_CAIRO_ROOT:-../../../../stwo-cairo}"
  GROVER_TAX_ROOT="${GROVER_TAX_ROOT:-../../..}"
  GROVER_TAX_URL="${GROVER_TAX_URL:-https://github.com/AbdelStark/grover-tax.git}"
  GROVER_TAX_REF="${GROVER_TAX_REF:-main}"
  ZKP_ECC_URL="${ZKP_ECC_URL:-https://github.com/tanujkhattar/zkp_ecc.git}"
  ZKP_ECC_REF="${ZKP_ECC_REF:-update_examples}"
}

path_from_root() {
  local root="$1"
  local path="$2"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    printf '%s/%s\n' "${root}" "${path}"
  fi
}

abs_path_from_root() {
  local root="$1"
  local path="$2"
  cd -- "$(path_from_root "${root}" "${path}")" >/dev/null 2>&1 && pwd
}

repo_head_line() {
  local dir="$1"
  git -C "${dir}" log -1 --oneline 2>/dev/null || printf 'not-a-git-checkout\n'
}

repo_branch_line() {
  local dir="$1"
  git -C "${dir}" status --short --branch 2>/dev/null | head -1 || printf 'not-a-git-checkout\n'
}
