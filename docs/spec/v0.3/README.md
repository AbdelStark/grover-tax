# grover-tax v0.3 — Spec Corpus

## Thesis

Convert the v0.2 *hope signal* (2.52× Stwo lead on a 1024-gate
microbenchmark) into a **defensible apples-to-apples benchmark on the
upstream Khattar/Google secp256k1 point-addition workload**. The audit
chain, scaling-curve methodology, and second-party reproduction protocol
exist so the result will survive review by the upstream paper's authors.

## Documents in this directory

| File | Role |
|---|---|
| `SPEC-v0.3.md` | Master specification — proof statement, workload, reference rig, audit chain, reporting, roadmap pointer. |
| `SCOPE.md` | Tier-A/B/C/D obligations; binding scope-change protocol. |
| `ROADMAP.md` | Four sequential phases (audit chain → small scale → large scale → reproduction + paper). |
| `ACCEPTANCE.md` | Per-phase exit-criteria with test-ID enumeration. |
| `BUDGET.md` | Compute / calendar / operator estimates and risk-adjusted ceilings. |
| `README.md` | This file. |

## RFC corpus added in v0.3

| RFC | Title | Resolves |
|---|---|---|
| RFC-0023 | Real secp256k1 point-addition workload | replaces v0.2's XOF-random circuit; pins upstream gate-net builder. |
| RFC-0024 | Scaling-curve methodology + audit-chain implementation | implements every Tier-A obligation (A1–A11). |
| RFC-0025 | Direct Stwo Cairo path (no bootloader) | resolves `OPEN-Q-22-1`; removes ~55k bootloader rows from Stwo. |
| RFC-0026 | FRI parameter equivalence (matched soundness) | defends `A_param` adversary; pins both stacks at matched conjectured-100-bit soundness. |
| RFC-0027 | Second-party reproduction protocol | resolves `OPEN-Q-v0.3-3`; defines independent-operator submission. |

## Reading order

1. **Cryptographic reviewer.** `SPEC-v0.3.md` → RFC-0023 → RFC-0026 →
   RFC-0024 §2 (audit chain) → RFC-0027.
2. **Implementer.** `SCOPE.md` → `ROADMAP.md` → RFC-0024 (the
   implementation bundle) → RFC-0025 (Stwo direct path).
3. **Methodology auditor.** `SCOPE.md` Tier-A → RFC-0024 audit chain →
   `ACCEPTANCE.md` → RFC-0027.
4. **Budget reviewer.** `BUDGET.md` first.
5. **Reproducer (third party).** Wait for `v0.3.0` release; then
   `RFC-0027` + the release's `BUILD.md` reproduction recipe.

## What the v0.3 corpus does

It **plans** v0.3. It does not implement anything yet — implementation
is filed as issues under `docs/roadmap/IMPLEMENTATION.md::v0.3`. The
spec corpus is binding once it lands on `main`; implementation PRs
must reference the relevant RFC + phase.

It does **not** produce numbers. Numbers come from running `make
headline TIER=T<i>` on the v0.3 reference rig (c3-highmem-22 in
europe-west1-b) after Phase 0's audit chain is green.

It does **not** retire v0.2. The v0.2 RFCs (RFC-0015 through RFC-0022)
remain authoritative for v0.2.x; v0.3 explicitly extends them via the
amend / supersede headers at the top of each new RFC.

## Status

`v0.3` — specification *draft*. Will enter `main` as accepted-draft on
first commit. Phase 0 implementation can start immediately; v0.3.0
release is gated by all four phase acceptance gates.

Current state of dependencies (v0.2 backlog that v0.3 will close):

| Obligation | Source | v0.2 status | v0.3 phase |
|---|---|---|---|
| Committed `proving-utils/Cargo.lock` | RFC-0021 §1 | gitignored; hot-patched during 2026-05-20 run | P0.1 |
| `FIXTURE_PATH` env var | RFC-0021 §4 | hot-patched via `sed` during 2026-05-20 run | P0.2 |
| Real M7 grammar | RFC-0021 §5 | wrapper-synthesised sentinel | P0.3 |
| `C16-T8`, `S17-T8` constant-cost-per-gate | RFC-0016/0017 | not implemented | P0.4, P0.5 |
| `digest_anchor` (SP1) | RFC-0017 §3.7 | not implemented | P0.6 |
| Bootloader `user_args` anchoring (Stwo) | RFC-0022 §4 | inline-verify only | P0.7 |
| `bin/apples-verify` | RFC-0022 §5 | does not exist | P0.8 |
| `versions.lock` extension | RFC-0021 §3 | partial | P0.9 |
| Soundness-floor preflight | RFC-0019 §2.4 / RFC-0026 | not implemented | P0.10 |
| Bootstrap-CI day-2 gate | RFC-0021 §11 | point-estimate gate only | P0.11 |
| Methodology lint `L1`–`L6` | RFC-0021 §2 | only `L1`-equivalent present | P0.12 |
| Cross-prover FRI equivalence | RFC-0026 | not pinned | P0.13 |

Every row is targeted at Phase 0 (`v0.3.0-rc.0`) per `ACCEPTANCE.md`.

## Naming convention

- `RFC-0023..RFC-0027` reserved for v0.3 design RFCs.
- `RFC-0028..` reserved for v0.4+.
- `headline-runs/v0.3.0/` is the canonical location for v0.3 GA
  results; rc artefacts live in `headline-runs/v0.3.0-rc.<X>/` and may
  be deleted at GA per RFC-0009 of v0.1 (versioning/yanking).
