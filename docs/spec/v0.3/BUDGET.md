# grover-tax v0.3 — Budget

Estimates as of May 2026 GCE pricing in `europe-west1-b`. Spot pricing
quoted at 70% of on-demand. Numbers are upper bounds (we'd preferentially
use lower-cost instances for Phase 0 CI work).

## Compute

### Per-scale wall-clock cost (single prove)

Linear extrapolation from the v0.2 measurement (1024 gates × 4 cases):
- Stwo: 298.755 s = ~5 min per 1024-gate proof
- SP1: 753.065 s = ~12.5 min per 1024-gate proof

Assuming `t = a + c · n_g · n_tc + b · log(n_g · n_tc) · n_g · n_tc`,
extrapolation breakdown (rough):

| Tier | `n_g` | Stwo per-proof (h) | SP1 per-proof (h) | Sum (h) |
|---|---|---|---|---|
| T0 | 1 024 | 0.083 | 0.21 | 0.29 |
| T1 | 16 384 | 1.3 | 3.5 | 4.8 |
| T2 | 262 144 | 21 | 56 | 77 |
| T3 | 1 048 576 | 84 | 226 | 310 |
| T4 | 16 777 216 | 1 350 | 3 600 | 4 950 |

T4 is *not* realistic on a single rig. T3 is borderline. T1/T2 are
feasible.

### Per-scale series cost (M1 + M5, both provers, both days)

| Tier | `n_runs` (per side) | Total proves (M1×2 days×2 sides) | Verifies | Hours | $ at c3-highmem-22 ($1.20/h) |
|---|---|---|---|---|---|
| T0 | 11 | 44 | 200 | ~13 | $16 |
| T1 | 11 | 44 | 100 | ~215 | $260 |
| T2 | 5 | 20 | 40 | ~1 540 | $1 850 |
| T3 | 3 | 12 | 20 | ~3 720 | $4 460 |
| T4 | 1 | 4 | 4 | ~19 800 | $23 800 |

These are *gross* upper bounds — in reality:
- T0/T1 fit easily (~$280 total).
- T2 needs to be smaller — `n_runs = 3` per side instead of 5 cuts it
  to $1 100.
- T3 at `n_runs = 1` per side per day = 8 proves × 310 h ÷ 2 (only one
  side per scale, no Day-2 at this scale) = $1 100 if we drop day-2 at
  T3.
- T4 is **out of single-rig budget** at on-demand pricing.

### Realistic v0.3 compute envelope

- **Tier-A audit chain implementation:** $0 (CI free-tier).
- **Tier-B T0/T1 day-1+day-2:** ~$280.
- **Tier-B T2 day-1 only, `n_runs=3`:** ~$550.
- **Tier-C T3 day-1 only, `n_runs=1`:** ~$1 100 OR Spot at $330.
- **Tier-C T4 single-prove sanity:** $0 if we skip; ~$5 000 if we
  attempt (very likely OOM on SP1).
- **Tier-C second-party Tier-C C1:** operator's compute, ~$280 mirrored.
- **Tier-C macOS companion:** $0 (operator-supplied).

**Total v0.3 compute estimate:** ~$1 500 on-demand; ~$700 with Spot for
T3.

## Calendar time

| Phase | Calendar | Compute hours | $ |
|---|---|---|---|
| Phase 0 (audit chain) | 3 weeks | 0 | 0 |
| Phase 1 (T0/T1) | 1.5 weeks | 220 | 280 |
| Phase 2 (T2 + best-effort T3) | 2 weeks | 1 500 | 750 spot / 1 650 on-demand |
| Phase 3 (day-2 + second-party) | 3 weeks | 250 (day-2 only) | 300 |
| Phase 4 (macOS + paper + release) | 6 weeks | 0 (operator-supplied) | 0 |
| **Total** | **~15 weeks** | **~2 000 h** | **~$1 300–2 200** |

The dominating cost is Phase 2 (T2). The dominating elapsed time is
Phase 4 (paper + Google team review cycle).

## Operator time

Estimate of active operator hours (not elapsed time):

| Phase | Active operator hours |
|---|---|
| Phase 0 | 80–120 (it's the bulk of the spec implementation) |
| Phase 1 | 30 |
| Phase 2 | 20 (mostly waiting for compute) |
| Phase 3 | 20 (operator) + ~40 (second-party operator) |
| Phase 4 | 40–60 (paper draft, review cycle) |
| **Total** | **~250 operator-hours** |

## Storage

Per scale:
- Proof binaries: 1.21 MiB SP1 + ~15 MiB Stwo per proof.
- Trace logs: ~80 KiB per Stwo proof, ~500 B per SP1 proof.
- Per-tier total: ~200 MiB per series (T0/T1) to ~5 GiB (T2+ with all
  the proverlog details).

Reference-rig disk: 200 GiB (default boot) is enough through T3. T4
storage is a separate concern (the proof for a 17M-gate circuit could
be in the hundreds-of-MiB range).

GitHub repo storage: artifacts under `headline-runs/v0.3.0/` should be
≤ 100 MiB. Anything larger goes to a release-artifact bucket per RFC-0014.

## Risk-adjusted budget

If everything goes well: **~$700 + 250 operator-hours over 15 weeks**.

If we hit:
- SP1 OOM at T3 on c3-highmem-22 → switch to `c3-highmem-44` ($2.40/hr,
  2× the cost; adds $300 to Phase 2 budget).
- Day-2 stability fails → re-investigate (~1 week + $300 in re-runs).
- Second-party operator drops out → recruit replacement, +2 weeks
  elapsed.
- Google team flags methodology gap requiring re-run → +1–2 weeks +
  $300–500.

**Risk-adjusted ceiling: ~$2 200 + 300 operator-hours over 18 weeks.**

This is conservative but defensible. v0.3 is not a small project; it's
the build-up to a publishable methodology paper. The cost reflects that.

## Compute provisioning recommendations

- **Phase 0:** local dev machine + CI free-tier.
- **Phase 1:** `c3-highmem-22` in `europe-west1-b`, on-demand, ~3 days
  rental.
- **Phase 2:** `c3-highmem-22` Spot in `europe-west1-b`, ~2 weeks
  rental. Backup on-demand quota for retry if preempted > 5%.
- **Phase 3:** same as Phase 1 + Phase 2 (day-2). Second-party operator
  provisions their own rig.
- **Phase 4:** no GCE; operator-local macOS + paper-writing.

GCP **budget alert** must be set at $1 500 (project-level) to catch
runaway Spot/on-demand costs.

## Cost-saving alternatives

1. **Skip Day-2 at T2/T3.** Saves ~$300. Trade-off: weakens RFC-0010's
   day-2 stability claim at the upper scales.
2. **Use AWS `m6i.8xlarge` (32 vCPU, 128 GiB) at $1.55/hr Spot.**
   Architecturally different from c3-highmem-22 (different CPU SKU);
   would need RFC-0024 §4 widening of the equivalence-class definition.
   Saves ~10%.
3. **Recruit the second-party operator earlier** so their compute
   doubles as redundancy for our T2/T3 runs. Net savings if it works:
   ~$500.
