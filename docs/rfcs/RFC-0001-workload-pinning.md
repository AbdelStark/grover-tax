# RFC-0001: Workload pinning protocol

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

This RFC freezes the six workload parameters (`N`, gate count of `C`, bit-stripe width `W`, modular-arithmetic gate count, SP1-side commitment scheme, entropy source for test-case generation) by extracting them verbatim from upstream `tanujkhattar/zkp_ecc` at a pinned commit and committing them to `WORKLOAD.md`. The pin happens once, on day 1; thereafter `WORKLOAD.md` is the single source of truth and may not change without invalidating the prior `results/`.

## Motivation

The PRD §3 names six fields as the contract that binds fixtures, Cairo translation, and result reporting. Until those fields are concrete numbers, no implementation work can begin: every downstream subsystem (fixture generator, Cairo program, measurement script) statically depends on them. Worse, if any of these fields drifts during implementation, the headline numbers are silently re-baselined and the comparison becomes untrustworthy.

The risk this RFC eliminates is *workload creep* — well-meaning re-derivation of one of these fields from upstream during a refactor, accidentally re-sizing the workload by 20% and re-baselining everything. The defence is a frozen, hand-maintained `WORKLOAD.md` with explicit provenance pointers.

## Goals

- Produce `WORKLOAD.md` on day 1 with all six fields filled in by source-reading the upstream repo at the pinned commit.
- Make any future change to `WORKLOAD.md` visible as a project version bump.
- Provide CI mechanism that fails when `WORKLOAD.md` contains `TBD` for any required field.

## Non-Goals

- Automating extraction. The protocol is source-read by a human, recorded once. Automated extraction would couple this repo's CI to upstream's source layout, which drifts.
- Tracking upstream changes. We pin to one commit; upstream's evolution is not our concern for `v0.1`.

## Proposed Design

### `WORKLOAD.md` schema

`WORKLOAD.md` is a Markdown file at the repo root with one frontmatter block and one table:

```markdown
---
upstream_repo: https://github.com/tanujkhattar/zkp_ecc
upstream_commit: <40-char hex SHA>
pinned_at: 2026-MM-DD
pinned_by: <github handle>
fixture_target_version: v0.1
---

# Workload pin

These six fields are extracted from the upstream repo at the pinned commit and frozen for `fixtures/v0.1.json`.

| Field | Source location (upstream) | Value | Notes |
|---|---|---|---|
| `N` (number of test cases) | `lib/src/example_zkp_prove.rs` default const | `<integer>` | exact constant name: `<name>` |
| Gate count of `C` for one secp256k1 point-add | `lib/src/sim.rs` initialisation output | `<integer>` | derived by running `sim.rs` initialisation once and reading the gate count |
| `W` (bit-stripe width) | `lib/src/sim.rs` const | `<integer>` | exact constant name: `<name>` |
| Modular-arithmetic gate count | derived from `lib/src/sim.rs` | `<integer>` | subset of total gate count consumed by 256-bit modular arithmetic |
| Circuit-commitment scheme (SP1 side) | `lib/src/example_zkp_prove.rs` | `<hash + encoding>` | expected: SHA-256 over canonical gate-list bytes |
| Entropy source for test-case generation (upstream behaviour) | `lib/src/example_zkp_prove.rs` | `<construction>` | this repo replaces this with `SEED` per `RFC-0002`; the upstream value is recorded for parity comparison |
```

### Process to fill in `WORKLOAD.md`

1. The implementer clones `tanujkhattar/zkp_ecc` at a specific commit. The commit is recorded in `upstream_commit`.
2. They open each of the named source files and copy the *literal* values (or computed result of one initialisation invocation, for derived fields).
3. They open a PR titled `Pin workload (`upstream_commit` <short SHA>)`. Reviewer asserts: every cell is non-`TBD`, every cell has a citation, the upstream commit exists and matches the SHA.
4. On merge, `WORKLOAD.md` is frozen.

### CI gate

`scripts/check_workload.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
if grep -q '\bTBD\b' WORKLOAD.md; then
  echo "FIXTURE.WORKLOAD_NOT_PINNED: WORKLOAD.md still contains TBD" >&2
  exit 4
fi
# Assert upstream_commit is a real SHA shape.
if ! grep -qE '^upstream_commit: [0-9a-f]{40}$' WORKLOAD.md; then
  echo "FIXTURE.WORKLOAD_NOT_PINNED: upstream_commit malformed" >&2
  exit 4
fi
```

Wired into CI as a required check on the `main` branch (`area:ci`).

### How `WORKLOAD.md` is consumed

- `python/grover_tax/gen_fixtures.py` reads the frontmatter and the table, validates structure, raises `FIXTURE.WORKLOAD_NOT_PINNED` if any value is `TBD`.
- `stwo-side/circuit.cairo` does *not* read `WORKLOAD.md`. Instead, the Cairo program is parameterised in source against compile-time constants. The constants in Cairo source must equal the values in `WORKLOAD.md`; this is enforced by a Rust-side test that loads both and asserts equality.
- `RESULTS.md` includes the `upstream_commit` SHA and `pinned_at` date in its reproduction-recipe section.

### Re-pinning

A re-pin is a project minor or major bump per `09-release-and-versioning.md`. The protocol:

1. Move `fixtures/v0.1.json` (and `results/v0.1.*`) to archive.
2. Update `WORKLOAD.md` (new upstream commit, new values).
3. Regenerate `fixtures/v0.2.json` (new filename) via `gen-fixtures`.
4. Re-run `run_all.sh`; new `RESULTS.md` produced.
5. Tag `v0.2.0`.

## Alternatives Considered

### A1. Auto-extract from upstream at build time

A script reads `tanujkhattar/zkp_ecc/lib/src/example_zkp_prove.rs` and `lib/src/sim.rs` at build time and emits `WORKLOAD.md` (or equivalent) in `target/`. Rejected because:

- Couples this repo's build to upstream's source-file layout; an upstream refactor silently breaks the build.
- Discourages the human source-read, which catches subtleties (constants named identically but with different semantics) that text-extraction misses.
- Makes the `WORKLOAD.md` audit trail invisible — the contract becomes a script, not a document.

### A2. Inline workload values in Python/Cairo source

Hard-code `N`, `W`, etc. directly in `python/grover_tax/gen_fixtures.py` and `stwo-side/circuit.cairo`. Rejected because:

- The two sources drift independently; nothing forces them to agree.
- A reviewer cannot tell at a glance whether `N` here matches `N` there.
- The provenance (upstream commit, source location) is buried in source comments rather than in a top-level pinned document.

### A3. JSON instead of Markdown for `WORKLOAD.md`

Use `WORKLOAD.json` for machine readability. Rejected because:

- The audience for `WORKLOAD.md` is primarily human reviewers; the table format is more readable.
- The machine consumers (`gen_fixtures.py`, the Cairo-equality test) parse a small structured subset (the frontmatter and the table) — straightforward in Python's `frontmatter` package.

## Drawbacks

- A manual source-read is error-prone. Mitigated by: PR review focus on this one file; tests that fail noisily if the values produce inconsistent fixtures.
- A re-pin is heavy. Intentional: re-pinning invalidates published numbers, so it should be heavy.

## Migration / Rollout

No migration; this is the first release. The rollout is the day-1 source-read pass.

## Testing Strategy

- **U-1**: A unit test asserts `WORKLOAD.md` parses with no `TBD` and has all six fields.
- **U-2**: A test compares Cairo compile-time constants against the parsed `WORKLOAD.md` values; mismatch fails.
- **U-3**: An integration test regenerates `fixtures/v0.1.json` from a fresh checkout and asserts the workload pin in the fixture (`workload_pin_commit`) matches `WORKLOAD.md.upstream_commit`.

## Open Questions

None. All six fields are extractable; the protocol is process, not technology.

## References

- `docs/spec/00-overview.md`
- `docs/spec/03-data-model.md` (`workload_pin_commit` field in fixture)
- `docs/spec/04-error-model.md` (`FIXTURE.WORKLOAD_NOT_PINNED`)
- PRD `PRD.md` §3
