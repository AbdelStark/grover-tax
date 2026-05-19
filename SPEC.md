# SPEC — `grover-tax` v0.2

This is the single-page index for the canonical specification of `grover-tax`, the single-laptop, single-core, no-GPU benchmark of Stwo vs SP1 on bit-level gate-circuit execution against a fixed reversible classical circuit.

**v0.2 status:** authoritative spec is `docs/spec/v0.2/SPEC-v0.2.md` (master) plus RFC-0015..RFC-0022 (new). The v0.1 corpus (RFC-0001..RFC-0014 plus `docs/spec/0X-*.md`) remains load-bearing for methodology RFCs (workload pinning, commitment divergence, wrapper contract, measurement protocol, single-core, hygiene, reporting, versions lock, reproducibility, governance). The v0.2 RFCs *supersede* RFC-0003, RFC-0004, RFC-0006 for the proof-statement and prover-architecture aspects, and *amend* most others via RFC-0021.

The PRD (`PRD.md`) is the historical statement of intent and is now superseded for `§2 Proof statement` by RFC-0015. The specification *below* is the implementation contract. Where they disagree, the spec wins; where the spec is silent, the PRD is informative.

## Executive summary

`grover-tax` produces one number — `t_SP1_Groth16 / t_Stwo` — on a fixed proof statement, on a fixed hardware reference, under fixed environmental controls, with a fixed metric set. Around that one number it produces a full reproducibility envelope: the fixture both provers consume, the toolchain matrix used to build them, the discard rules that excluded noise, the disclosures that name every divergence from apples-to-apples.

A reproducer with the reference rig can recompute the number from a clean clone in under 30 minutes.

## Corpus layout

```
SPEC.md                                  ← this file
PRD.md                                   ← historical statement of intent
docs/
├── spec/
│   ├── 00-overview.md                   thesis, goals, non-goals, success criteria
│   ├── 01-architecture.md               system shape, module boundaries, data flow
│   ├── 02-public-api.md                 contracts (fixture, wrappers, entry points, outputs)
│   ├── 03-data-model.md                 schemas and invariants for every persisted artifact
│   ├── 04-error-model.md                error taxonomy, failure modes, recovery
│   ├── 05-observability.md              logging, metrics, tracing, redaction
│   ├── 06-security.md                   threat model, trust boundaries, secrets, licensing
│   ├── 07-testing-strategy.md           test pyramid, property + integration + methodology
│   ├── 08-performance-budget.md         latency/throughput/memory targets
│   ├── 09-release-and-versioning.md     semver, deprecation, changelog discipline
│   └── 10-glossary.md                   canonical terms
└── rfcs/
    ├── RFC-0001-workload-pinning.md             §3 workload-parameter freeze
    ├── RFC-0002-fixture-pipeline.md             §6 generator + schema
    ├── RFC-0003-reference-simulator.md          sim_reference.py
    ├── RFC-0004-cairo-circuit-design.md         M31 limbs, gate exec, in-circuit Blake2s
    ├── RFC-0005-commitment-divergence.md        SHA-256 vs Blake2s on the two sides
    ├── RFC-0006-sp1-patch-surface.md            <50-line SP1 patch boundary
    ├── RFC-0007-wrapper-contract.md             bin/run_*.sh and bin/verify_*.sh symmetry
    ├── RFC-0008-measurement-protocol.md         M1..M10, hyperfine + gnu-time
    ├── RFC-0009-single-core-no-gpu.md           enforcement + macOS gap
    ├── RFC-0010-environmental-hygiene.md        preflight, thermal, discard rules
    ├── RFC-0011-reporting.md                    RESULTS.md template + disclosures
    ├── RFC-0012-versions-lock.md                pinned-toolchain manifest
    ├── RFC-0013-reproducibility-envelope.md     tiered reproducibility
    └── RFC-0014-governance.md                   licensing, CI, contributor workflow
```

Schemas live at `docs/spec/schemas/` (JSON Schema, draft 2020-12). Templates live at `docs/spec/templates/`. They are referenced from the documents above.

## RFC index

| RFC | Subsystem | Status | Decision locked |
|---|---|---|---|
| RFC-0001 | Workload pin | Accepted | Six fields in `WORKLOAD.md` frozen against upstream commit; CI gate rejects `TBD`. |
| RFC-0002 | Fixture pipeline | Accepted (amended by RFC-0021 §16: SHAKE-256) | Deterministic Python generator + JSON Schema + `--check` mode. |
| RFC-0003 | Reference simulator | Superseded by RFC-0015 §3.4 for gate semantics | Pure Python re-implementation; v0.2-aware `_verify_fixture`. |
| RFC-0004 | Cairo circuit (v0.1) | **Superseded by RFC-0016** | `[u31; 9]` for 256-bit state; constant-cost `step()`; in-circuit Blake2s. |
| RFC-0005 | Commitment divergence | Accepted (amended by RFC-0019 §5) | SP1 = SHA-256; Stwo = Blake2s. Both bind the same bytes; cost asymmetry quantified. |
| RFC-0006 | SP1 patch (v0.1) | **Superseded by RFC-0017** (patch-budget retired) | v0.2: freshly-owned zkVM program at `third_party/sp1/program/`. |
| RFC-0007 | Wrapper contract | Accepted (amended by RFC-0021 §§5, 7) | M7 from real prover; macOS affinity-class assertion dropped. |
| RFC-0008 | Measurement | Accepted (amended by RFC-0021 §§4, 5, 6, 11) | FIXTURE_PATH; bootstrap CI for day-2; Mann-Kendall trend. |
| RFC-0009 | Single-core / no-GPU | Accepted (amended by RFC-0021 §7) | macOS QoS-class read removed; `taskpolicy` invocation logged. |
| RFC-0010 | Hygiene | Accepted (amended by RFC-0021 §11) | `preflight.sh` + bootstrap-CI stability gate. |
| RFC-0011 | Reporting | Accepted (amended by RFC-0021 §2) | Methodology lint extended with L1-L6. |
| RFC-0012 | Versions lock | Accepted (amended by RFC-0021 §3) | New fields: `os_build`, `sp1.toolchain_sha256`, `sp1.fri_params`, `stwo.circle_fri_params`, etc. |
| RFC-0013 | Reproducibility envelope | Accepted (amended by RFC-0021 §§12, 13) | `SOURCE_DATE_EPOCH` set; equivalence class formalised. |
| RFC-0014 | Governance | Accepted (amended by RFC-0021 §18) | CODEOWNERS hardening on `third_party/sp1/program/`, `stwo-side/cairo/src/`, `docs/spec/v0.2/`. |
| **RFC-0015** | **v0.2 proof statement** | **Accepted** | **Formal `Φ_v0.2`: gate-execution + commitment binding; replaces point-add language.** |
| **RFC-0016** | **Cairo gate-execution AIR** | **Accepted** | **`apples_to_apples_executable`; constant-cost-per-gate; carry-slack soundness.** |
| **RFC-0017** | **SP1 gate-execution program** | **Accepted** | **`zkp_ecc-program` + `prove.rs`; constant-cycle-per-gate; public-input anchoring.** |
| **RFC-0018** | **Operations-counted equivalence** | **Accepted** | **`rows_X = c·n_tc·n_g + k·|cb| + b + B`; per-row efficiency factor.** |
| **RFC-0019** | **Soundness, ZK, binding** | **Accepted** | **100-bit conjectured floor; ZK explicitly not claimed; commitment cost quantified.** |
| **RFC-0020** | **Extended threat model** | **Accepted** | **A_anchor and A_statement adversaries; `apples-verify` defence.** |
| **RFC-0021** | **Reproducibility hardening** | **Accepted** | **Committed lockfiles, schema fields, new error codes, methodology lint extensions.** |
| **RFC-0022** | **Bootloader integration** | **Accepted** | **`bin/apples-prove` + `bin/apples-verify`; Pedersen disclosure; bootloader `B` constant.** |

## Reading order

- **Reproducer** (clone-and-run): `README.md` → `RESULTS.md` (after running).
- **Cryptographic reviewer** (judging fairness): `docs/spec/v0.2/SPEC-v0.2.md` → RFC-0015 → RFC-0018 → RFC-0019 → RFC-0020 → RFC-0005.
- **Implementer** (writing code): `docs/spec/v0.2/SPEC-v0.2.md` → RFC-0016 (Stwo) or RFC-0017 (SP1) → RFC-0022 (bootloader) → `docs/spec/01-architecture.md`, `02-public-api.md`, `03-data-model.md`.
- **Operator** (running the measurement series): `docs/spec/v0.2/SPEC-v0.2.md` §7 → `docs/spec/05-observability.md`, `08-performance-budget.md`, `RFC-0008` (amended by RFC-0021) → `RFC-0010`.
- **Methodology auditor:** `docs/spec/v0.2/GAP-ANALYSIS.md` → RFC-0021 → RFC-0011 → `RESULTS.md` lint output.

## Open questions

The corpus carries 7 explicit `OPEN-Q-*` open questions, all marked with owner and target resolution:

- `OPEN-Q-2.1` — Whether to inline reproduction recipe in fixture file. Decided: no.
- `OPEN-Q-4.1` — Limb-count choice (9 vs 11). Decided: 9, revisit if reduction overhead is excessive.
- `OPEN-Q-6` — Supply-chain hardening (signing, full SBOM). Decided: out of scope for `v0.1`.
- `OPEN-Q-8.1` — `iostat_capture.sh` interaction with measured window. Decided: M10 informational only.
- `OPEN-Q-9.1` — Future macOS hard-core-pinning if exposed. Watch list.
- `OPEN-Q-10.1` — Whether day-2 run-order reversal is tooling-enforced. Decided: yes.
- `OPEN-Q-11.1` — CSV companion to `RESULTS.md`. Decided: no for `v0.1`.
- `OPEN-Q-12.1` — Record macOS marketing build in `versions.lock`. Decided: yes (follow-up patch).
- `OPEN-Q-13.1` — Graduate to SLSA-3 / Sigstore. Post-`v0.1`.
- `OPEN-Q-13.2` — Publish reference-rig binaries as release artifacts. Currently no.
- `OPEN-Q-14.1` — When to add second maintainer. Trigger defined.
- `OPEN-Q-14.2` — Require GPG-signed commits on `main`. Currently no.

All open questions are *informational* or have decisions; none block `v0.1` implementation.

## What this corpus does not do

- It does not implement anything. Implementation is filed as GitHub issues per `docs/roadmap/IMPLEMENTATION.md`.
- It does not produce numbers. Numbers come from running `scripts/run_all.sh` on the reference rig.
- It does not audit upstream provers. SP1 and Stwo are taken on their own terms.

## Provenance

- Source of intent: `PRD.md`, frozen as historical record.
- Source of truth for implementation: this spec corpus.
- Source of truth for numbers: `RESULTS.md`, generated by `analyze.py`.
- Source of truth for toolchain: `versions.lock`.

## Status

`v0.1` — specification frozen; implementation issues filed; reference-rig measurements pending.
