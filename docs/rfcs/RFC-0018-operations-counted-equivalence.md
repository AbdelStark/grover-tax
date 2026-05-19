# RFC-0018 — Operations-Counted Equivalence

| Field | Value |
|---|---|
| Status | Accepted |
| Depends on | RFC-0015 (statement), RFC-0016 (Cairo AIR), RFC-0017 (SP1 program), RFC-0019 (soundness) |
| Defends against | Adversary `A_statement` (RFC-0020 §3) |
| Audience | cryptographic reviewers, methodology auditors |

## 1. Summary

States and proves (at the level of rigour appropriate for a benchmark methodology paper) that the SP1 and Stwo provers at v0.2 expend computational effort over the *same* arithmetised relation up to disclosed divergences. The result is the formal underpinning of the "apples-to-apples" claim: an outside reviewer can read this RFC plus RFC-0015 and conclude that the wall-clock ratio in `RESULTS.md` is measuring "STARK prove cost on bit-level gate-circuit execution," not an arbitrary or asymmetric workload.

This RFC is the keystone for the apples-to-apples soundness argument. RFCs 0015–0017 specify *what* is computed; RFC-0019 specifies *how soundly*; this RFC specifies *that the work is equivalent up to disclosure*.

## 2. Equivalence theorem

### 2.1 Formal statement

Let `Φ_v0.2^{X}` (`X ∈ {SP1, Stwo}`) be the relation in RFC-0015 §3.6. Let `Π_X` be the prover specified in RFC-0016 (`X = Stwo`) or RFC-0017 (`X = SP1`).

Define the **constraint footprint** of a prover argument as the multiset of constraint-system rows used (its trace-row count), parameterised by `(n_g, n_tc)` and the byte length `|cb|`. We write `rows_X(n_g, n_tc, |cb|)`.

**Theorem 1 (operations-counted equivalence).** Assuming RFC-0016 §5 (constant-cost-per-gate, Stwo) and RFC-0017 §3.1 (constant-cycle-per-gate, SP1), there exist constants `c_Stwo, c_SP1, k_Stwo, k_SP1, b_Stwo, b_SP1, B ∈ ℝ_{>0}` such that for every `n_g, n_tc ∈ ℕ` and `|cb| = 8 + 8 n_g`:

```
rows_Stwo(n_g, n_tc, |cb|)  =  c_Stwo · n_tc · n_g + k_Stwo · |cb| + b_Stwo + B    (Stwo)
rows_SP1  (n_g, n_tc, |cb|)  =  c_SP1  · n_tc · n_g + k_SP1  · |cb| + b_SP1        (SP1)
```

where `B` is the bootloader's fixed-cost trace contribution (RFC-0022 §2), independent of `(n_g, n_tc, |cb|)`. The terms decompose as:

| Term | SP1 meaning | Stwo meaning |
|---|---|---|
| `c_X · n_tc · n_g` | RISC-V cycles for the `simulate` loop body × per-cycle SP1 trace rows | `step` constraints per gate × M31 trace rows per constraint |
| `k_X · |cb|` | bytes hashed by SHA-256 syscall + cycles for `parse_gtv1` | bytes hashed by BLAKE2s builtin + felt operations for `deserialise` |
| `b_X` | program preamble/postamble cycles (`read_vec`, public-value commits, digest_anchor) | program preamble (input read), commitment-check, return |
| `B` | 0 (no bootloader) | bootloader cycles for task dispatch, args parsing, program-hash chain |

**The two prover programs perform the exact same set of operations on the same data**, modulo:
1. The choice of hash family (SHA-256 vs BLAKE2s; disclosed, RFC-0019 §5);
2. The choice of base field (BabyBear vs M31; structural, non-tunable);
3. The presence of a bootloader on the Stwo side (necessary; RFC-0022 §1 explains why no symmetric bootloader is added on the SP1 side);
4. The arithmetisation primitives (RISC-V cycle constraints vs Cairo AP constraints + Stwo Circle-AIR composition).

### 2.2 Proof sketch

We prove `rows_Stwo` (Stwo); `rows_SP1` is analogous.

*Per-gate cost.* By RFC-0016 §5, every call to `step(s, g)` emits exactly the same constraint shape regardless of `g.opcode`. The selector polynomial sums to 1 across opcodes; the boolean-decomposition, XOR-AND, and target-set sub-circuits each have fixed degree and fixed number of rows. Hence each gate consumes a constant number of trace rows, call it `c_Stwo`.

*Per test case.* The test-case loop iterates `n_tc` times, each iteration running the gate loop `n_g` times. Outside the gate loop, each test-case iteration does:
- 32 felt252 reads (`x_bytes`)
- 32 felt252 reads (`y_bytes`)
- one `bytes_to_state` (256 boolean decompositions + 9 limb composes — constant cost)
- one `bytes_to_state` for `y`
- one final `assert_eq` (9 limb comparisons — constant cost)

These contribute a per-test-case constant `c_Stwo_tc`. Total per-test-case cost: `c_Stwo_tc + c_Stwo · n_g`. Total across all test cases: `c_Stwo · n_tc · n_g + n_tc · c_Stwo_tc`. The `n_tc · c_Stwo_tc` term is linear in `n_tc` but constant in `n_g`; for `n_tc = O(1)` (v0.2 fixes `n_tc = 4`) it is absorbed into `b_Stwo`. For `n_tc → ∞` it would belong in a separate term; v0.3 will accommodate that if `n_tc` grows.

*Per-byte hash cost.* `commit_blake2s(@circuit_bytes)` consumes `|cb|` bytes by the BLAKE2s builtin. Each byte contributes a constant number of trace rows (the builtin's per-byte cost; documented in stwo-cairo's component spec). Plus the `deserialise` step touches each byte once. Linear in `|cb|`: `k_Stwo · |cb|`.

*Preamble + postamble + bootloader.* All constant. Aggregate into `b_Stwo + B`.

Hence `rows_Stwo(n_g, n_tc, |cb|) = c_Stwo · n_tc · n_g + k_Stwo · |cb| + b_Stwo + B`. ∎

### 2.3 Constants for v0.2

| Constant | SP1 | Stwo | Source |
|---|---|---|---|
| `c_X` | ~12 (RISC-V cycles per `apply_gate` × ~1.2 SP1 trace rows/cycle) | ~80 (constraint count per `step`, including selectors and range-check) | C16-T8, S17-T8 measurements (filled at first measured run) |
| `k_X` | ~64 (1 cycle/byte hashed × ~1 row/cycle, syscall amortised) | ~120 (per-byte BLAKE2s builtin cost) | M7 trace summary |
| `b_X` | ~5000 (program preamble) | ~10000 (program preamble + Cairo runtime) | M7 |
| `B` | 0 | ~50000 (bootloader fixed cost) | RFC-0022 §2 |

These are *expected* values. The first measured run series fills them with measured values to within ±5% (per RFC-0021 §6 trend detection); the actual numbers MUST be recorded in `RESULTS.md` §"Operations-counted footprint" (RFC-0021 §11). RFC-0019 §5 separately quantifies the commitment-cost contribution within `k_X`.

### 2.4 Wall-clock vs constraint-counted ratio

The constraint-counted ratio at v0.2 fixed `(n_g = 1024, n_tc = 4)` is:

```
ρ_constraints := rows_SP1(1024, 4, 16400) / rows_Stwo(1024, 4, 16400)
              ≈ (12 · 4096 + 64 · 16400 + 5000) / (80 · 4096 + 120 · 16400 + 60000)
              ≈ (49152 + 1049600 + 5000) / (327680 + 1968000 + 60000)
              ≈ 1103752 / 2355680
              ≈ 0.47
```

The *wall-clock* ratio `ρ` is empirical and depends on each prover's constants — FFT cost per row, hash cost per byte (which `RESULTS.md` separately discloses), commit-tree cost. The wall-clock ratio at the 2026-05-14 v0.1 headline was 33644× (SP1 much slower than Stwo) — driven primarily by SP1's compressed-STARK FRI prove cost being much larger per-row than Stwo's Circle-FRI cost, NOT by SP1 doing 33644× more work.

RFC-0021 §11 requires `RESULTS.md` to report both `ρ` (wall-clock) and `ρ_constraints` (computed from M7). The ratio `ρ / ρ_constraints` is the "per-row efficiency factor" — the apples-to-apples diagnostic that says "of the wall-clock ratio, how much is workload and how much is per-row prover efficiency."

## 3. What this RFC does *not* prove

- It does **not** prove the constants `c_X, k_X, b_X` in §2.3 are tight or optimal. They are measured, not derived from a model.
- It does **not** prove that the two arithmetisations have equal proof-system overhead. SP1's BabyBear FRI vs Stwo's M31 Circle-FRI have meaningfully different per-row costs and ratio constants. RFC-0019 §2 documents this asymmetry.
- It does **not** prove that the bootloader's `B` is bounded or sub-linear in any workload parameter. RFC-0022 §2 fixes the bootloader's `B` numerically; if a future bootloader change adds workload-dependent terms, this RFC's theorem fails and a v0.3 supersession is required.
- It does **not** address the cost of *verifying* the proofs, which is a separate measurement (M5).

## 4. Operational implications

The apples-to-apples claim is *meaningful* iff:

1. **C16-T8 passes** (constant-cost-per-gate on Stwo, RFC-0016 §5).
2. **S17-T8 passes** (constant-cycle-per-gate on SP1, RFC-0017 §3.1).
3. **The commitment-cost breakdown row in `RESULTS.md`** isolates `k_X · |cb|` (RFC-0019 §5, RFC-0021 §11).
4. **The bootloader cost `B`** is disclosed and verified to be workload-independent (RFC-0022 §2).

If any of (1)–(4) fails, the headline `ρ` is not measuring what RFC-0015 says it is, and the v0.2 RESULTS.md is *not* an apples-to-apples comparison in the sense of this RFC.

The methodology lint (`check-results-md`, RFC-0011) MUST be extended (RFC-0021 §2) to assert that `RESULTS.md` contains:

```
### Operations-counted footprint

| Term      | SP1 (rows) | Stwo (rows) |
|-----------|------------|-------------|
| c · n_tc · n_g  | <measured> | <measured>  |
| k · |cb|        | <measured> | <measured>  |
| b               | <measured> | <measured>  |
| B (bootloader)  | 0          | <measured>  |
| total           | <measured> | <measured>  |

Ratio ρ_constraints = <total_SP1 / total_Stwo> = <…>.
Wall-clock ratio ρ = <…>.
Per-row efficiency factor (ρ / ρ_constraints) = <…>.
```

A `RESULTS.md` lacking this section fails the methodology lint and CI.

## 5. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S18-T1` | C16-T8 + S17-T8 both green in CI (cross-reference) | meta |
| `S18-T2` | Methodology lint asserts the "Operations-counted footprint" section in `RESULTS.md` | meta |
| `S18-T3` | For three different `(n_g, n_tc)` pairs (e.g., `(256, 1)`, `(1024, 4)`, `(4096, 4)`), verify the linear-in-`n_g·n_tc` model: fit `c_X` and `b_X` from two data points, predict the third, assert prediction within ±5% of measured | methodology |
| `S18-T4` | Bootloader cost `B` measurement: a "no-task" bootloader invocation (the bootloader runs an empty task) measures `B`; `B` must agree with §2.3 within ±5% | methodology |

## 6. Open questions

- `OPEN-Q-18-1`: When `n_tc` grows, the per-test-case constant `c_Stwo_tc` will dominate over the per-gate cost for small `n_g`. The v0.2 fixed `(n_g = 1024, n_tc = 4)` avoids the regime but a v0.3 with `n_tc = 64` would expose it. Theorem 1's `b_X` assumption (constant in both `n_g` and `n_tc`) would need amendment. Deferred.
- `OPEN-Q-18-2`: Cross-prover *constraint-equivalence* (same number of rows for the same workload) would strengthen the apples-to-apples claim. v0.2 makes no such claim — the constants differ. A v0.3 that arithmetises both stacks to the same row count is a research project.
