# RFC-0019 — Soundness, Zero-Knowledge, Binding

| Field | Value |
|---|---|
| Status | Accepted |
| Supersedes | the (implicit) soundness statements of `06-security.md` |
| Depends on | RFC-0015 (statement), RFC-0016, RFC-0017, RFC-0018 |
| Audience | cryptographic reviewers |

## 1. Summary

States the soundness floor, retires the residual zero-knowledge language, pins the commitment-binding primitives byte-precisely, quantifies the commitment-cost asymmetry between SP1's SHA-256 syscall and Stwo's in-circuit BLAKE2s, and gives the verifier-equivalence statement that backs RFC-0015 §5.

## 2. Soundness

### 2.1 Floor

Both prover backends MUST be invoked with parameter sets whose *conjectured* soundness against the FRI / Circle-FRI / Groth16 attack models is ≥ **100 bits**, in the standard interactive-oracle-proof setting. We follow the conjectured-vs-proven boundary established in Ben-Sasson, Bentov, Horesh, Riabzev (BBHR18) and Ben-Sasson, Carmon, Ishai, Kopparty, Saraf (BCIKS20), and we adopt the soundness-conjecture extension to Circle-STARKs from Habök, Wuille, et al. (Circle STARKs, eprint 2024/278).

### 2.2 SP1 conjectured soundness

SP1's compressed STARK uses FRI over BabyBear (`p = 2^31 − 2^27 + 1`) with the parameter set documented in `sp1-sdk@6.0.2`:

| Parameter | Value | Conjectured contribution to soundness |
|---|---|---|
| Field | BabyBear (31-bit prime) | Base for the FRI conjecture |
| Code blowup factor | 4 | `log_2(4) = 2` bits per query |
| Number of FRI queries | 100 | `100 · 2 = 200` bits in BBHR18-style accounting; the conjectured bound including soundness slack tightens this to ~100 bits |
| Grinding bits (PoW per IOP round) | 16 | adds 16 bits |
| Round count | derived from circuit-degree polynomial | not a free parameter |

Net conjectured soundness: ≥ 100 bits at the parameters above. RFC-0021 §3 requires `versions.lock::sp1.fri_params` to record `(blowup, num_queries, grinding_bits)`. `preflight.sh` MUST refuse to enter the measurement window if `sp1.fri_params` would imply < 100 bits under BBHR18/BCIKS20 accounting.

### 2.3 Stwo conjectured soundness

Stwo's Circle STARK uses Circle-FRI over M31 (`p = 2^31 − 1`) with the parameter set documented at the pinned `third_party/stwo-cairo/` commit:

| Parameter | Value (default) | Soundness contribution |
|---|---|---|
| Field | M31 (Mersenne-31) extended to ℂ_31 (degree-2) for FRI | Circle-STARK conjecture (eprint 2024/278 §6) |
| Code blowup factor | 4 | 2 bits per query |
| Number of FRI queries | 64 | ~128 bits via BCIKS20-style accounting on the circle group; tightens to ~100 bits with slack |
| Grinding bits | 16 | adds 16 bits |
| Bootloader proof composition | shared between bootloader and task | both must independently meet the floor; RFC-0022 §2 |

Net conjectured soundness: ≥ 100 bits. RFC-0021 §3 records the parameters in `versions.lock::stwo.circle_fri_params`.

### 2.4 Groth16 (SP1 with `SP1_USE_GROTH16=1`)

When the SP1 proof is Groth16-wrapped (RFC-0017 §5), the soundness is the Groth16 soundness for the SP1 verifier circuit, conjectured at 128 bits under the q-PKE / SDH assumption family for the BN254 curve (Groth16 §3). The 2 sb Groth16 setup ceremony provenance (filename, source, entropy contributors) is recorded in `results/sp1_setup.json::groth16_ceremony_origin` (RFC-0011 §"Required fields"). v0.2 amends RFC-0011 to require the field to be a *URL or content hash* (RFC-0021 §3), not a free-form string.

### 2.5 Concrete soundness ≠ asymptotic soundness

The 100-bit floor is conjectured against the IOP model. Concrete attacks (e.g., parallel-FRI grinding precomputation, near-codeword distinguisher attacks) are not in scope; we follow upstream's conjectured-soundness positions. A v0.3 may switch to provably-sound parameter sets if BBHR's lower bounds become tight enough at production parameters.

## 3. Zero-knowledge: explicitly not claimed at v0.2

`circuit_byte_serialisation_hex` is *published* in `fixtures/v0.2.json`. Both prover programs consume `cb` as public input. The proofs are honest-verifier argument-of-knowledge for the NP statement `Φ_v0.2` (RFC-0015 §3.6); they are *not* zero-knowledge.

Practical implications:

- An attacker observing the proof, the public values, and the fixture learns nothing beyond what the fixture already reveals — which is everything. There is no secret.
- The glossary entry for "Zero-knowledge proof" (`10-glossary.md`) MUST be amended (RFC-0021 §15) to clarify: "v0.2's proofs are arguments of knowledge for a public NP statement, not ZK. A future v0.3 may hide `cb` as a witness."
- The `RESULTS.md` template MUST NOT use the phrase "zero-knowledge proof" anywhere in the SP1/Stwo headline rows (RFC-0021 §2).

## 4. Soundness obligations on the v0.2 programs

Beyond the prover-backend parameter floor, the v0.2 programs themselves impose soundness obligations:

### 4.1 SP1 program (RFC-0017)

| Obligation | Mechanism |
|---|---|
| `commitment` in committed public values equals `H_SHA256(cb)` actually computed in zkVM | RFC-0017 §3.3 — call to `Sha256::digest(&circuit_bytes)` then `io::commit` |
| `n_cases` matches the bytes consumed from stdin | RFC-0017 §3.4 — explicit `for _ in 0..n_cases` |
| Test-case anchor `digest_anchor` binds `(cb, n_cases, T)` | RFC-0017 §3.7 |
| Every `assert_eq!` panics on failure, aborting the proof | RISC-V trap → no committed-output → proof unverifiable |

### 4.2 Stwo program (RFC-0016)

| Obligation | Mechanism |
|---|---|
| BLAKE2s commitment equals `expected_commitment` (input slot) | RFC-0016 §6 — `assert!(computed == expected_commitment)` |
| Gate-list `|C| · 8 + 8 = |cb|` | RFC-0016 §4 — assertion in `deserialise` |
| Test-case loop runs `n_tc` times | RFC-0016 §7 — loop counter |
| Carry-slack bits of `limb[8]` remain 0 | RFC-0016 §3 — explicit range check (load-bearing, see §6.3) |

## 5. Commitment-cost asymmetry (the disclosed divergence cost)

RFC-0005 introduces the SHA-256 vs BLAKE2s divergence. This RFC quantifies it.

### 5.1 SP1 SHA-256

The SP1 program uses `sha2` patched per `https://github.com/sp1-patches/RustCrypto-hashes` tag `patch-sha2-0.10.9-sp1-6.0.0`. The patched `Sha256::digest` is implemented as a single zkVM precompile syscall. For a 16400-byte input, the syscall consumes:

- ~`16400 / 64 = 256.25 → 257` SHA-256 compression rounds
- Each compression round: ~`64` RISC-V cycles equivalent (per the precompile's amortised cost)
- Total: ~`257 · 64 = 16448` cycle-equivalents, of which ~`90%` is the precompile and ~`10%` is the surrounding I/O and length-prefixing

Net trace contribution: `k_SP1 · |cb| ≈ 64 · 16400 ≈ 1.05M` rows (per RFC-0018 §2.3 estimate).

The SP1 syscall path is the *zero-overhead* baseline for SHA-256 inside a zkVM. Implementing SHA-256 inside SP1 by hand (without the precompile) would be ~50× slower per byte.

### 5.2 Stwo BLAKE2s

The Stwo Cairo program uses `commit_blake2s` from `commit.cairo`, which calls Cairo's BLAKE2s builtin with the *normalised default* parameter set:

| Parameter | Value (must equal) |
|---|---|
| `digest_length` | 32 |
| `key_length` | 0 |
| `fanout` | 1 |
| `depth` | 1 |
| `leaf_length` | 0 |
| `node_offset` | 0 |
| `node_depth` | 0 |
| `inner_length` | 0 |
| `salt` | 64 zero bytes |
| `personal` | 64 zero bytes |

This MUST match Python's `hashlib.blake2s(input, digest_size=32)` byte-for-byte. RFC-0021 §16 adds a test vector to the schemas table to verify the agreement.

Per-byte trace cost: the BLAKE2s builtin's amortised cost is ~`120` M31 trace rows per byte for the input length range `[64, 100 000]`. For `|cb| = 16400` this is ~`1.97M` rows.

### 5.3 Bootloader's Pedersen commitment

The bootloader (RFC-0022 §3) uses **Pedersen** (Starkware's pedersen, not BLS-12-381) as `program_hash_function` to commit the task program. This commitment is *internal* to the Stwo stack and binds the bootloader to the task it's running; it does *not* extend the apples-to-apples commitment cost. The Pedersen commitment of the ~15 KB compiled task program costs ~`5000` M31 trace rows (per bootloader spec).

This MUST be disclosed in `RESULTS.md` (RFC-0021 §2) as: "Stwo's bootloader internally uses Pedersen to commit the apples-to-apples task program. This is structural to the Cairo bootloader pattern and does not weaken the BLAKE2s commitment binding `Φ_v0.2`."

### 5.4 Cost ratio

```
Cost(SHA-256_SP1) / Cost(BLAKE2s_Stwo) ≈ 1.05M / 1.97M ≈ 0.53
```

The Stwo side spends ~`2×` more constraints on its hash than the SP1 side spends on its hash, in absolute trace-row terms. RFC-0018 §2.3 isolates this in the `k · |cb|` term; the `RESULTS.md` "Operations-counted footprint" section (RFC-0021 §11) makes it visible.

RFC-0005's "0.05–0.1%" claim (which referenced wall-clock fraction, not constraint fraction) is retracted: this RFC supersedes the unsupported quantification with the per-row breakdown above. A wall-clock fraction can be computed by multiplying `k · |cb|` by each prover's per-row FFT cost, both of which are measured at run time.

## 6. Verifier equivalence and binding

### 6.1 Verifier-equivalence statement

**Definition (verifier acceptance).** A verifier `V_X` *accepts* a proof `π` for public input `Π` iff `V_X(π, Π) = 1`. The verifier may have residual probability of accepting an invalid proof; that probability is bounded by the soundness floor of §2.

**Statement.** For the v0.2 statement `Φ_v0.2`, the SP1 verifier `V_SP1` and Stwo verifier `V_Stwo` are *jointly sound*: an adversary who produces `(π_SP1, π_Stwo, Π)` such that both `V_SP1(π_SP1, Π) = 1` and `V_Stwo(π_Stwo, Π) = 1` but `Π ∉ Φ_v0.2` has success probability ≤ `2^{-100}` against the AND of both soundness conjectures.

This is weaker than what is needed for the apples-to-apples claim — we don't need joint soundness, we need *each side independently sound*. Joint soundness is a stronger derived property useful for the headline interpretation: "two prover stacks independently accept the same statement."

### 6.2 Public-input anchoring (formal version of RFC-0015 §3.7)

A proof `π` for `Φ_v0.2` *anchors* a public input `Π = (cb, h, n_g, n_tc, T)` iff:

- **SP1:** `π`'s committed public values contain `(commitment = h, n_cases = n_tc, digest_anchor = H_SHA256(cb ‖ n_tc_be ‖ T_serialised))` and the verifier `V_SP1` re-checks all three against the fixture-recomputed values.
- **Stwo:** `π`'s public-input slot (bootloader-level) contains `(cb_bytes, expected_commitment_lo, expected_commitment_hi, n_tc, T_serialised)` and the bootloader's `program_hash_function`-chain commits all of these into the proof's outer commitment, against which `V_Stwo` re-checks the fixture-recomputed value.

A v0.2 verifier MUST anchor `Π`. A proof that "verifies" without anchoring is `PROVER.PUBLIC_INPUT_MISMATCH`. RFC-0017 §4 and RFC-0022 §4 specify the anchoring mechanism for each side.

### 6.3 Why carry-slack matters

The Stwo state representation uses 9 × 31-bit M31 limbs to hold a 256-bit state. Limb `[8]` carries the top `9·31 − 256 = 23` bits of slack. If these bits are not constrained to zero, an adversarial prover could:

1. Build a state `s'` whose first 256 bits are *not* the simulator's output but whose 23 carry-slack bits hold extra data.
2. Produce a "match" against `y_state` (RFC-0016 §7's `assert!(s == y_state)`) by carefully selecting the carry-slack bits to make a malicious limb-level equality succeed without an actual bit-level equality.

The defence is the carry-slack zero-check (RFC-0016 §3). This RFC marks it **load-bearing for soundness** and requires `C16-T7` to assert it on every `step` invocation, not just at boundaries. A missing carry-slack check is a soundness defect, not a performance defect.

### 6.4 Selector polynomial soundness

RFC-0016 §5's opcode selector polynomial `(s_NOP, s_NOT, s_CNOT, s_TOFFOLI)` is the algebraic encoding of the four-arm switch in `step`. Soundness requires:

- All four selectors are zero outside `{0,1,2,3}` (range-check on `op` enforces this).
- Exactly one selector is `1` for each valid `op` (the polynomial identities ∑ selectors = 1 over the four-row evaluation domain).
- The XOR/AND sub-circuits operate only on the variables their selector is nonzero on (constraint multiplied by selector).

The implementation's selector construction (lookup-based, sumcheck-based, or polynomial-based) is RFC-0016 §5's choice. *This RFC requires the choice to be soundness-equivalent to the polynomial selector above.* A lookup-based selector is soundness-equivalent iff the lookup table covers all four `(op, s_op_value)` rows and is range-checked. A future implementation that uses a different selector MUST update this section with the soundness argument.

## 7. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S19-T1` | `versions.lock` carries `sp1.fri_params` and `stwo.circle_fri_params`; `preflight.sh` asserts both ≥ 100-bit floor | meta |
| `S19-T2` | Cross-implementation BLAKE2s test vector: 100 random inputs, Python `hashlib.blake2s` vs Cairo `commit_blake2s` outputs MUST match byte-for-byte | crypto-equivalence |
| `S19-T3` | Cross-implementation SHA-256 test vector: 100 random inputs, Python `hashlib.sha256` vs SP1 `sha2`-patched `Sha256::digest` outputs MUST match byte-for-byte | crypto-equivalence |
| `S19-T4` | Public-input anchoring: tamper with one byte of `circuit_byte_serialisation_hex` in the fixture (without retampering test-case y values); SP1 verifier MUST reject, Stwo verifier MUST reject | soundness |
| `S19-T5` | Carry-slack invariant: random property test on 1000 `step` invocations; assert `limb[8] < 2^8` always | soundness |
| `S19-T6` | Selector polynomial coverage: enumerate all 4 opcodes; assert exactly-one selector = 1 in each row | soundness |
| `S19-T7` | Wall-clock vs constraint-counted ratio diagnostic in `RESULTS.md` (RFC-0018 §4) is present | meta |

## 8. Open questions

- `OPEN-Q-19-1`: Provably-sound FRI parameters at production query counts (BBHR's lower bounds) are open research. v0.2 follows the conjecture-soundness consensus; v0.3 tracks the academic state of the art.
- `OPEN-Q-19-2`: Cross-prover commitment-cost-equivalence (same constraint count for SHA-256 and BLAKE2s) would close the §5.4 asymmetry. v0.3 may add a normalisation row to `RESULTS.md` ("commitment-cost-normalised wall-clock") if the asymmetry exceeds 2.5×.
