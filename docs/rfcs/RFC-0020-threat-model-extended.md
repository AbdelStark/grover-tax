# RFC-0020 — Extended Threat Model

| Field | Value |
|---|---|
| Status | Accepted |
| Supersedes | `06-security.md::§"Threat model"` (extended, not replaced) |
| Depends on | RFC-0015, RFC-0017, RFC-0019, RFC-0021 |

## 1. Summary

Catalogues the adversaries the v0.2 benchmark defends against, the precise advantage definition for each, and the test obligations a defence must satisfy. Extends `06-security.md`'s informal threat list with two new categories that the v0.1 corpus did not consider: `A_statement` (a prover that proves a *different* statement than claimed but whose verifier still accepts) and `A_anchor` (substitution of public inputs between proof and fixture).

## 2. Adversary model

We model adversaries as PPT (probabilistic polynomial-time in `λ`) algorithms with access to:

- The public repository (read).
- The fixture file (read).
- The pinned upstream provers' source (read).
- The reference rig (no direct read; the adversary can submit a PR that the maintainer merges).

Their goal is to bias the headline ratio `ρ` (RFC-0015) or to produce a `RESULTS.md` whose claim "both provers prove `Φ_v0.2`" is false. Each adversary has a specific lever; the table below enumerates them.

## 3. Adversary catalogue

### 3.1 `A_fixture` — fixture-substitution PR

**Description.** A PR that modifies `fixtures/v0.2.json` such that one prover's wall-clock is shortened or lengthened by a measurable margin.

**Advantage.** `|ρ_attacker − ρ_honest| / ρ_honest ≥ 5%`.

**Defences.**
1. `gen-fixtures --check` (RFC-0002) compares the on-disk fixture to a regenerated fixture from the pinned `SEED` and the workload pin. CI fails on drift.
2. `fixture-v0.1.schema.json` validation: `additionalProperties: false`, exact length patterns, `n_samples == len(test_cases)`.
3. F-INV-2 / F-INV-3 (`03-data-model.md`): byte-stable normalised JSON; SHA-256 of the canonical bytes recorded in `RESULTS.md`.

**Test obligations.**
- `T20-3.1.a`: `gen-fixtures --check` exits 4 if `fixtures/v0.2.json` is mutated.
- `T20-3.1.b`: CI matrix `gen-fixtures-check` job (`.github/workflows/ci.yml`) is required before merge.

### 3.2 `A_anchor` — public-input substitution (new at v0.2)

**Description.** A prover (possibly the prover binary itself, possibly an adversarial wrapper) generates a proof for a *different* `(cb, T)` than the fixture's, and the verifier accepts because it does not cross-check the proof's public values against the fixture.

**Concrete attack.** Adversary produces `cb' ≠ cb` with `|cb'| = |cb|` and a matching test-case set `T'`. They run an honest prover on `(cb', T')`, emitting a proof `π`. They commit `π` to the repository. The verifier-wrapper script reads the *fixture* (which has `cb`, `T`) but only invokes the upstream verifier on `π`. The upstream verifier accepts `π` (it's a valid proof for `(cb', T')`). The wall-clock recorded for `π` is for the smaller `(cb', T')` workload — biasing `ρ`.

**Advantage.** Unbounded: an attacker who controls one prover's witness can make that prover's measured wall-clock arbitrarily small.

**Defences.**
1. **Public-input anchoring** (RFC-0019 §6.2): the proof's committed public values bind `(cb, T)`. The verifier recomputes them from the fixture and rejects on mismatch.
2. **`bin/apples-verify`** (RFC-0022 §5): a single binary that performs both the upstream-verifier call AND the public-input-cross-check. The wrapper invokes `apples-verify`, not the upstream verifier directly.

**Test obligations.**
- `T20-3.2.a`: For each side, modify the prover's stdin (SP1) or input-felt array (Stwo) to use a non-fixture `T`; assert `apples-verify` exits 1.
- `T20-3.2.b`: `apples-verify` MUST be invoked by `bin/verify_sp1.sh` and `bin/verify_stwo.sh`; the wrapper-symmetry CI test (RFC-0007 §"I-1") MUST also enforce this call.

### 3.3 `A_statement` — different-but-verifying statement (new at v0.2)

**Description.** A prover proves a *weaker* statement than `Φ_v0.2` whose verifier still returns `0`. Example: the 2026-05-14 Stwo headline used a wide-Fibonacci AIR whose witness was a Fibonacci sequence, not a gate simulation. The verifier returned 0 (the Fibonacci proof was valid for the Fibonacci AIR), but no apples-to-apples assertion was actually verified.

**Concrete attack.**
- SP1 side: an attacker replaces `third_party/sp1/program/src/main.rs` with a no-op program that commits the fixture's `circuit_commitment_sha256_hex` directly to public values without running `simulate`. The proof is "valid" (it's a real SP1 proof of a no-op program), and the committed `commitment` matches the fixture.
- Stwo side: replace the gate-execution Cairo program with a constant-time program that returns `1`. The bootloader still proves "task completed without panicking," but no gate simulation occurred.

**Advantage.** Wall-clock collapses to the prover-stack's minimum overhead; `ρ` goes to a meaningless extreme.

**Defences.**
1. **Operations-counted equivalence** (RFC-0018 §2): if the constants `c_X · n_tc · n_g` in `RESULTS.md` deviate by more than 5% from the model's predictions, the methodology lint flags the run as inconsistent and the run is discarded.
2. **M7 grammar** (`CONSTRAINTS:` / `TRACE_ROWS:`) reports actual trace size; a no-op program has visibly tiny trace.
3. **`apples-verify`** re-runs `parse_gtv1`-and-`simulate` from the fixture as part of its cross-check (RFC-0022 §5.3) — a defence-in-depth measure that detects a "fast but wrong" prover offline.
4. **CODEOWNERS** + branch protection on `third_party/sp1/program/` and `stwo-side/cairo/src/` (RFC-0014, RFC-0021 §18).

**Test obligations.**
- `T20-3.3.a`: A "null prover" PR — replace `simulate` with `return *x` (identity) — MUST fail `apples-verify` for any test case where `y ≠ x`.
- `T20-3.3.b`: `RESULTS.md` ops-counted footprint section (RFC-0018 §4) MUST list `c · n_tc · n_g` not = 0; CI assertion enforces.
- `T20-3.3.c`: Methodology lint asserts `rows_measured ≥ 0.95 · rows_predicted` (with `rows_predicted` from the §2.3 estimates).

### 3.4 `A_toolchain` — toolchain substitution

**Description.** A reproducer's `rustc`, `scarb`, or `sp1up`-installed toolchain produces a prover binary with different per-row FFT cost, biasing wall-clock.

**Defences.** `versions.lock` + `preflight.sh` drift gate (RFC-0012, RFC-0021 §3).

**Test obligations.** Existing V-T1, V-T2 (RFC-0012); plus new V-T4 (RFC-0021 §3): assert `versions.lock::sp1.toolchain_sha256` equals the SHA-256 of `${HOME}/.sp1/bin/cargo-prove`.

### 3.5 `A_wrapper` — asymmetric wrapper modification

**Description.** A PR modifies `bin/run_sp1.sh` (adding overhead) without modifying `bin/run_stwo.sh` (or vice versa).

**Defences.** RFC-0007 symmetry test; CODEOWNERS on `bin/`; methodology lint.

### 3.6 `A_measurement` — measurement-script tampering

**Description.** A PR changes `scripts/measure.sh` to use a smaller `--runs 10`, skip the warmup, or otherwise relax the protocol.

**Defences.** RFC-0008 fixed parameters; methodology lint (`check-results-md`) asserts `n_runs ≥ 10` and `n_warmup ≥ 1` from `*.timing.json`.

### 3.7 `A_setup` — Groth16 ceremony substitution

**Description.** Adversary substitutes the SP1 Groth16 proving / verifying keys to one whose trapdoor is known, allowing forged proofs.

**Defences.** `versions.lock::groth16_ceremony_origin` (RFC-0021 §3 requires URL or content hash, not free-form string). `preflight.sh` MUST fetch the key file and SHA-256-match it to the recorded hash.

### 3.8 `A_supplychain` — Cargo / installer compromise

**Description.** Adversary publishes a malicious version of a transitive crate dependency that lands in either prover's build.

**Defences (v0.2, partial).**
- Committed lockfiles (`Cargo.lock`, `third_party/sp1/Cargo.lock`, `third_party/proving-utils/Cargo.lock` per RFC-0021 §1) pin every transitive crate by SHA-256.
- `cargo build --locked` is normative for all measured builds (RFC-0021 §1).
- `sp1up` toolchain SHA-256 is pinned (RFC-0021 §3).
- `uv` SHA-256 is pinned (RFC-0012).

**Defences (deferred to v0.3).** SLSA-3 provenance for the entire build chain; Sigstore signing of release artefacts (`OPEN-Q-13.1`).

### 3.9 `A_operator` — malicious reference-rig operator (acknowledged, not defended)

**Description.** The maintainer running `scripts/run_all.sh` on the reference rig manipulates measurements (e.g., introduces a sleep into one wrapper, runs another prover concurrently).

**Defences (acknowledged limitation).** v0.2 is a single-maintainer benchmark. Defence requires second-party reproduction on a different rig and operator, which is `OPEN-Q-v0.3-3`.

**Mitigation in v0.2.** The reproducer's checklist (RFC-0013) lets anyone re-run the protocol and verify the ratio independently. The Tier-3 ±5% reproducibility envelope is the operational mitigation.

## 4. Defence-completeness obligations

Every adversary in §3 has at least one defence and one test obligation. RFC-0021 §17 amends `04-error-model.md` with the new subcodes:

| Subcode | Triggered by | Adversary defended |
|---|---|---|
| `PROVER.PUBLIC_INPUT_MISMATCH` | `apples-verify` rejection | `A_anchor` |
| `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` | `preflight.sh` finds < 100-bit conjectured soundness | (out-of-band misuse) |
| `MEASUREMENT.OPS_FOOTPRINT_DEVIATION` | Methodology lint detects `rows_measured` outside ±5% of model | `A_statement` |
| `BUILD.SP1_TOOLCHAIN_DRIFT` | `versions.lock::sp1.toolchain_sha256` mismatch | `A_toolchain` |
| `BUILD.GROTH16_KEY_DRIFT` | Key SHA-256 mismatch | `A_setup` |

## 5. Out-of-scope adversaries (explicit)

- **Side-channel attackers.** Single-tenant rig, network-off, AC-power. Not adversarial.
- **Cryptographic-primitive breaks.** SHA-256, BLAKE2s, BabyBear-FRI, M31-Circle-FRI assumed sound.
- **Reference-rig hardware compromise.** Out of scope; trust in the rig's CPU/RAM is a prerequisite.
- **Cloning attack on Groth16 SRS.** The ceremony's MPC participants are out-of-scope; we rely on the ceremony's published trust assumptions.

## 6. Test obligations summary

| Test ID | Adversary defended |
|---|---|
| `T20-3.1.a`, `T20-3.1.b` | A_fixture |
| `T20-3.2.a`, `T20-3.2.b` | A_anchor |
| `T20-3.3.a`, `T20-3.3.b`, `T20-3.3.c` | A_statement |
| `T20-3.4` (V-T4) | A_toolchain |
| `RFC-0007::I-1` | A_wrapper |
| `RFC-0011::methodology-lint` | A_measurement |
| `T20-3.7` (SHA-256 of SP1 SRS) | A_setup |
| (no v0.2 test) | A_supplychain (deferred) |
| (no v0.2 test) | A_operator (deferred) |

All in-scope tests MUST be in `tests/integration/test_threat_model_v0.2.py` and MUST be gated in CI.
