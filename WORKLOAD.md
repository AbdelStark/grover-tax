---
upstream_repo: https://github.com/tanujkhattar/zkp_ecc
upstream_commit: TBD
pinned_at: TBD
pinned_by: TBD
fixture_target_version: v0.1
---

# Workload pin

These six fields are extracted from the upstream repo at the pinned commit and
frozen for `fixtures/v0.1.json`. Every cell carries a citation back to the
upstream source. Once frozen, this file does not change without a project
minor or major version bump (see `docs/spec/09-release-and-versioning.md` and
`docs/rfcs/RFC-0001-workload-pinning.md`).

The CI gate `scripts/check_workload.sh` exits `4`
(`FIXTURE.WORKLOAD_NOT_PINNED`) until every value in this table is non-`TBD`
and `upstream_commit` is a 40-character lowercase hex SHA.

| Field | Source location (upstream) | Value | Notes |
|---|---|---|---|
| `N` (number of test cases) | `lib/src/example_zkp_prove.rs` default const | TBD | exact constant name: TBD |
| Gate count of `C` for one secp256k1 point-add | `lib/src/sim.rs` initialisation output | TBD | derived by running `sim.rs` initialisation once and reading the gate count |
| `W` (bit-stripe width) | `lib/src/sim.rs` const | TBD | exact constant name: TBD |
| Modular-arithmetic gate count | derived from `lib/src/sim.rs` | TBD | subset of total gate count consumed by 256-bit modular arithmetic |
| Circuit-commitment scheme (SP1 side) | `lib/src/example_zkp_prove.rs` | TBD | expected: SHA-256 over canonical gate-list bytes |
| Entropy source for test-case generation (upstream behaviour) | `lib/src/example_zkp_prove.rs` | TBD | this repo replaces this with `SEED` per `RFC-0002`; the upstream value is recorded for parity comparison |
