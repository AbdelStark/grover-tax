#!/usr/bin/env bash
#
# apply_sp1_patch.sh — apply every patch in `sp1-side-patches/` to
# the pinned `sp1-side/` submodule. Per RFC-0006 §"Apply / re-apply".
#
# Idempotent. A re-run on an already-patched tree:
#
#   * Verifies the patches are already in the working tree (by trying
#     `git apply --check --reverse`; if the reverse applies, the patch
#     is already there).
#   * Reports "already applied" and exits 0.
#
# Exit codes:
#   0 — every patch applied (or already in tree).
#   3 — `BUILD.SP1_PATCH_FAIL`: any patch failed to apply cleanly.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

SP1_DIR="${REPO_ROOT}/sp1-side"
PATCH_DIR="${REPO_ROOT}/sp1-side-patches"

if [[ ! -d "${SP1_DIR}" ]]; then
  echo "BUILD.SP1_PATCH_FAIL: ${SP1_DIR} does not exist; run scripts/init_submodules.sh first" >&2
  exit 3
fi
if [[ ! -d "${PATCH_DIR}" ]]; then
  echo "BUILD.SP1_PATCH_FAIL: ${PATCH_DIR} does not exist" >&2
  exit 3
fi

# Iterate over .patch files in sorted order (matches RFC-0006 §"Patch
# series" intent: 0001..0002..).
shopt -s nullglob
patches=("${PATCH_DIR}"/*.patch)
shopt -u nullglob

if (( ${#patches[@]} == 0 )); then
  echo "apply_sp1_patch: no patches to apply"
  exit 0
fi

cd "${SP1_DIR}"

for patch in "${patches[@]}"; do
  name="$(basename -- "${patch}")"
  if git apply --check --reverse "${patch}" 2>/dev/null; then
    echo "apply_sp1_patch: ${name} already applied; skipping"
    continue
  fi
  if ! git apply --check "${patch}" 2>/dev/null; then
    echo "BUILD.SP1_PATCH_FAIL: ${name} does not apply cleanly to ${SP1_DIR}" >&2
    echo "Possible causes:" >&2
    echo "  - sp1-side/ has uncommitted changes (run: git -C sp1-side checkout -- .)" >&2
    echo "  - WORKLOAD.md.upstream_commit drifted from the patch's target" >&2
    echo "  - the patch needs a refresh per RFC-0001 §\"Re-pinning\"" >&2
    exit 3
  fi
  echo "apply_sp1_patch: applying ${name}"
  git apply "${patch}"
done

echo "apply_sp1_patch: all patches applied"
exit 0
