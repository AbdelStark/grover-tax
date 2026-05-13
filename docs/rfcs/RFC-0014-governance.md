# RFC-0014: Repository governance, licensing, CI, contributor workflow

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

This RFC fixes the public-repo discipline that makes the benchmark trustworthy and contributable: licensing, submodule consumption, CI gates, branch protection, PR review, contributor onboarding, code of conduct, security policy. Most of these are unremarkable open-source practice; this RFC documents them so a contributor can find them in one place.

## Motivation

A public-from-day-one MIT-licensed benchmark needs governance plumbing. Without it, fixture-tampering PRs, drive-by performance "improvements" that bias measurements, or supply-chain attempts have no defence. With it, the same plumbing provides clear contribution paths for genuine improvements.

## Goals

- Choose and apply an OSI-approved licence (MIT).
- Define CI gates that enforce: schema validation, methodology lints, line-budget on the SP1 patch, gen-fixtures --check, wrapper symmetry, license compatibility.
- Define a CODEOWNERS scheme that routes reviews of methodology-critical files (`fixtures/`, `WORKLOAD.md`, `RESULTS.md`, `docs/spec/`, `docs/rfcs/`) to maintainers.
- Define how upstream submodules (SP1, Stwo) are consumed and bumped.
- Provide a `CONTRIBUTING.md` and `SECURITY.md`.

## Non-Goals

- Building out a contributor leaderboard, OS-style governance committees, or RFC-acceptance processes beyond what this repo needs.
- Multi-maintainer voting; for `v0.1`, the maintainer set is one.

## Proposed Design

### Licensing

- Repo root: **MIT**. Recorded in `LICENSE` and `pyproject.toml`'s `license` field.
- `SPDX-License-Identifier: MIT` header in non-trivial source files.
- Upstream submodules retain their licences (SP1: Apache-2.0 typically; Stwo: Apache-2.0 / MIT; Cairo: Apache-2.0). MIT redistribution is compatible with Apache-2.0 by inclusion of upstream LICENSE files in the source tree.
- `scripts/check_licenses.sh` enumerates submodule licences and fails the build if any non-MIT-compatible licence appears. Runs as the first step of `run_all.sh` and as a CI gate.

### Submodule consumption

Two consumption models for upstream:

1. **Git submodule** at a pinned SHA. Used for `sp1-side/` (`tanujkhattar/zkp_ecc`) — the patch-on-submodule pattern matches `RFC-0006`.
2. **Cargo dependency** at a pinned SHA (`stwo = { git = "...", rev = "<sha>" }` in `Cargo.toml`). Used for `stwo` itself if we do not need source-tree access; otherwise, git submodule.

Decision: `tanujkhattar/zkp_ecc` is a git submodule (patch required). `starkware-libs/stwo` is **a git submodule** as well, because we need source-tree access for testing and version verification. Cargo dependency-by-rev is a fallback if submodule update turns out to be painful.

Both consumption modes record their pin in `versions.lock`.

### CI matrix

GitHub Actions. One workflow file at `.github/workflows/ci.yml`.

| Job | Runs on | Triggers | Asserts |
|---|---|---|---|
| `lint-python` | ubuntu-latest | every push/PR | `ruff check`, `mypy --strict` on `python/grover_tax/` and `tests/` |
| `test-python` | ubuntu-latest, macos-latest | every push/PR | `pytest` Layers 1–2; coverage gate (`RFC-0003`) |
| `gen-fixtures-check` | ubuntu-latest | every PR | `uv run gen-fixtures --check` exits 0 |
| `schema-validate` | ubuntu-latest | every PR | `python -m grover_tax.validate_schemas` over `fixtures/v0.1.json`, `versions.lock`, sample `results/*.json` |
| `cairo-test` | ubuntu-latest | every PR | Cairo unit tests (`RFC-0004` C-T1..C-T8) |
| `rust-test` | ubuntu-latest, macos-latest | every PR | `cargo test --release` for `stwo-side/`; wrapper exit-code matrix |
| `sp1-patch-budget` | ubuntu-latest | every PR touching `sp1-side-patches/` | `git diff --stat` budget check (`RFC-0006`) |
| `apply-sp1-patch` | ubuntu-latest | every PR | `scripts/apply_sp1_patch.sh` against pinned `sp1-side/` |
| `wrapper-symmetry` | ubuntu-latest | every PR | `tests/integration/test_wrapper_symmetry.py` (`RFC-0007.I-1`) |
| `results-md-lint` | ubuntu-latest | every PR touching `analyze.py` or template | `check_results_md.py` against a fixture-driven RESULTS.md |
| `license-check` | ubuntu-latest | every PR | `scripts/check_licenses.sh` |
| `integration` | ubuntu-latest | every PR | small-fixture E2E (Layer 3 + abbreviated Layer 4) |

The `headline` numbers are *not* produced in CI. They are produced on the reference rig by the maintainer.

### Branch protection

- `main` is protected.
- All CI jobs above are required.
- One approving review required before merge.
- Force-push to `main` disabled.
- Direct commit to `main` disabled (PR-only).

These rules are configured at the GitHub repo-settings level. They are recorded in this RFC because they are part of the contract; if they were silently disabled, the methodology guarantees would weaken.

### CODEOWNERS

`.github/CODEOWNERS`:

```
*                              @AbdelStark
WORKLOAD.md                    @AbdelStark
fixtures/                      @AbdelStark
docs/spec/                     @AbdelStark
docs/rfcs/                     @AbdelStark
versions.lock                  @AbdelStark
sp1-side-patches/              @AbdelStark
analyze.py                     @AbdelStark
docs/spec/templates/           @AbdelStark
.github/workflows/             @AbdelStark
```

For `v0.1`, the maintainer set is `@AbdelStark`. Adding maintainers is a project-level decision recorded in this RFC.

### Contributor workflow

`CONTRIBUTING.md` documents:

- How to set up the dev environment (`uv sync`, `rustup install`, `git submodule update`).
- How to run tests (`pytest`, `cargo test`).
- How to propose an RFC change (open a PR against `docs/rfcs/`).
- How to propose a measurement methodology change (only via a versioned RFC change, never silently).
- The PR checklist:
  - [ ] Touched code has tests.
  - [ ] If touching methodology, an RFC change is included.
  - [ ] If touching `fixtures/v0.1.json`, a version bump rationale is included.
  - [ ] No new vendor tool branding in spec/RFC/issue text.
  - [ ] `CHANGELOG.md` `[Unreleased]` updated.

### `SECURITY.md`

A short file at the repo root:

```markdown
# Security policy

This project is a methodology benchmark, not a production cryptographic
deployment. Soundness defects in the *methodology* (e.g., bias in metric
capture, asymmetric measurement) should be reported as public GitHub issues
with label `type:bug priority:p0`. There is no embargoed disclosure track.

Soundness defects in the underlying *provers* (SP1, Stwo, Groth16) are
out-of-scope here; report them to their respective upstream projects.
```

### `CODE_OF_CONDUCT.md`

The standard Contributor Covenant 2.1 verbatim, with contact email `<maintainer>@<domain>` (`AbdelStark`'s preferred address; recorded out-of-band).

### Repo metadata

- `README.md`: brief project description, one-paragraph methodology summary, link to `RESULTS.md`, link to `SPEC.md`, reproduction recipe.
- `pyproject.toml`: project name `grover-tax`, version (synced to release tag), entry points, dev/test extras.
- `CHANGELOG.md`: per `09-release-and-versioning.md`.
- `Cargo.toml` workspace (for `stwo-side/`).

### Upstream-bump workflow

When a maintainer wants to bump `sp1-side/` to a newer upstream SHA:

1. Create a PR titled `Bump sp1-side to <new SHA>`.
2. Update the submodule pin; update `versions.lock`.
3. Re-test the patch application; update the patch if needed (subject to the line budget of `RFC-0006`).
4. Run a full `scripts/run_all.sh` on the reference rig; commit the regenerated `results/` and `RESULTS.md`.
5. Bump the project version per `09-release-and-versioning.md` (minor if the bump affects methodology, patch if it does not).
6. Land the PR.

Same workflow applies to `stwo` bumps.

### Issue triage

Labels (see `RFC-0014.A` for full taxonomy; mirrored from the goal-file Phase 2 instructions). Triage rules:

- `priority:p0`: methodology-critical defects, blocks release. Maintainer addresses within 7 days or escalates.
- `priority:p1`: feature/bug for `v0.1` scope. Triaged within 14 days.
- `priority:p2`: nice-to-have. No SLA.

## Alternatives Considered

### A1. Apache-2.0 root license

Pros: clearer patent grant.

Cons:
- MIT is the most-permissive widely-used licence; matches the spirit of "minimum-friction reproducibility".
- Apache-2.0 with NOTICE files imposes redistribution friction.

Rejected for `v0.1`. Revisit if downstream wants stronger patent protection.

### A2. Multi-maintainer governance now

Pros: scale.

Cons: premature for a one-person project at `v0.1`. Add maintainers when contributors demonstrate sustained engagement.

Rejected.

### A3. GitLab/Codeberg instead of GitHub

Pros: avoid lock-in.

Cons: tooling integration (CI, branch protection, `gh` CLI) is mature on GitHub; switching costs are real.

Rejected for `v0.1`.

### A4. No `CODEOWNERS`

Pros: simpler.

Cons: methodology files are exactly the ones that benefit from forced review. The single-line `@AbdelStark` overhead is trivial.

Rejected.

## Drawbacks

- The maintainer set of one is a single-point-of-failure. Mitigated by: PRs being self-describing; tests being thorough; the methodology being documented. A successor maintainer can read the docs and onboard.
- Branch protection is enforced via GitHub repo settings, not code. A misconfiguration could weaken it silently. Mitigated by a periodic audit (annually; reflected in `MEMORY.md` if used).

## Migration / Rollout

First-time. Files land in one PR: `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.github/workflows/ci.yml`, `.github/CODEOWNERS`. Branch protection is configured at the GitHub repo-settings level, separately.

## Testing Strategy

- **G-T1**: `scripts/check_licenses.sh` returns 0 against the current submodule set.
- **G-T2**: `CONTRIBUTING.md` exists and references the test commands accurately.
- **G-T3**: CI workflow YAML lints (`actionlint` recommended).
- **G-T4**: `CODEOWNERS` is syntactically valid (GitHub's parser accepts).
- **G-T5**: Branch protection: covered by manual audit, not code.

## Open Questions

**OPEN-Q-14.1** — When to add a second maintainer. Trigger: a contributor lands ≥ 3 substantive PRs (methodology improvements) over ≥ 3 months. Owner: maintainer. Resolution target: ongoing.

**OPEN-Q-14.2** — Whether to require GPG-signed commits on `main`. Currently no — the friction is significant and the threat model (`06-security.md`) does not justify it. Revisit if the project sees malicious-PR attempts.

## References

- `docs/spec/06-security.md`
- `docs/spec/09-release-and-versioning.md`
- `RFC-0006` (SP1 patch budget that CI enforces)
- `RFC-0007` (wrapper symmetry that CI enforces)
- `RFC-0011` (RESULTS.md lints that CI enforces)
- PRD `PRD.md` §10
