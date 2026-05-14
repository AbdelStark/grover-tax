#!/usr/bin/env bash
#
# init_submodules.sh — initialise and pin every submodule per `.gitmodules`.
#
# Idempotent: safe to re-run on any host. Sourced (or invoked directly)
# from `scripts/run_all.sh` (#37) as the first step before any build.
#
# Pinned commits live in the gitlink entries in `.gitmodules` + the index;
# `versions.lock` (#7) records the same SHAs at the project level so a
# drift detection check (`scripts/lock_versions.sh --dry-run` vs the
# committed file) catches stealth-bumps.
#
# Exit codes:
#   0 — every submodule is initialised and at the recorded SHA.
#   3 — `BUILD.STWO_SHA_DRIFT` (stwo) on any post-init mismatch.
#
# MVP note: SP1 source lives at `third_party/sp1/` as a vendored copy
# (not a submodule). This script no longer initialises sp1-side.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

# `git submodule update --init --depth 1 --recursive` clones any missing
# submodules and brings each to the SHA recorded in `.gitmodules`. The
# `--depth 1` shallow fetch is allowed because the only thing we care
# about is the pinned commit; the full history isn't on the measured
# path.
(
  cd "${REPO_ROOT}"
  git submodule update --init --depth 1 --recursive
)

# Post-init verification — assert each submodule's HEAD matches what
# `.gitmodules` + the index expects. `git submodule status` prefixes the
# SHA with ' ' (clean) or '+' (modified) or '-' (uninitialised). We
# accept only the clean prefix.
expect_clean() {
  local path="$1" expected_subcode="$2"
  local line
  line="$(git submodule status "${path}")"
  case "${line}" in
    " "*)
      echo "${path}: pinned at $(echo "${line}" | awk '{print $1}')"
      ;;
    "+"*)
      echo "${expected_subcode}: ${path} is at the wrong commit:" >&2
      echo "  ${line}" >&2
      exit 3
      ;;
    "-"*)
      echo "${expected_subcode}: ${path} is uninitialised after submodule update:" >&2
      echo "  ${line}" >&2
      exit 3
      ;;
    *)
      echo "${expected_subcode}: ${path} unexpected status: ${line}" >&2
      exit 3
      ;;
  esac
}

(
  cd "${REPO_ROOT}"
  expect_clean stwo BUILD.STWO_SHA_DRIFT
)
