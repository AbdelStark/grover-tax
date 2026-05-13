#!/usr/bin/env bash
#
# audit_branch_protection.sh — verify `main` branch protection against
# `docs/branch-protection.md` (RFC-0014 §"Branch protection").
#
# Queries the live GitHub branch-protection config via `gh api` and asserts
# every load-bearing setting matches the table in `docs/branch-protection.md`.
# Exits 0 on full agreement; exits 7 with a structured diagnostic on any
# drift. Wire into CI as a weekly cron once branch protection stabilises.
#
# Exit code 7 was chosen to avoid colliding with the canonical 1..6 from
# `docs/spec/04-error-model.md` — branch-protection drift is a governance
# defect, not a measurement / build / fixture / prover / report failure.
#
# The script accepts a `REPO` env override; defaults to `AbdelStark/grover-tax`.

set -euo pipefail

REPO="${REPO:-AbdelStark/grover-tax}"
BRANCH="${BRANCH:-main}"

# Probe `gh` is available + authenticated.
if ! command -v gh >/dev/null 2>&1; then
  echo "audit_branch_protection: gh CLI not installed" >&2
  exit 7
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "audit_branch_protection: gh not authenticated; run 'gh auth login'" >&2
  exit 7
fi

ENDPOINT="repos/${REPO}/branches/${BRANCH}/protection"

# Fetch the live config. `gh api` returns JSON or a 404 if no protection is
# configured.
if ! LIVE="$(gh api "${ENDPOINT}" 2>/dev/null)"; then
  echo "audit_branch_protection: no branch-protection rule on ${REPO}@${BRANCH}" >&2
  echo "audit_branch_protection: apply the config from docs/branch-protection.md" >&2
  exit 7
fi

FAILURES=()

# Each check below extracts one boolean / numeric / array setting via jq and
# asserts it matches the spec table. The matrix is the *intersection* of
# RFC-0014 and the GitHub branch-protection API schema; settings the API
# names differently than the spec table use the API name in the comment.

# Helper: assert a jq selector evaluates to an expected literal value.
assert_jq_eq() {
  local label="$1" selector="$2" expected="$3"
  local actual
  actual="$(jq -r "${selector}" <<< "${LIVE}")"
  if [[ "${actual}" != "${expected}" ]]; then
    FAILURES+=("${label}: expected '${expected}', got '${actual}'")
  fi
}

# `allow_force_pushes.enabled` must be false.
assert_jq_eq "allow_force_pushes" '.allow_force_pushes.enabled' "false"

# `allow_deletions.enabled` must be false.
assert_jq_eq "allow_deletions" '.allow_deletions.enabled' "false"

# `enforce_admins.enabled` must be true (admins are not exempt).
assert_jq_eq "enforce_admins" '.enforce_admins.enabled' "true"

# Pull-request requirement.
assert_jq_eq "required_pr_review.required_approving_review_count" \
  '.required_pull_request_reviews.required_approving_review_count' "1"
assert_jq_eq "required_pr_review.dismiss_stale_reviews" \
  '.required_pull_request_reviews.dismiss_stale_reviews' "true"
assert_jq_eq "required_pr_review.require_code_owner_reviews" \
  '.required_pull_request_reviews.require_code_owner_reviews' "true"
assert_jq_eq "required_pr_review.require_last_push_approval" \
  '.required_pull_request_reviews.require_last_push_approval' "true"

# Status checks.
assert_jq_eq "required_status_checks.strict" \
  '.required_status_checks.strict' "true"

# Required-check list. Spec value (sorted, as JSON array):
EXPECTED_CHECKS='["gen-fixtures-check","lint-python","results-md-lint","schema-validate","test-python (macos-latest)","test-python (ubuntu-latest)","workflow-lint","workload-pin"]'
ACTUAL_CHECKS="$(jq -c '.required_status_checks.contexts | sort' <<< "${LIVE}")"
if [[ "${ACTUAL_CHECKS}" != "${EXPECTED_CHECKS}" ]]; then
  FAILURES+=("required_status_checks.contexts: expected ${EXPECTED_CHECKS}, got ${ACTUAL_CHECKS}")
fi

# Conversation resolution + linear history.
assert_jq_eq "required_conversation_resolution.enabled" \
  '.required_conversation_resolution.enabled' "true"
assert_jq_eq "required_linear_history.enabled" \
  '.required_linear_history.enabled' "true"
assert_jq_eq "lock_branch.enabled" '.lock_branch.enabled' "false"

if (( ${#FAILURES[@]} > 0 )); then
  echo "audit_branch_protection: ${#FAILURES[@]} drift(s) from docs/branch-protection.md:" >&2
  for f in "${FAILURES[@]}"; do
    echo "  - ${f}" >&2
  done
  exit 7
fi

echo "audit_branch_protection: ${REPO}@${BRANCH} matches docs/branch-protection.md"
exit 0
