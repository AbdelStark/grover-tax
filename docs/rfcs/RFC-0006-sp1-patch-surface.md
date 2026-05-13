# RFC-0006: SP1 patch surface and boundary

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

This RFC bounds the modifications made to `tanujkhattar/zkp_ecc` on the SP1 side. The patch is a single `.patch` file (`sp1-side-patches/0001-read-fixtures-from-json.patch`), targets under 50 net lines of diff, and replaces the example's internal SHA-2 XOF derivation of test cases with a deserialise-from-JSON path so both provers read the same fixture. Any patch growth beyond this budget is a project-level escalation.

## Motivation

The integrity of the benchmark depends on the upstream SP1 example being run *as upstream wrote it*, modulo the minimum required to consume our shared fixture. Every line added to the patch:

- adds maintenance burden when re-pinning to a new upstream SHA,
- adds attack surface for accidental apples-to-non-apples (e.g., changing the proof statement),
- makes the comparison "our SP1 fork" instead of "SP1 itself".

A hard line-budget defends against scope creep.

## Goals

- A single, small patch that reads `fixtures/v0.1.json` and emits the proof to a CLI-supplied path.
- A patch that re-applies cleanly on a re-pin without conflicts (no patches touching code we don't need to touch).
- A line budget that is enforced by CI.

## Non-Goals

- Changing SP1's prover internals. The benchmark is "SP1 + Groth16 as deployed", not "Hand-tuned SP1".
- Changing the proof statement. The proof statement on the SP1 side is whatever `tanujkhattar/zkp_ecc` shipped at the pinned commit, modulo the fixture-reading change.
- Adding telemetry or instrumentation to the SP1 example. Measurement lives in the wrappers, not in patched upstream code.

## Proposed Design

### Patch surface (in scope)

The patch may modify only:

1. **The test-case derivation entry point.** The upstream example derives test cases internally from a hard-coded SHA-2 XOF seed. The patch replaces that derivation with a `serde_json` deserialisation from a JSON file whose path is read from `argv[1]`.
2. **The proof output sink.** The upstream example writes the proof to a hard-coded path; the patch parameterises the path via `argv[2]`.
3. **The `Cargo.toml` of the example crate.** If `serde_json` is not already a dependency at the pinned commit, the patch adds it. No other dependency changes.

Everything else is forbidden: no changes to prover internals, constraint shape, verifier path, or build flags.

### Patch surface (out of scope, would require their own RFC)

- Changing the commitment hash (the SP1 side commits with SHA-256, see `RFC-0005`).
- Changing the proof system parameters (proving key, verifying key, Groth16 wrap configuration).
- Removing or altering any constraints in the example circuit.
- Adding logging beyond the M7 grammar (`CONSTRAINTS:`, `TRACE_ROWS:`). If upstream already emits the constraint count under `RUST_LOG=info`, the wrapper parses it; if not, the wrapper *post-processes* the prover's stdout to derive the count (done in `bin/run_sp1.sh`, not in the patched example).

### Line budget

- Hard limit: 50 net additions + deletions in the example crate.
- Hard limit: 5 net lines in `Cargo.toml`.
- CI enforces both. A PR that grows the patch beyond the budget fails CI; the PR author either justifies an exception (and the budget is raised in a follow-up RFC) or reduces the patch.

The line count is measured by `git diff --stat sp1-side-patches/0001-read-fixtures-from-json.patch` applied to a clean checkout.

### Patch shape

The patch is a `git format-patch -1` output, structured as:

```
From <sha> Mon Sep 17 00:00:00 2001
From: AbdelStark <noreply@github.com>
Date: <date>
Subject: [PATCH] read fixtures from JSON; emit proof path from argv

Adds serde_json dependency; replaces internal test-case derivation with
deserialise-from-JSON; parameterises proof output path.

No changes to prover or verifier paths. No changes to constraint shape.
---
 examples/zkp_prove/src/main.rs | 30 +++++++++++++++++-------------
 examples/zkp_prove/Cargo.toml  |  1 +
 2 files changed, 18 insertions(+), 13 deletions(-)
...
```

### Apply / re-apply

The patch is applied at build time by `scripts/apply_sp1_patch.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd sp1-side
git checkout -- .                                    # reset to pinned upstream
git apply ../sp1-side-patches/0001-read-fixtures-from-json.patch
```

`BUILD.SP1_PATCH_FAIL` triggers if the patch does not apply (signals an SP1 submodule drift from `versions.lock.sp1`).

### Re-pin discipline

When `versions.lock.sp1` is updated:

1. The patch is re-tested against the new SP1 SHA.
2. If it applies clean: ship.
3. If it does not apply: the patch is regenerated against the new SP1. The regeneration may *not* expand the line budget.
4. If regeneration cannot stay under budget (e.g., upstream restructured the example beyond easy retargeting), the re-pin is a project minor bump (`09-release-and-versioning.md`).

### Interaction with `bin/run_sp1.sh`

The wrapper invokes the patched binary as:

```bash
./sp1-side/target/release/example_zkp_prove "$fixtures_path" "$output_proof_path"
```

The wrapper is the *only* layer that knows about the binary's argv shape. The patch sets argv shape; the wrapper consumes it.

## Alternatives Considered

### A1. Vendor `sp1-side/` as a copy, not a submodule

Pros: full control over modifications; no patch round-tripping.

Cons:
- Vendoring 100k+ lines of SP1-example code into our repo bloats the diff for every PR.
- Discourages re-pinning (vendor copies drift).
- Hides the upstream provenance.

Rejected.

### A2. Patch via `git am` series instead of a single `.patch` file

A `git am` series with multiple commits, easier to review one logical change at a time.

Pros: cleaner history.

Cons:
- The "submodule + patches/" pattern is standard and well-understood.
- A multi-commit series invites unrelated changes ("while I was there, I also..."); a single small patch enforces minimality.

Rejected.

### A3. Configure-time JSON path, not argv

Bake the fixture path into a `const`; `sed` it at build time.

Pros: tiny diff (one constant).

Cons: makes the binary depend on build-time path, which is fragile across machines. argv is cleaner.

Rejected.

### A4. Read fixture from stdin instead of file

Pros: even smaller patch (just consume `stdin`).

Cons:
- Loses the symmetry with the Stwo side, which reads the fixture from a file path.
- Requires the wrapper to `cat` the file into the binary, complicating timing.

Rejected.

## Drawbacks

- The 50-line budget is arbitrary. The justification is "small enough that a reviewer can read the entire patch in 5 minutes". A future RFC can raise the budget if a real need arises.
- The patch couples to `argv` semantics, which means a Rust-level refactor of `main.rs` upstream may make re-pinning expensive.

## Migration / Rollout

First-time landing. The patch is authored against the day-1 SP1 SHA in `versions.lock`. It is committed to the repo at `sp1-side-patches/0001-read-fixtures-from-json.patch`. CI exercises `apply_sp1_patch.sh` on every build.

## Testing Strategy

- **P-T1**: `scripts/apply_sp1_patch.sh` runs against the pinned `sp1-side/` checkout and exits 0.
- **P-T2**: The line-count check (`git diff --stat`) reports ≤ 50 changed lines in the example crate, ≤ 5 in `Cargo.toml`.
- **P-T3**: After applying the patch, `cargo build --release` succeeds.
- **P-T4**: After build, `./bin/run_sp1.sh fixtures/test_v0.1.json /tmp/p.proof` exits 0 and produces a non-empty proof file.
- **P-T5**: `./bin/verify_sp1.sh /tmp/p.proof` exits 0.
- **P-T6**: Tampering with the proof file (flip one byte) makes `verify_sp1.sh` exit non-zero.

## Open Questions

None for `v0.1`.

## References

- `docs/spec/01-architecture.md` ("SP1 prover side" section)
- `docs/spec/04-error-model.md` (`BUILD.SP1_PATCH_FAIL`)
- `RFC-0005` (commitment scheme not changed by this patch)
- `RFC-0007` (wrapper consumes patched argv)
- PRD `PRD.md` §5.4
