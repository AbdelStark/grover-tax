# grover-tax v0.2 — Spec Corpus

## Documents in this directory

| File | Role |
|---|---|
| `SPEC-v0.2.md` | Master technical specification for v0.2 (single point of truth for what's proven and why the comparison is fair). |
| `GAP-ANALYSIS.md` | Exhaustive catalogue of every drift, gap, and silent assumption found in the v0.1 corpus, with disposition. |
| `README.md` | This file. |

## RFC corpus added in v0.2 (in `docs/rfcs/`)

| RFC | Title | Resolves |
|---|---|---|
| RFC-0015 | v0.2 statement under proof | `Φ_v0.2` defined; PRD §2 retired. |
| RFC-0016 | Cairo gate-execution AIR (Stwo side) | replaces RFC-0004. |
| RFC-0017 | SP1 gate-execution zkVM program | replaces RFC-0006 (patch-budget retired). |
| RFC-0018 | Operations-counted equivalence | apples-to-apples soundness keystone. |
| RFC-0019 | Soundness, zero-knowledge, binding | 100-bit floor; ZK retracted at v0.2. |
| RFC-0020 | Extended threat model | `A_anchor`, `A_statement` added. |
| RFC-0021 | Reproducibility hardening | committed lockfiles, schemas, methodology lints. |
| RFC-0022 | Bootloader integration | `bin/apples-verify` + Pedersen disclosure. |

## How to read

1. Start with `SPEC-v0.2.md` (master).
2. If you are a cryptographic reviewer: RFC-0015 → RFC-0018 → RFC-0019 → RFC-0020.
3. If you are an implementer: pick the side (Stwo → RFC-0016 + RFC-0022; SP1 → RFC-0017).
4. If you are a methodology auditor: `GAP-ANALYSIS.md` → RFC-0021.
5. If you maintain CI / build infrastructure: RFC-0021 §17 (new error codes) → RFC-0021 §3 (versions.lock fields).

## What the v0.2 corpus does not do

It does not produce numbers. The first v0.2 measured run series (planned on GCE c3-standard-8, europe-west1-b) will fill the `RESULTS.md` template per RFC-0011 amended by RFC-0021 §2.

It does not implement code. Each RFC has §"Test obligations" enumerating the CI gates that block a v0.2 release; the implementation issues are filed under `docs/roadmap/IMPLEMENTATION.md::v0.2`.

It does not formally verify either prover's STARK soundness. Both stacks are taken on their respective upstream's conjectured-soundness claims (RFC-0019 §2).

## Status

`v0.2` — specification frozen. Implementation partially compliant (commit `c5fff05` ships RFC-0015/0016/0017 surface; RFC-0021 hardening is not yet in tree; RFC-0022 §5 `bin/apples-verify` is missing). A `COMPLIANCE.md` follow-up will track per-RFC compliance state.
