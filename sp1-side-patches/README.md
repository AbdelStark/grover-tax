# SP1 patches

This directory holds the patch series applied to `sp1-side/`
(`tanujkhattar/zkp_ecc`) on every reproducer run. Per RFC-0006
§"Patch surface" the series is bounded:

* **≤ 1 patch file per RFC-0006 surface** (today: the
  `prover/prove.rs` argv + `prover/Cargo.toml` dep additions).
* **≤ 50 net lines** in any example-crate file.
* **≤ 5 lines** in `Cargo.toml`.
* **No touch** of SP1 prover internals, constraint shape, or
  commitment-hash logic.

## Files

| Patch | Purpose |
|---|---|
| `0001-read-fixtures-from-json.patch` | Replace upstream's `clap`-parsed CLI + `Shake256`-derived test cases with the RFC-0007 wrapper-contract argv shape + `serde_json` deserialise of `fixtures/v0.1.json`. Route the emitted proof bytes to `argv[2]`. |

## How patches are applied

`scripts/apply_sp1_patch.sh` runs `git -C sp1-side am --3way <patch>` over
every patch in this directory in sorted order. CI (`#27`) re-applies
against the pinned `WORKLOAD.md.upstream_commit` on every PR and asserts
the net line budget hasn't drifted.

The patches are **not** committed against the submodule's history — they
live here, the apply script applies them to a clean checkout, and the
build is performed in-tree under `sp1-side/`. Re-pinning the submodule
SHA is the trigger to regenerate the patch series.
