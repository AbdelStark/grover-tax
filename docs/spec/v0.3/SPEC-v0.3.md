# grover-tax v0.3 — Master Technical Specification

**Status:** draft (this file enters `main` when v0.3 implementation begins).
**Supersedes:** the *workload* and *scaling* sections of `SPEC-v0.2.md` §§2, 5, 7; the *bootloader-as-headline-path* decision of RFC-0022 §2.
**Amends:** all v0.2 RFCs by implementing the open obligations (RFC-0021 hardening + RFC-0019 anchoring + RFC-0022 §5 apples-verify).
**Does not supersede:** the *methodology* envelope of RFC-0007..0011, the soundness-floor framework of RFC-0019 §2, the threat model of RFC-0020 (extended, not replaced — see RFC-0027 for second-party adversary).

## 1. Objective

Publish a single number — `ρ_v0.3` — that satisfies all five
conditions:

1. It is the wall-clock ratio of SP1 / Stwo proving the same NP statement
   on **the upstream Khattar/Google secp256k1 point-addition gate net**
   (not a downscaled random circuit).
2. It is measured at a workload size at which both stacks meet a
   conjectured 100-bit soundness floor (RFC-0019 §2; RFC-0026 enforces
   matched parameters).
3. It is captured under a *scaling-curve* methodology (RFC-0024 §3) that
   reports the per-point ratio and the linear-model extrapolation with
   95% confidence intervals.
4. It is reproducible by an independent operator on a matching rig
   within ±5% (Tier-C C1; RFC-0027).
5. The audit chain — `C16-T8`, `S17-T8`, `apples-verify`, soundness-floor
   preflight, methodology lint `L1`–`L6`, day-1/day-2 stability — is
   green in CI before the headline is published.

If any of the five fails, v0.3 publishes only the diagnostic and defers
the headline to v0.3.1.

## 2. Statement under proof

`Φ_v0.3` is the same statement as `Φ_v0.2` (RFC-0015 §3.6), with one
substitution: the GTV1-encoded `cb` is now produced by the upstream
point-addition gate-net builder, not by a XOF-derived random gate
sampler.

Concretely:

```
Φ_v0.3(cb, h, n_g, n_tc, T) :⇔
    h = H_*(cb)                          (commitment binding; SHA-256 SP1, BLAKE2s Stwo)
∧   parse_gtv1(cb) = C ≠ ⊥                (well-formed serialisation)
∧   |C| = n_g
∧   C is consistent with the pinned point-add builder at the WORKLOAD.md
    upstream_commit (RFC-0023 §2 — checked offline by gen_fixtures)
∧   ∀ i ∈ [1..n_tc]:  simulate(C, x_i) = y_i.
```

The fourth conjunct is *checkable from the fixture alone* (the builder is
deterministic; given the upstream commit and the SEED, `cb` is uniquely
determined) but is **not enforced inside the proof** at v0.3 — the prover
treats `cb` as opaque and proves only the simulation. This keeps the
v0.3 proof statement byte-equal to v0.2 in shape and lets RFC-0018's
operations-counted equivalence theorem carry forward unchanged. RFC-0023
§3 documents the deferred in-proof verification of the builder
correspondence as a v0.4 OPEN-Q.

## 3. Workload

### 3.1 Scale ladder

v0.3 measures both provers at five workload scales:

| Scale tier | `n_g` | `n_tc` | `n_g · n_tc` | Notes |
|---|---|---|---|---|
| T0 | 1 024 | 4 | 4 096 | continuity with v0.2; required for cross-check |
| T1 | 16 384 | 4 | 65 536 | small-scale stability |
| T2 | 262 144 | 4 | 1 048 576 | mid-scale regime |
| T3 | 1 048 576 | 4 | 4 194 304 | approaches single-rig memory ceiling |
| T4 | 16 777 216 | 4 | 67 108 864 | full upstream point-add scale (RFC-0023 §2) |

T4 may not fit in `c3-highmem-22` (88 GiB) on either stack; RFC-0023 §4
describes the fallback path (recursion or memory-tier upgrade). v0.3
ships a headline iff T0–T3 are clean and T4 is at least one successful
prove on either stack.

### 3.2 Sample sizes

Per scale, per prover, per day:

| Scale | `n_runs` | `n_warmup` | Verifier `n_runs` |
|---|---|---|---|
| T0 | 11 | 1 | 50 |
| T1 | 11 | 1 | 25 |
| T2 | 5 | 1 | 10 |
| T3 | 3 | 1 | 5 |
| T4 | 1 | 0 | 1 |

The shrinking sample count reflects budget reality and is captured in
the scaling-curve fitter's per-point weight (RFC-0024 §3.2). The fitter
weights each point by `1 / variance(point)`; T0/T1 dominate the fit, T4
provides an empirical anchor for the model's high-end extrapolation.

### 3.3 Headline

The v0.3 headline is **the geometric mean of `ρ` across T1, T2, T3**,
with T0 used as cross-check against v0.2 (must be within 5% of v0.2's
2.52×) and T4 used as a *truth anchor* (does the linear model predict
the empirical T4 within ±20%?). The CoV must be ≤ 5% within each series
for the point to enter the headline; otherwise it is reported as a
diagnostic only.

## 4. Reference rig

### 4.1 Primary (v0.3 headline)

- **Provider / shape:** GCP `c3-highmem-22` in `europe-west1-b`
  (22 vCPU, 11 physical cores with SMT-off, 176 GiB RAM)
- **Single-core pinning:** `taskset -c 0` (only one of the 11 physical
  cores is used)
- **Env caps:** unchanged from v0.2 (RFC-0009)
- **Rationale for the bump from c3-standard-8:** T3/T4 workloads exceed
  c3-standard-8's 31 GiB. c3-highmem-22's 176 GiB accommodates T3 on
  both stacks and T4 on Stwo (SP1 T4 may still OOM; RFC-0023 §4).
- **Hourly cost (May 2026 on-demand):** ~$1.20/hr.

### 4.2 Secondary (Tier C cross-architecture)

- macOS Apple Silicon M4 Max, 48 GiB, AC-power, `taskpolicy -c utility`.
- Used for `RESULTS-macos.md` companion at scale T0/T1/T2 (T3/T4 likely
  exceed 48 GiB).

### 4.3 Equivalence class

A reproducer is in the v0.3 reference equivalence class iff the
`versions.lock::host` matches:
- CPU SKU (`sysctl machdep.cpu.brand_string` or `/proc/cpuinfo`'s
  `model name`)
- Physical core count (visible vCPUs / 2)
- RAM in MiB
- Firmware version

A reproducer outside the class can still validate the methodology but
the headline ratio is allowed to drift by ±10% relative to the v0.3
reference numbers (per Tier 3 of RFC-0013, slightly widened from ±5%
because of the cross-machine-class scope).

## 5. Audit chain

The numbered audit obligations from `SCOPE.md` Tier-A map to test-IDs
that MUST be green in CI before `make headline` succeeds:

| Tier-A obligation | Test-ID(s) | Implementation in |
|---|---|---|
| A1 — constant-cost-per-gate (Stwo) | `C16-T8` | RFC-0016 §5, RFC-0024 §5 |
| A1 — constant-cycle-per-gate (SP1) | `S17-T8` | RFC-0017 §3.1, RFC-0024 §5 |
| A2 — public-input anchoring | `S19-T4`, `T20-3.2.a`, `T20-3.2.b` | RFC-0019 §6.2, RFC-0024 §6 |
| A3 — `bin/apples-verify` | `T22-1..5`, `T20-3.3.a` | RFC-0022 §5, RFC-0024 §7 |
| A4 — committed lockfile | `T21-1` | RFC-0021 §1, RFC-0024 §2 |
| A5 — `FIXTURE_PATH` parameter | `T21-4` | RFC-0021 §4, RFC-0024 §3 |
| A6 — real M7 grammar | `T21-5` | RFC-0021 §5, RFC-0024 §4 |
| A7 — soundness-floor preflight | `S19-T1` | RFC-0019 §2.4, RFC-0026 §2 |
| A8 — `versions.lock` schema completeness | `T21-3.a/b/c` | RFC-0021 §3, RFC-0026 §3 |
| A9 — day-1/day-2 bootstrap-CI gate | `T21-11` | RFC-0021 §11, RFC-0024 §8 |
| A10 — methodology lint `L1`–`L6` | `S18-T2`, `S19-T7` | RFC-0021 §2, RFC-0024 §9 |
| A11 — cross-prover FRI equivalence | `S26-T1`, `S26-T2` | RFC-0026 §4 |

`make headline` MUST `exit 0` only if all tests above are green. The
exact CI gate is specified in `ACCEPTANCE.md`.

## 6. Security model (deltas from v0.2)

### 6.1 Soundness floor

Unchanged from RFC-0019 §2: both stacks at ≥ 100-bit conjectured
soundness. **Newly enforced** at runtime by `preflight.sh` (RFC-0026 §2)
and pinned in `versions.lock::{sp1.fri_params, stwo.circle_fri_params}`.

### 6.2 Apples-to-apples adversary `A_param`

RFC-0020's threat model gains a new adversary: a maintainer who selects
FRI parameter sets that give different conjectured soundness on the two
sides (e.g., 100 bits SP1, 80 bits Stwo, biasing Stwo's wall-clock
favourably). Defence: RFC-0026 §2 — `preflight.sh` computes conjectured
soundness for both stacks and aborts if they differ by more than 1 bit.

### 6.3 ZK still not claimed at v0.3

OPEN-Q-v0.3-1 (reintroduce ZK) is deferred to v0.4. v0.3 remains an
honest-verifier argument-of-knowledge for a public NP statement.

## 7. Measurement protocol

RFC-0008 amended by RFC-0021 amended by RFC-0024:

1. **Fixture path is `FIXTURE_PATH`** (default `fixtures/v0.3-T<tier>.json`).
   Hard-coded paths removed from all wrapper scripts.
2. **`make headline` orchestrates the full ladder**: per RFC-0024 §3.3,
   sequentially executes T0 → T1 → T2 → T3 → T4 on both provers, with
   `RFC-0010` 5-min cool-downs between consecutive same-prover runs and
   `2×` cool-downs (10-min) between provers within a scale tier.
3. **Day-2** runs in reverse scale order (T4 → T0) AND with the prover
   sequence flipped (Stwo first per scale on day 2). RFC-0024 §8.
4. **M7 grammar from real prover stdout** (RFC-0021 §5).
5. **`apples-verify` runs after each prove** (not just at end of series)
   to catch a per-run public-input mismatch fast (RFC-0024 §6).
6. **Trend detection (Mann-Kendall) flags warming** per run series
   (RFC-0021 §6).
7. **M9 (deterministic-setup wall-clock) captured separately from M5**
   (per-verify wall-clock). The SP1 verifier's `ProverClient::setup(ELF)`
   call is a deterministic function of the ELF and is cached via the
   `SP1_VK_CACHE` env var (introduced in commit `6236340`, behind the
   verifier's `--vk-cache` indirection). v0.3 reporting separates the
   one-time M9 cost from the per-invocation M5 cost so a reader can
   assess production-realistic verify performance.

## 8. Reporting

The v0.3 `RESULTS.md` template (RFC-0024 §9 amends RFC-0011's template)
gains:

- A **per-tier headline table** (one row per scale tier, columns:
  `n_g`, SP1 median, Stwo median, ρ, `ρ_constraints`, CoV, n_runs).
- A **scaling-curve fit** with 95% CI and the extrapolation to upstream
  scale.
- An **operations-counted footprint** table (RFC-0018 §4) per scale tier.
- A **commitment-cost-asymmetry** quantitative breakdown (RFC-0019 §5).
- A **setup-vs-verify breakdown** (M9 vs M5) per RFC-0024 §2.10 — required
  because v0.2's diagnostic (`headline-runs/2026-05-20-v0.2/README.md`
  §"Setup-vs-verify breakdown") established that ~2.5% of v0.2's
  reported 190 s SP1 M5 is one-time setup; the remaining ~185 s is
  per-verify recursive-STARK work. A production deployment that
  amortises setup over many verifies sees only the ~185 s cost. Stwo's
  M9 is ~0 ms (FRI-commitment verifier has no per-program setup).
- A **methodology-paper anchor** subsection summarising the audit chain.
- A **known limitations** section listing any Tier-C item missing at
  release.

## 9. Implementation roadmap

See `ROADMAP.md`. Briefly:

- **Phase 0 (v0.3.0-rc.0):** Tier-A audit chain implemented + green in CI.
- **Phase 1 (v0.3.0-rc.1):** Tier-B workload + scaling curves run at T0/T1/T2.
- **Phase 2 (v0.3.0-rc.2):** T3 / T4 attempts on c3-highmem-22.
- **Phase 3 (v0.3.0-rc.3):** Day-2 + second-party reproduction (Tier-C).
- **Phase 4 (v0.3.0):** Tier-C polish + methodology paper + release.

## 10. Open questions for v0.4

| Tag | Question |
|---|---|
| `OPEN-Q-v0.4-1` | Reintroduce ZK by hiding `cb` as witness (D1) |
| `OPEN-Q-v0.4-2` | Provably-sound FRI parameters (D2) |
| `OPEN-Q-v0.4-3` | SLSA-3 + Sigstore (D3) |
| `OPEN-Q-v0.4-4` | Trace-row equivalence (D4) |
| `OPEN-Q-v0.4-5` | Multi-rig statistical envelope (D5) |
| `OPEN-Q-v0.4-6` | Recursive composition for `n_g > 2^24` (D6) |

## 11. Status

`v0.3` — specification frozen on date this file enters `main`.
Implementation tracked under `IMPLEMENTATION.md::v0.3`. Compliance state
per RFC in `docs/spec/v0.3/COMPLIANCE.md` (follow-up).
