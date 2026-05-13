#!/usr/bin/env bash
#
# check_workload.sh — RFC-0001 workload-pinning CI gate.
#
# Exits 4 (`FIXTURE.WORKLOAD_NOT_PINNED`) if `WORKLOAD.md` is missing,
# contains any `TBD` value, or does not record `upstream_commit` as a
# 40-character lowercase hex SHA in the frontmatter.
#
# Exit codes are aligned with `docs/spec/04-error-model.md`:
#   0 — pinned and well-formed
#   4 — FIXTURE.WORKLOAD_NOT_PINNED
#
# Anything outside `{0, 4}` from this script is unspecified and indicates a defect.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
WORKLOAD_MD="${REPO_ROOT}/WORKLOAD.md"

if [[ ! -f "${WORKLOAD_MD}" ]]; then
  echo "FIXTURE.WORKLOAD_NOT_PINNED: WORKLOAD.md missing at repo root" >&2
  exit 4
fi

# Any literal token `TBD` (word-boundary) anywhere in the file is a hard fail.
if grep -qE '\bTBD\b' "${WORKLOAD_MD}"; then
  echo "FIXTURE.WORKLOAD_NOT_PINNED: WORKLOAD.md still contains TBD" >&2
  exit 4
fi

# The `upstream_commit` frontmatter key must be a 40-char lowercase hex SHA.
if ! grep -qE '^upstream_commit: [0-9a-f]{40}$' "${WORKLOAD_MD}"; then
  echo "FIXTURE.WORKLOAD_NOT_PINNED: upstream_commit malformed (want 40-char hex SHA)" >&2
  exit 4
fi

exit 0
