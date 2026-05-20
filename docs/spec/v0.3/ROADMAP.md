# grover-tax v0.3 — Implementation Roadmap

Phases are sequential. Each phase has a release-candidate tag, an
acceptance gate (link to `ACCEPTANCE.md`), and a budget estimate. A
phase cannot start until the previous phase's gate passes.

## Phase 0 — Audit chain (rc.0)

**Goal.** Make the v0.2 measurement *defensible* without changing the
workload. Every Tier-A item from `SCOPE.md` must be green in CI.

**Scope.**

| Step | Issue | RFC | Estimate |
|---|---|---|---|
| P0.1 | Commit `third_party/proving-utils/Cargo.lock`; remove from `.gitignore`; gate `lockfile-completeness` in CI | A4 | 1 day |
| P0.2 | Parameterise `FIXTURE_PATH` across all wrapper scripts and `measure.sh` | A5 | 0.5 day |
| P0.3 | Implement M7 grammar in real prover stdout: SP1 `prove.rs` emits `CONSTRAINTS:` from `ExecutionReport`; Stwo extracts from `stwo-cairo`'s component-summary log | A6 | 2 days |
| P0.4 | Implement `C16-T8` (Cairo per-opcode trace-row equality) | A1 | 3 days |
| P0.5 | Implement `S17-T8` (SP1 per-arm RISC-V cycle equality) | A1 | 2 days |
| P0.6 | SP1 program: add `digest_anchor` committed public value | A2 | 1 day |
| P0.7 | Stwo bootloader: bind `user_args_list` hash to proof public input | A2 | 1 day (depends on RFC-0025 for direct-Cairo work) |
| P0.8 | Implement `bin/apples-verify` per RFC-0022 §5 | A3 | 3 days |
| P0.9 | Extend `versions.lock` schema: add `sp1.fri_params`, `stwo.circle_fri_params`, `sp1.toolchain_sha256`, `sp1.program_elf_sha256`, `host.os_build`, `groth16.ceremony_url`; regenerate `lock_versions.sh` and `versions-lock-v1.schema.json` | A8 | 1.5 days |
| P0.10 | `preflight.sh` soundness-floor assertion | A7 | 1 day |
| P0.11 | Bootstrap-CI day-1/day-2 stability gate in `analyze.py` | A9 | 1.5 days |
| P0.12 | Methodology lint extensions `L1`–`L6` in `check_results_md.py` | A10 | 1 day |
| P0.13 | Cross-prover FRI parameter equivalence pin in `versions.lock` + `preflight.sh` check | A11 | 1 day |

**Estimated calendar time:** 3 weeks (allowing for review cycles).
**Compute:** zero (CI runs are within free-tier minutes).
**Tag:** `v0.3.0-rc.0` when Phase 0 acceptance gate passes.

## Phase 1 — Real point-add workload at small scale (rc.1)

**Goal.** Replace the v0.2 XOF-random circuit with the upstream
point-add gate net; capture T0/T1/T2 series on the v0.3 reference rig.

**Scope.**

| Step | Issue | RFC | Estimate |
|---|---|---|---|
| P1.1 | Import upstream gate-net builder; pin its commit in `WORKLOAD.md`; produce `fixtures/v0.3-pointadd-T0.json` (1024 gates) | B1 | 2 days |
| P1.2 | Cross-validate the imported builder against upstream sim semantics; F-INV-4 holds for T0 | B1 | 1 day |
| P1.3 | Run T0 measurement on c3-highmem-22; compare to v0.2's 2.52× ratio (cross-check) | B2 | 1 day (incl. rig spin-up) |
| P1.4 | Produce T1/T2 fixtures (16K / 256K gates) | B1, B2 | 1 day |
| P1.5 | Run T1/T2 measurement series; analyze + plot | B2, B3 | 2 days compute (mostly wall-clock) |
| P1.6 | Fit scaling-curve linear model `t = a + c·n_g + d·log(n_g)·n_g`; emit RESULTS.md per-tier table | B5 | 1 day |
| P1.7 | Validate ops-counted-footprint section per RFC-0018 §4 | B5 | 0.5 day |

**Estimated calendar time:** 1.5 weeks.
**Compute:**
- c3-highmem-22 at $1.20/hr.
- T0 (1k gates): ~5 min Stwo + ~12.5 min SP1 + verify = ~25 min per series.
  × 2 series (day-1/day-2) × 11 measured runs = ~10 hours.
- T1 (16k gates): scaled linearly = ~80 min/proof, ~30 hours total.
- T2 (256k gates): ~22 hours/proof × 5 runs × 2 sides = ~440 hours? No — re-think.

  Actually, with linear scaling, 256k gates / 1024 gates × 5 min Stwo
  = 1280 min ≈ 21 hours per Stwo proof. Even with 5 runs (T2's reduced
  sample), that's 105 hours of Stwo M1 alone. T2 budget is unrealistic
  unless we scale `n_g` lower OR use a bigger rig.

  **Re-plan:** Phase 1 ships T0 + T1 only. T2 deferred to Phase 2.

- Total Phase 1 compute: ~40 hours = $48.
**Tag:** `v0.3.0-rc.1` when T0+T1 are green per acceptance gate.

## Phase 2 — Mid-to-large scale (rc.2)

**Goal.** Push to T2 (262k gates) and attempt T3 (1M gates).

**Scope.**

| Step | Issue | RFC | Estimate |
|---|---|---|---|
| P2.1 | T2 fixture + measurement on `c3-highmem-22` | B1, B2 | 5 days compute |
| P2.2 | T3 fixture + memory-pressure probe (does SP1 fit on 176 GiB?) | B1 | 2 days |
| P2.3 | T3 measurement IF P2.2 fits; otherwise document the OOM bound | B2 | 5 days compute |
| P2.4 | Scaling-curve refit with T0+T1+T2(+T3) | B5 | 1 day |
| P2.5 | Empirical-vs-linear-model gap quantified; report deviation | B5 | 1 day |

**Estimated calendar time:** 2 weeks.
**Compute:**
- T2: ~21 hours/proof × 5 runs × 2 sides = ~210 hours. Pricey.
  Alternative: T2 with `n_runs=3` instead of 5 = 126 hours. = $150.
- T3: ~85 hours/proof × 3 runs × 2 sides = 510 hours = $610. Likely
  infeasible at on-demand pricing. Consider Spot for T3.

**Spot caveat.** GCE Spot for c3-highmem-22 is ~70% cheaper. v0.3 spec
permits Spot for Phase 2 PROVIDED the preemption rate during the
measurement window is logged and < 5% per RFC-0024 §11. A preempted run
is *not* a discard; the entire run series is invalidated.

**Tag:** `v0.3.0-rc.2` when T2 is clean AND T3 is either clean or
formally documented as out-of-budget.

## Phase 3 — Day-2 stability + second-party reproduction (rc.3)

**Goal.** Validate temporal and operator independence.

**Scope.**

| Step | Issue | RFC | Estimate |
|---|---|---|---|
| P3.1 | Day-2 series in reverse-scale order on the same rig (24h later) | C6, RFC-0010 | 1 day per scale already-budgeted |
| P3.2 | Bootstrap-CI stability gate validated against day-1/day-2 deltas | A9 | 0.5 day |
| P3.3 | Recruit second-party operator (Tier-C C1); provide them with `versions.lock` + reproduction recipe | C1, RFC-0027 §2 | 1 week (mostly waiting) |
| P3.4 | Second-party operator submits PR with their independent `RESULTS-replicator.md` | C1 | 2 weeks (operator-bound) |
| P3.5 | Compare both `RESULTS.md` files; if within ±5%, Tier-3 reproducibility validated | C1, RFC-0013 | 1 day |

**Estimated calendar time:** 3 weeks (most of it elapsed time for the
second-party operator).
**Compute:** Day-2 doubles the Phase 1+2 cost.
**Tag:** `v0.3.0-rc.3` when day-2 + second-party reproduction agree
within Tier-3 envelope.

## Phase 4 — Cross-architecture + methodology paper + release (v0.3.0)

**Goal.** macOS companion result; write-up for external review; tag.

**Scope.**

| Step | Issue | RFC | Estimate |
|---|---|---|---|
| P4.1 | macOS reference rig: T0/T1/T2 series on M4 Max | C7 | 5 days operator time |
| P4.2 | `RESULTS-macos.md` companion published | C7 | 1 day |
| P4.3 | Cross-architecture commentary: does ρ differ ≥ 10% between Linux and macOS rigs? | C7 | 0.5 day |
| P4.4 | Methodology paper draft (4-6 pages) | C8 | 2 weeks |
| P4.5 | Share draft with Khattar/Google team; collect feedback | C8 | 2 weeks elapsed |
| P4.6 | Incorporate feedback; final `RESULTS.md` + RESULTS-macos.md + methodology paper | C8 | 1 week |
| P4.7 | Tag `v0.3.0`; CHANGELOG; release notes | RFC-0014, RFC-0009 of v0.1 (versioning) | 0.5 day |

**Estimated calendar time:** 6 weeks (paper + external review dominate).
**Compute:** macOS rig is operator-supplied, $0.
**Tag:** `v0.3.0` GA when paper is shared and `RESULTS.md` reflects the
final accepted methodology.

## Total estimate

| Resource | Estimate |
|---|---|
| Calendar time | ~13–15 weeks |
| Compute ($, on-demand) | ~$300–400 |
| Compute ($, Spot for T3 only) | ~$200–250 |
| Operator time | ~8–10 weeks of active work |
| Second-party operator | volunteer time, ~2 weeks active |
| Methodology paper review cycle | ~2–4 weeks (Google team-dependent) |

## Critical-path dependencies

```
P0.4 (C16-T8) ──┐
                ├─→ P0.6 + P0.7 (anchoring) ──→ P0.8 (apples-verify) ──→ Phase 1 starts
P0.5 (S17-T8) ──┘
P0.13 (FRI equivalence) ──→ P0.10 (preflight) ──→ Phase 1 starts

Phase 1 (T0/T1) ──→ Phase 2 (T2/T3)
Phase 1 ──→ Phase 3 (day-2 + second-party)
Phase 2 + Phase 3 ──→ Phase 4 (paper + release)
```

Phase 0 has the longest critical path (~3 weeks). Phase 2 has the
highest compute spend. Phase 3 has the highest elapsed-time risk
(operator availability). Phase 4 has the highest external-review risk
(Google team's feedback cycle).

## Risks + mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| T3 / T4 SP1 OOM on c3-highmem-22 | high | Document the memory bound; ship v0.3 with T0–T2 headline; defer T3+ to v0.4 / recursive composition |
| Stwo Cairo program panics on real point-add gate net at T1+ scale | medium | Pre-flight on smaller fixtures during Phase 0; gate the upstream builder import on F-INV-4 cross-check |
| Bootstrap-CI day-2 stability gate fails | medium | Re-investigate thermal protocol; expand cool-down; re-run; if persistent, escalate to per-day rig reset |
| Second-party operator can't reproduce within ±5% | medium-low | Check rig-class match; check FRI param drift; expand Tier-3 window to ±10% in worst case |
| Khattar/Google team takes ≥ 4 weeks to review | medium | Pre-share the methodology paper draft at Phase 3 start, not Phase 4 |
| FRI parameter equivalence is hard to achieve (RFC-0026) | medium | RFC-0026 §4 defines acceptable alternative pinnings if exact match isn't feasible |
| `proving-utils` upstream-bumps a transitive crate that breaks the build | low | Committed lockfile + `--locked` build (A4) defends |
