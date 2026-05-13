# Release and versioning

## Versioning scheme

`grover-tax` uses semantic versioning over the *contract surface* defined in `02-public-api.md`, not over the codebase.

- **MAJOR (`vX.0.0`)** — breaks any contract in C1–C6 of `02-public-api.md`. Old `RESULTS.md` reproductions are no longer numerically comparable.
- **MINOR (`v0.X.0`)** — strictly additive contract changes (new metric, new fixture field, new plot). Prior reproductions remain valid; new fields default to absent for old artifacts.
- **PATCH (`v0.X.Y`)** — bug fixes and documentation changes that do not alter measured numbers. Re-running `run_all.sh` after a patch produces numerically identical results (modulo timing noise).

The repo carries one in-tree version in `pyproject.toml` (`project.version`). The shipped fixture version is encoded in the fixture filename: `fixtures/v0.1.json` is the `v0.1` fixture. They may diverge during a patch series: `pyproject.toml: v0.1.2` with `fixtures/v0.1.json` unchanged is normal.

## Release artifacts

A release is defined by:

1. A git tag of the form `v<major>.<minor>.<patch>` on the default branch.
2. `RESULTS.md` populated from a fresh `run_all.sh` on the reference rig at that commit.
3. `versions.lock` updated and committed at that commit.
4. `CHANGELOG.md` entry under the new version heading.
5. The `results/` tree at that commit captured under `results/v<major>.<minor>.<patch>/` (the per-version archive).

A release without all five is an incomplete release and must be re-cut.

No binary distribution. The project is source-distributed only. Consumers clone and run.

## Compatibility commitments

For the duration of `v0.1.x`:

- `fixtures/v0.1.json` schema is frozen (per `03-data-model.md` invariants F-INV-1..9).
- Wrapper signatures `bin/run_<prover>.sh` and `bin/verify_<prover>.sh` are frozen.
- `RESULTS.md` table column headers are frozen.
- `versions.lock` schema is frozen.
- The metric set M1–M10 is frozen.

A patch release may:

- Fix a bug in `analyze.py` that miscomputed a derived statistic. The fix is land + re-publish; the prior `RESULTS.md` is moved to `results/archive/v0.1.<n-1>/`.
- Add a missing schema validation that should have been present.
- Correct documentation typos and broken links.

A patch release may **not**:

- Change `SEED`, `WORKLOAD.md`, the canonical serialiser, the metric set, or wrapper signatures. Any of these requires at least a minor bump.

## Deprecation policy

When `v0.2` is planned:

1. The patch release immediately preceding `v0.2.0` (e.g., `v0.1.N`) lands a `## Deprecations` section in `CHANGELOG.md` and a `Deprecated` note at the head of any spec doc whose contracts will change.
2. `fixtures/v0.1.json` is preserved in the repo through the entire `v0.2.x` series. Reproductions of the `v0.1` headline remain runnable from `git checkout v0.1.N`.
3. `RESULTS.md` is replaced by the `v0.2`-generated version. The `v0.1` `RESULTS.md` is moved to `RESULTS-v0.1.md` and linked from the new `RESULTS.md` header.

Deprecated functionality is removed only at the *next* major bump after deprecation.

## Backwards compatibility

For `v0.1`, there is nothing to be backwards compatible *with*. The first release defines the baseline.

For future minor and patch bumps, backwards compatibility means: anyone who can run `git checkout v0.1.0 && ./scripts/run_all.sh` today can still do so after `v0.1.x` is shipped, modulo external toolchain availability (rust nightly removal, etc.). This obligation does not extend across major bumps.

## Changelog discipline

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions:

```markdown
## [Unreleased]
### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [0.1.0] - 2026-MM-DD
### Added
- Initial release.
- Specification corpus and RFC set.
- ...
```

Every PR that lands updates `## [Unreleased]`. At release time, the unreleased entries become the new version's section, and a new empty `## [Unreleased]` is added.

A release PR is a separate PR whose only role is to:

1. Move `[Unreleased]` content into the new version heading.
2. Bump `pyproject.toml: project.version`.
3. Run `scripts/lock_versions.sh` and commit the result.
4. Land the tag (after merge).

## Release cadence

`v0.1` is the first release. No fixed cadence is committed for subsequent minor releases. Patch releases happen as bugs land.

## Yanking

If a release is found to contain a methodology defect that biases the headline numbers:

1. The release is *not deleted* from git or GitHub (yanking destroys the audit trail).
2. The `CHANGELOG.md` entry gains a `### Yanked` subsection at the top with the reason.
3. The corresponding `results/v<x>.<y>.<z>/RESULTS.md` is moved to `results/archive/yanked-v<x>.<y>.<z>/` with a `WHY.md`.
4. A patch release is cut with the fix.

Yanking is a public statement of methodology error. It is preferable to silent re-publication, which destroys reader trust.

## Versioning of supporting documents

| Document | Versions with | Bumps on |
|---|---|---|
| `SPEC.md` and `docs/spec/*.md` | the project version | any change |
| `docs/rfcs/*.md` | their own `Status:` line | RFC-internal updates only |
| `PRD.md` | frozen as historical record | never (after v0.1 ships) |
| `CHANGELOG.md` | the project version | every release |
| `README.md` | the project version | every release that changes user-facing flow |

`PRD.md` is explicitly historical: once `v0.1` ships, the PRD does not get updated to reflect future versions. New product context lands in a new `PRDvX.md` if needed.

## RFC lifecycle

RFCs in `docs/rfcs/` follow the standard `Draft → Accepted → (Superseded by RFC-MMMM)` lifecycle. For `v0.1`, every RFC ships in `Accepted` status. Future RFCs may be drafted under `Status: Draft` and merged only at `Accepted`.

A `Superseded by` relationship preserves the old RFC's content and adds a header note pointing forward. Old RFCs are not deleted.

## What a future `v0.2` might look like

This is forward-looking; nothing here is committed. It exists to give context for *why* `v0.1` is bounded the way it is.

Plausible `v0.2` additions:

- A second proof statement (e.g., a fixed-size SHA-256 preimage). Triggers a minor bump (additive: new fixture file, new metric series in `RESULTS.md`).
- Multi-threaded prover comparison (`RAYON_NUM_THREADS=N` variants). Triggers a minor bump (new metric dimension).
- A Linux-headline-rig variant alongside the macOS reference rig. Triggers a minor bump (new rig profile).

Implausible additions that would not happen as `v0.2`:

- A different proof system (Plonky3, etc.) — separate project.
- GPU prover paths — different benchmark.
- A web UI for results — out of scope.

## Archival

When a release is superseded:

- `results/v<x>.<y>.<z>/` is preserved.
- `RESULTS.md` for the prior version is preserved at `RESULTS-v<x>.<y>.<z>.md`.
- `fixtures/v<x>.<y>.json` is preserved.

Nothing is deleted. The repo history is the audit trail.
