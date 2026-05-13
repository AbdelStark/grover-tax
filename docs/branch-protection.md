# Branch protection — `main`

Per RFC-0014 §"Branch protection". Branch protection lives outside `git`
itself — it is configured through the GitHub web UI or the GitHub REST
API. This document is the **specification** of what the maintainer must
configure on the live repo; `scripts/audit_branch_protection.sh` verifies
the live state against this spec.

## Required configuration

Protected branch: `main`.

| Setting | Value | Rationale |
|---|---|---|
| Restrict creations to admins | false | maintainer can land via PR |
| Allow force pushes | **false** | rewriting history on the release branch destroys the audit trail |
| Allow deletions | **false** | symmetric protection against accidental branch removal |
| Require a pull request before merging | **true** | every change reviewed |
| Required approving review count | 1 | the v0.1 maintainer set is one; the maintainer can self-approve via the GitHub API once another reviewer is on the team this is bumped to 1-from-CODEOWNERS |
| Require approval of the most recent reviewable push | **true** | force-pushed reviews don't bypass |
| Dismiss stale reviews on new commit | **true** | rewriting a PR re-requests review |
| Require review from CODEOWNERS | **true** | the methodology paths in `.github/CODEOWNERS` route every change to the maintainer |
| Require conversation resolution before merging | **true** | every PR comment must be resolved |
| Require status checks to pass before merging | **true** | the seven `ci.yml` jobs are required |
| Require branches to be up to date | **true** | the head must merge cleanly against `main` |
| Required status checks | `lint-python`, `test-python (ubuntu-latest)`, `test-python (macos-latest)`, `workload-pin`, `gen-fixtures-check`, `schema-validate`, `results-md-lint`, `workflow-lint` | every Python-side gate; Cairo / Rust gates from #48 / #49 get added once they ship |
| Require linear history | **true** | rebase + squash merge only |
| Restrict who can push to matching branches | maintainer + admins | non-maintainer pushes blocked at the protection layer |
| Lock branch (read-only) | false | not the release-cut workflow |

## How to apply

The maintainer applies the configuration via the GitHub web UI
(`Settings → Branches → Branch protection rules → Add rule`) or via the
REST API:

```bash
gh api -X PUT \
  /repos/AbdelStark/grover-tax/branches/main/protection \
  --input docs/branch-protection.template.json
```

`docs/branch-protection.template.json` (out of scope here — landed
post-v0.1 when the required-status-check list stabilises across #48 /
#49) carries the JSON payload that mirrors this table.

## Audit

`scripts/audit_branch_protection.sh` queries the live config via
`gh api` and asserts each field above matches. It exits 0 on agreement
and non-zero with a `BUILD.LICENSE_CHECK_FAIL`-style structured
diagnostic on drift. Wire it into CI as a weekly cron once #51 lands.

## Why protection lives outside git

The defence-in-depth here is structural: a defect in the Python or
Cairo source (RFC-0001 through RFC-0011) is what `git diff` catches.
A defect in *who can land what* is what branch protection catches.
Both are necessary; neither subsumes the other.

A misconfiguration that silently weakens protection (force-push enabled,
required reviews dropped to 0, status-check list shrunk) is
*invisible* to the source tree. The audit script + the periodic cron
make drift visible at most one week late — slow enough to skip the
hot-path overhead, fast enough to surface in advance of any
release cut.
