# grover-tax v0.3 — Scope

**Thesis.** Convert the v0.2 *hope signal* (2.52× Stwo lead on a 1024-gate
microbenchmark, single c3-standard-8 day-1) into a *defensible
apples-to-apples benchmark* against the upstream Khattar/Google secp256k1
point-addition Grover-oracle workload, at a scale and audit level a
methodology reviewer cannot tear apart.

This file enumerates what v0.3 will and will not do. Each tier is binding;
moving a Tier-C item up to Tier-A requires a scope-change PR before
implementation can claim v0.3 progress.

## Tier A — Defensibility blockers (must-have)

The v0.2 measurement is not defensible without these. v0.3 ships none of
its numbers as headline until every Tier-A item is green in CI.

| ID | Obligation | Source |
|---|---|---|
| A1 | Implement `C16-T8` (Stwo) and `S17-T8` (SP1) constant-cost-per-gate enforcement | RFC-0016 §5, RFC-0017 §3.1, RFC-0024 |
| A2 | Implement public-input anchoring: SP1 commits `digest_anchor`, Stwo binds the bootloader's `user_args_list` to a proof-side hash | RFC-0019 §6.2, RFC-0024 |
| A3 | Implement `bin/apples-verify` with the five-step cross-check protocol | RFC-0022 §5, RFC-0024 |
| A4 | Commit `third_party/proving-utils/Cargo.lock`; build everything with `cargo --locked` in CI and on the measurement rig | RFC-0021 §1, RFC-0024 |
| A5 | Parameterise the fixture path: `FIXTURE_PATH` env var across `scripts/measure.sh`, `bin/run_<prover>.sh`, `bin/verify_<prover>.sh` | RFC-0021 §4, RFC-0024 |
| A6 | Real M7 grammar (parse `CONSTRAINTS:` / `TRACE_ROWS:` from each prover's actual stdout, not wrapper-synthesised) | RFC-0021 §5, RFC-0024 |
| A7 | Soundness-floor assertion in `preflight.sh` (read FRI params from `versions.lock`, refuse to enter measurement window if < 100-bit conjectured) | RFC-0019 §2.4, RFC-0021 §17, RFC-0026 |
| A8 | `versions.lock` populated with `sp1.fri_params`, `stwo.circle_fri_params`, `sp1.toolchain_sha256`, `sp1.program_elf_sha256`, `host.os_build`, `groth16.ceremony_url` | RFC-0021 §3, RFC-0026 |
| A9 | Day-1 / Day-2 stability gate fires on bootstrap-CI exclusion of 5% threshold (not point estimate) | RFC-0021 §11, RFC-0024 |
| A10 | Methodology lint extensions `L1`–`L6` enforced in CI: ops-counted-footprint section, commitment-cost row, soundness-floor declaration, bootloader Pedersen disclosure, apples-verify confirmation, sample-size bounds | RFC-0021 §2, RFC-0024 |
| A11 | Cross-prover FRI parameter equivalence: SP1 and Stwo proof generation at FRI parameter sets that give the same conjectured soundness floor; ratio reported is at *matched soundness* | RFC-0026 |

## Tier B — Workload (must-have)

The v0.2 1024-random-gate microbenchmark is the wrong workload to ship as
the v0.3 headline. v0.3's headline is on a workload that is
**structurally faithful to the upstream paper at a scale that fits a
single-rig budget**.

| ID | Obligation | Source |
|---|---|---|
| B1 | Real point-add gate net: import the upstream `tanujkhattar/zkp_ecc::lib::sim` gate list for one secp256k1 point-addition; emit it as `fixtures/v0.3-pointadd-<scale>.json` for multiple scale points (see B2) | RFC-0023 §2 |
| B2 | Scaling-curve methodology: measure at `n_g ∈ {1024, 16384, 262144, 1048576, 16777216}` with shrinking sample counts (`{n_runs: 10, 10, 5, 3, 1}`); fit a linear model `t = a + c·n_g + d·log(n_g)·n_g` for each prover; report the model fit + 95% CI alongside the per-point measurements | RFC-0024 |
| B3 | Operations-counted footprint section in `RESULTS.md` with per-prover row counts derived from M7, per RFC-0018 §4 | RFC-0021 §2, RFC-0024 |
| B4 | Replace the macOS reference rig: v0.3 reference rig is `c3-highmem-22` (88 GiB, 11 physical cores × SMT-off); v0.2's Apple-Silicon reference is *retained* for cross-architecture validation but is no longer the headline rig | RFC-0024 §4 |
| B5 | The headline reports both the wall-clock ratio `ρ` AND the constraint-counted ratio `ρ_constraints` (RFC-0018 §2.4), so a reader can separate per-row efficiency from workload cost | RFC-0018 §2.4, RFC-0024 |
| B6 | Direct Stwo Cairo path (no bootloader) is the v0.3 default Stwo prover. The bootloader-mediated path remains for compatibility but is not the headline | RFC-0025 |

## Tier C — Hardening + breadth (should-have, gated)

Each Tier C item is a soft-blocker: missing it weakens v0.3's external
credibility but does not prevent publication. If a Tier C item is missing
at v0.3 release time, `RESULTS.md` MUST flag it explicitly under
"Known limitations of this run."

| ID | Obligation | Source |
|---|---|---|
| C1 | Second-party reproduction: at least one independent operator on a matching reference rig reproduces the headline ratio within ±5% (Tier-3 reproducibility, RFC-0013) | RFC-0027 |
| C2 | SP1 toolchain SHA-256 + program-ELF SHA-256 pinned and asserted at preflight | RFC-0021 §3, RFC-0026 |
| C3 | SOURCE_DATE_EPOCH set for all measurement builds; byte-stable Rust binaries asserted in CI where the toolchain supports it | RFC-0021 §12 |
| C4 | Schema additions: `iostat-v1.schema.json` shipped, `discards-v1.schema.json` extended with `affinity_miss`, `soundness_floor_breach`, `public_input_mismatch`, `ops_footprint_deviation` | RFC-0021 §§8, 10 |
| C5 | CODEOWNERS hardening on `third_party/sp1/program/`, `stwo-side/cairo/src/`, `docs/spec/v0.3/`, `docs/rfcs/`, `bin/`, `scripts/measure*.sh` — requires a second reviewer when v0.3 ships | RFC-0021 §18 |
| C6 | Day-2 reversed-order series (Stwo first on day 2) executed and reported, not just acknowledged | RFC-0010 §"Day-2" |
| C7 | Linux + macOS cross-architecture run: v0.3 publishes the c3-highmem-22 headline and a `RESULTS-macos.md` companion on the M-Max reference rig with identical fixtures | RFC-0024 §4 |
| C8 | Methodology paper draft: a 4–6 page write-up of v0.3 methodology + result, sharable with the Khattar/Google team for review *before* publication | RFC-0024 §10 |

## Tier D — Research / out of scope for v0.3

Each Tier D item is a known limitation acknowledged in `RESULTS.md` and
tracked as a v0.4+ OPEN-Q.

| ID | Item | Why deferred |
|---|---|---|
| D1 | True ZK: hide `circuit_bytes` as witness, commit only `H(C)` as public input | Requires SP1 stdin redesign + Stwo Cairo executable signature change; significant engineering, not on the apples-to-apples critical path |
| D2 | Provably-sound FRI parameters (not conjectured) | Open research; tracking BBHR/BCIKS lower bounds |
| D3 | SLSA-3 build provenance + Sigstore artefact signing | Independent supply-chain hardening initiative |
| D4 | Cross-prover *trace-row equivalence* (same `c_X` constant on both sides) | Requires arithmetisation co-design; research project |
| D5 | Multi-rig statistical envelope (≥ 3 independent reproductions on ≥ 2 distinct CPU SKUs) | Volunteer recruitment + coordination effort |
| D6 | Recursive proof composition for workloads exceeding single-machine memory | Algorithmic; possibly required for `n_g > 2²⁰` even on c3-highmem-22 |

## Scope-change protocol

A Tier-A or Tier-B item cannot be removed without a SCOPE-CHANGE PR that
documents:
1. The original reason it was Tier-A/B.
2. The new evidence justifying removal.
3. The replacement obligation (or explicit acceptance of the regression).

CODEOWNERS approval (per RFC-0014 amended by RFC-0021 §18) is required
on any SCOPE-CHANGE PR.

Tier-C items can move down to Tier-D with a single-line CHANGELOG entry
and a re-issued `RESULTS.md` (if v0.3 has already shipped).
