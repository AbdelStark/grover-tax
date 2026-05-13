#!/usr/bin/env bash
#
# check_sp1_patch_budget.sh — RFC-0006 line-budget gate.
#
# Counts +/- lines in `sp1-side-patches/*.patch` per file changed and
# asserts each falls within the RFC-0006 budgets:
#
#   * any example-crate `.rs` file: ≤ 50 net lines
#   * any `Cargo.toml`:             ≤ 5 net lines
#
# Exit codes:
#   0 — every patch fits the budget.
#   3 — `BUILD.SP1_PATCH_FAIL`: at least one file's diff exceeds its budget.
#   2 — usage error.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

BUDGET_RS="${BUDGET_RS:-50}"
BUDGET_CARGO_TOML="${BUDGET_CARGO_TOML:-5}"

PATCH_DIR="${REPO_ROOT}/sp1-side-patches"
if [[ ! -d "${PATCH_DIR}" ]]; then
  echo "MEASUREMENT.ENV_VAR_MISS: ${PATCH_DIR} does not exist" >&2
  exit 2
fi

shopt -s nullglob
patches=("${PATCH_DIR}"/*.patch)
shopt -u nullglob

if (( ${#patches[@]} == 0 )); then
  echo "check_sp1_patch_budget: no patches to check"
  exit 0
fi

VIOLATIONS=()

for patch in "${patches[@]}"; do
  name="$(basename -- "${patch}")"
  # Parse the unified diff. Each `diff --git a/<path> b/<path>` opens a
  # per-file block; we sum + / - lines until the next `diff --git` or EOF.
  # `awk` is the right tool here: bounded buffer, no shelling out per line.
  while IFS=$'\t' read -r path adds dels; do
    if [[ -z "${path}" ]]; then continue; fi
    net=$(( adds + dels ))
    budget="${BUDGET_RS}"
    if [[ "${path}" == *Cargo.toml ]]; then
      budget="${BUDGET_CARGO_TOML}"
    fi
    if (( net > budget )); then
      VIOLATIONS+=("${name}: ${path}: ${net} net lines exceeds budget ${budget}")
    else
      echo "${name}: ${path}: ${net} net lines (budget ${budget}) OK"
    fi
  done < <(
    awk '
      /^diff --git/ {
        if (path) { print path "\t" adds "\t" dels }
        match($0, /b\/[^ ]+/)
        path = substr($0, RSTART + 2, RLENGTH - 2)
        adds = 0; dels = 0
        next
      }
      /^\+\+\+/ || /^---/ { next }
      /^\+/ { adds++ }
      /^-/  { dels++ }
      END { if (path) print path "\t" adds "\t" dels }
    ' "${patch}"
  )
done

if (( ${#VIOLATIONS[@]} > 0 )); then
  echo "BUILD.SP1_PATCH_FAIL: ${#VIOLATIONS[@]} line-budget violation(s):" >&2
  for v in "${VIOLATIONS[@]}"; do
    echo "  - ${v}" >&2
  done
  exit 3
fi

echo "check_sp1_patch_budget: all patches within budget"
exit 0
