# RFC-0024 — Scaling-Curve Methodology + Audit-Chain Implementation

| Field | Value |
|---|---|
| Status | Draft (v0.3) |
| Depends on | RFC-0008 (measurement protocol), RFC-0011 (reporting), RFC-0018 (operations equivalence), RFC-0019 (soundness/ZK), RFC-0021 (reproducibility hardening), RFC-0023 (workload) |
| Implements | every Tier-A item in `SCOPE.md` plus the scaling-curve workload of Tier-B |

## 1. Summary

This RFC is the v0.3 *implementation bundle*. It supersedes pieces of
RFC-0008 / RFC-0011 with concrete code, defines the scaling-curve
measurement protocol that replaces v0.2's single-scale headline, and
delivers every Tier-A audit-chain obligation in `SCOPE.md` (A1–A11) as
test-enforced CI gates. The companion design RFCs (RFC-0023, RFC-0025,
RFC-0026, RFC-0027) cover workload, prover architecture, soundness
equivalence, and second-party reproduction respectively; this RFC
covers the *machinery that runs them all*.

## 2. Audit-chain implementation: Tier-A obligations

Each Tier-A obligation in `SCOPE.md` is implemented as a concrete code
PR with the listed test IDs (see `ACCEPTANCE.md` Phase 0 gate). The
sequence below is the recommended commit-order; cross-references to
the issue tracker live in `IMPLEMENTATION.md::v0.3`.

### 2.1 Lockfile commit (A4 → P0.1)

- Remove `third_party/proving-utils/Cargo.lock` from root `.gitignore`.
- `git add` the current working lockfile (ruint pinned at 1.17.2 per
  the 2026-05-18 incident).
- All measurement-path `cargo build` invocations use `--locked`.
- New CI job `lockfile-completeness` (`.github/workflows/ci.yml`): for
  each workspace under `third_party/`, assert `Cargo.lock` is tracked
  in git.
- Test `T21-1`.

### 2.2 Fixture-path parameter (A5 → P0.2)

- In `scripts/measure.sh`, replace the hard-coded `FIXTURE` with
  `FIXTURE_PATH="${FIXTURE_PATH:-fixtures/v0.3/T0-pointadd-1024.json}"`.
- In `bin/run_<prover>.sh` and `bin/verify_<prover>.sh`, replace
  `FIXTURE_RELATIVE_PATH` with the same env-var defaulting pattern.
- `preflight.sh` asserts the fixture's `version` field is `v0.3` (or
  `v0.2` for cross-check runs).
- Test `T21-4`.

### 2.3 Real M7 grammar (A6 → P0.3)

- **SP1 (`third_party/sp1/prover/prove.rs`):** after `prover.prove(...)`,
  read `ExecutionReport::total_instruction_count()` and
  `total_syscall_count()`, derive the SP1 SDK's "constraint count" and
  "trace row count" (formulas in the SP1 SDK's docs at v6.0.2), emit:
  ```
  CONSTRAINTS: <total_constraint_count>
  TRACE_ROWS: <total_trace_row_count>
  ```
  on stdout.
- **Stwo (`bin/apples-prove`):** parse `stwo-cairo`'s component-summary
  block (lines like `RangeCheck_9_9: 3801088`, `BlakeRound: 4352`, …),
  sum across components, emit:
  ```
  CONSTRAINTS: <sum of constraints, per stwo-cairo's component spec>
  TRACE_ROWS: <sum of rows>
  ```
- Remove the `gate_count` sentinel emission at `bin/apples-prove:163-171`.
- Test `T21-5`.

### 2.4 Constant-cost-per-gate (A1 → P0.4 + P0.5)

#### Stwo `C16-T8`

Canary fixture: 4 gates, one per opcode. Compile and prove via
`scarb execute` + `stwo-cairo`'s trace inspector. Parse the per-row
component breakdown to extract the rows attributable to each gate
(the gate-loop trace is identifiable as a sub-component). Assert all
four opcodes contribute equal row counts. **Hard equality, not ±1.**

A non-zero difference is a soundness *and* apples-to-apples failure;
CI must fail the build.

#### SP1 `S17-T8`

Compile the SP1 program with `cargo +1.93.0 build --release`. Run
`cargo objdump --release` on the resulting ELF, locate the `simulate`
function symbol, extract the RISC-V cycle count per `match` arm
(decode instruction-by-instruction; deterministic on a pinned
toolchain). Assert all four arms have equal cycle count.

If LLVM has optimised one arm into early-out, fix with `core::hint::black_box`
in the SP1 program source until cycle-equality holds.

### 2.5 Public-input anchoring (A2 → P0.6 + P0.7)

#### SP1 anchoring

Per RFC-0017 §3.7. After the `assert_eq!` loop in
`third_party/sp1/program/src/main.rs::main`, compute:

```rust
let mut hasher = Sha256::new();
hasher.update(&commitment);                  // SHA-256(circuit_bytes), already computed
hasher.update(&(n_cases as u64).to_be_bytes());
for i in 0..n_cases {
    hasher.update(&xs[i]);                   // each x_i (32 bytes)
    hasher.update(&ys[i]);                   // each y_i (32 bytes)
}
let digest_anchor: [u8; 32] = hasher.finalize().into();
sp1_zkvm::io::commit(&digest_anchor);
```

The verifier (`third_party/sp1/verifier/verifier.rs` updated at
commit `7499931`) is extended to:
1. Read the third committed public value (`digest_anchor`).
2. Recompute `H_SHA256(commitment ‖ n_cases_be ‖ T_serialised)` from
   the fixture.
3. Compare; exit 1 with `PROVER.PUBLIC_INPUT_MISMATCH` on mismatch.

#### Stwo anchoring

Per RFC-0022 §4 + RFC-0025 (direct-Cairo path). Two cases:

- **Bootloader path (legacy / RFC-0022):** The bootloader's
  `program_hash_function: "Pedersen"` already binds the
  `user_args_list` into the proof's public input. `bin/apples-verify`
  recomputes the expected `user_args_list` from the fixture and
  compares to the proof's public input slot.
- **Direct-Cairo path (RFC-0025):** The Cairo executable's input
  array is the proof's public input; same comparison as above.

Test `S19-T4` and `T20-3.2.a/b`.

### 2.6 `bin/apples-verify` (A3 → P0.8)

A new Rust binary (or Python script with `subprocess` calls to the
upstream verifiers) at `bin/apples-verify`:

```
bin/apples-verify --fixture <path> --proof <path> --side <sp1|stwo>
```

The five-step protocol:
1. Read fixture; extract `cb`, both commitments, `n_tc`, `T`.
2. Recompute the side-specific `H_*` over `cb`; check against the
   fixture's hash field. (Defends against `A_fixture`.)
3. Invoke the side's upstream verifier (`prover/verifier` for SP1,
   `stwo-cairo verify` for Stwo) on the proof file; expect exit 0.
4. Parse the proof's public-input slot; recompute the expected slot
   from the fixture per RFC-0019 §6.2; assert equality. (Defends
   against `A_anchor`.)
5. Defence-in-depth: in-Python re-run `sim_reference.run(parse_gtv1(cb), x_i[:32])`
   for each test case; assert `== y_i[:32]`. (Defends against `A_statement`.)

Exit codes: 0 (pass), 1 (any check fails), 2 (precondition).

`bin/verify_<prover>.sh` is rewritten to invoke `bin/apples-verify`,
not the upstream verifier directly. Test obligations `T22-1..5` from
RFC-0022.

### 2.7 `versions.lock` extensions (A8 → P0.9)

`docs/spec/schemas/versions-lock-v1.schema.json` gains 9 new fields per
RFC-0021 §3. `scripts/lock_versions.sh` is extended to populate them.
Tests `T21-3.a/b/c`.

### 2.8 Soundness-floor preflight (A7 → P0.10)

`scripts/preflight.sh` reads `versions.lock::{sp1.fri_params, stwo.circle_fri_params}`,
computes conjectured-soundness via the formulas in RFC-0019 §2.2 and
§2.3, and aborts with `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` (new
subcode per RFC-0021 §17) if either falls below 100 bits.

Test `S19-T1`.

### 2.9 Day-1/Day-2 bootstrap-CI gate (A9 → P0.11)

`python/grover_tax/analyze.py` gains a bootstrap-resampling stability
gate. Synthesise 1000 bootstrap medians for each of day-1 and day-2;
compute the 95% CI on the delta-ratio; gate fires only if the entire
CI exceeds ±5%. Test `T21-11`.

### 2.10 Methodology-lint extensions `L1`–`L6` (A10 → P0.12)

`python/grover_tax/check_results_md.py` gains six new assertion blocks:

- `L1`: presence of the "Operations-counted footprint" section per
  RFC-0018 §4.
- `L2`: presence of the "Commitment-cost asymmetry" disclosure with
  the constraint-counted ratio per RFC-0019 §5.4.
- `L3`: presence of the "Both proofs at conjectured 100-bit
  soundness" declaration.
- `L4`: presence of the bootloader Pedersen disclosure (or "Direct
  Cairo path; no bootloader" if RFC-0025 is shipped at v0.3).
- `L5`: presence of "All public inputs verified against fixture via
  bin/apples-verify".
- `L6`: parsed `n_runs ≥ 10` for M1 and `≥ 50` for M5 from
  `*.timing.json` / `*.verify.json`.

Failure of any: exit 6 with `REPORT.METHODOLOGY_LINT_FAIL`.

### 2.11 Cross-prover FRI equivalence (A11 → P0.13)

Implemented per RFC-0026 §4. `preflight.sh` computes both stacks'
conjectured soundness; aborts if they differ by > 1 bit. Tests
`S26-T1`, `S26-T2`.

## 3. Scaling-curve protocol

### 3.1 Scale tiers

Per RFC-0023 §1 + SPEC-v0.3.md §3.1: `n_g ∈ {1 024, 16 384, 262 144,
1 048 576, 16 777 216}` × `n_tc = 4`.

### 3.2 Linear-model fit

For each prover `X ∈ {SP1, Stwo}`, fit:

```
log(t_X(n_g)) = log(a_X) + log(c_X · n_g + d_X · n_g · log₂(n_g) + b_X)
```

via weighted least squares on the available scale points (T0–T4). The
weighting per point is `1 / σ²(t_X(n_g))` where `σ` is the per-point
sample standard deviation.

A 95% confidence interval is reported via bootstrap resampling (1000
draws) of the per-point measurements.

**Out-of-sample validation (`S24-T2`):** after Phase 2 captures T0/T1/T2,
re-fit on `{T0, T1}` only and predict T2; the prediction's 95% CI must
contain the measured T2. If not, the linear-FRI model is wrong; the
RFC is amended with a non-linear correction.

### 3.3 `make headline` orchestration

A top-level Makefile target `headline`:

```makefile
TIER ?= T0
HEADLINE_DAY ?= 1
HEADLINE_REPLICATE ?= 1

headline:
	bash scripts/preflight.sh
	bash scripts/measure.sh stwo "${TIER}-day${HEADLINE_DAY}-r${HEADLINE_REPLICATE}"
	sleep 600   # 10-min cool-down
	bash scripts/measure.sh sp1 "${TIER}-day${HEADLINE_DAY}-r${HEADLINE_REPLICATE}"
	uv run analyze
	uv run plot
	uv run check-results-md RESULTS.md
```

`make headline TIER=T2 HEADLINE_DAY=2` runs the T2 series on day-2.
The acceptance gates fire on the standard exit codes (RFC-0004 of v0.1
+ RFC-0021 §17 of v0.2 + new `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` etc.).

## 4. Reporting deltas (amends RFC-0011)

`RESULTS.md` template gains:

### 4.1 Per-tier headline table

```
## Headline by scale tier

| Tier | n_g | n_tc | SP1 median | Stwo median | ρ | ρ_constraints | CoV(SP1) | CoV(Stwo) | n_runs |
|---|---|---|---|---|---|---|---|---|---|
| T0 | 1 024 | 4 | <m> | <m> | <ρ> | <ρ_c> | <c> | <c> | 11 |
...
```

### 4.2 Scaling-curve fit

```
## Scaling-curve fit (linear-FRI model)

SP1:  t = a_SP1 + c_SP1·n_g + d_SP1·n_g·log₂(n_g)
        a_SP1 = X.X ± Y.Y ; c_SP1 = ... ; d_SP1 = ...
        95% CI at n_g=16M: [Z.Z, W.W] seconds

Stwo: t = a_Stwo + c_Stwo·n_g + ...
        ... 95% CI at n_g=16M: [...] seconds

Predicted ρ at n_g=16M: ρ_predicted = <m> ± <ci>
Measured ρ at n_g=16M:  ρ_measured  = <m> (single sample, T4 in-budget)
```

### 4.3 Headline summary

```
## v0.3 headline (geometric mean of T1+T2+T3 if all clean)

ρ_v0.3 = <X.XX>×  (SP1 / Stwo, geometric mean across mid-scale tiers)
   T1: <ρ>  CoV <c%>  n=<n>
   T2: <ρ>  CoV <c%>  n=<n>
   T3: <ρ>  CoV <c%>  n=<n>
   95% CI: [<lo>, <hi>]
```

### 4.4 Operations-counted footprint

Per RFC-0018 §4. Required section.

### 4.5 Known limitations

Lists every Tier-C item that is not yet shipped at this release. CI's
methodology lint does not enforce content of this section but requires
the section header to be present (`L1`–`L6` extension).

## 5. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S24-T1` | Linear-FRI model agrees with measured T0+T1 within ±5% | methodology |
| `S24-T2` | Out-of-sample T2 prediction (from T0+T1 fit) within ±10% of measured T2 | methodology |
| `S24-T3` | Spot preemption rate (if applicable) is < 5% per series | infrastructure |
| `S24-T4` | `make headline TIER=T0` exits 0 on a clean rig with all Tier-A green | integration |
| `S24-T5` | `make headline` aborts at preflight if any FRI param falls below 100 bits | soundness |
| `S24-T6` | Day-1 / day-2 bootstrap-CI gate fires on a synthetic 8% delta | methodology |
| `S24-T7` | `RESULTS.md` schema-validates against the new template (RFC-0024 §4) | reporting |

## 6. Open questions

- `OPEN-Q-24-1`: Should the scaling-curve fitter also model the FRI
  tree depth's `O(log n)` contribution explicitly, or is the current
  `c·n + d·n·log n` model sufficient? Empirically determine at Phase 2.
- `OPEN-Q-24-2`: Should Day-3 / Day-N be added if Day-1/Day-2 delta is
  > 5% (rolling stability gate)? v0.3 ships with Day-2 only.

## 7. Implementation order

The 13 Tier-A obligations (P0.1–P0.13) are sequential where dependent,
parallel where independent. The recommended commit order is documented
in `ROADMAP.md::Phase 0`. Each P0.* lands as a separate PR; CODEOWNERS
review is required on any PR touching `third_party/sp1/`,
`stwo-side/cairo/src/`, or `bin/apples-verify`.
