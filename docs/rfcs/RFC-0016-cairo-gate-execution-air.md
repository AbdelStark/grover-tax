# RFC-0016 — Cairo Gate-Execution AIR (Stwo Side)

| Field | Value |
|---|---|
| Status | Accepted |
| Supersedes | RFC-0004 (Cairo circuit design at v0.1) |
| Depends on | RFC-0015 (statement), RFC-0022 (bootloader), RFC-0019 (soundness) |
| Implements | `stwo-side/cairo/src/{lib,gates,serialise,io,limbs,commit}.cairo` |

## 1. Summary

Defines the Cairo program that the Stwo side proves under the apples-to-apples v0.2 statement (RFC-0015 §3.6). Specifies the state representation (`[u31; 9]`), the byte ↔ state mapping, the gate-by-gate transition function, the in-circuit BLAKE2s commitment check, the constraint-shape obligations (constant-cost-per-gate), and the bootloader-task interface. Test obligations and CI gates are listed in §8.

## 2. Program shape

The Cairo entry point is

```
#[executable]
pub fn apples_to_apples_executable(input: Array<felt252>) -> felt252
```

at `stwo-side/cairo/src/lib.cairo:194`. The signature is fixed by the bootloader's `Cairo1Executable` task type (RFC-0022 §2). Return value is `felt252(1)` on success; any constraint violation panics inside the prover, which the bootloader propagates as a verifier-rejecting trace.

The `input` array layout, normative:

| Offset | Field | Type-in-felt252 |
|---|---|---|
| `0` | `n_cb` | u32 |
| `1 .. 1 + n_cb` | `circuit_bytes` (one byte per slot) | u8 |
| `1 + n_cb` | `commitment_lo` | u128 (low 128 bits of `H_BLAKE2s(cb)` interpreted big-endian) |
| `2 + n_cb` | `commitment_hi` | u128 (high 128 bits) |
| `3 + n_cb` | `n_tc` | u32 |
| then per test case (`64` felts) | `x_bytes[0..32]` then `y_bytes[0..32]` | u8 |

Total input length: `4 + n_cb + 64·n_tc` felts. For the v0.2 fixture (`n_cb = 16400`, `n_tc = 4`): `4 + 16400 + 256 = 16660` felts.

Implementations MUST refuse to extend this layout in v0.2.x without a RFC bump (RFC-0021 §15).

## 3. State representation

The 256-bit state `s ∈ B^256` is represented as `State = [u31; 9]` (9 × 31-bit M31 limbs).

The mapping `bytes_to_state : B^{256} → State` and its inverse `state_to_bytes : State → B^{256}` are normative and implemented in `io.cairo`:

```
bit i of s lives at:
    limb_idx     = i / 31
    bit_in_limb  = i mod 31

The 256-bit byte array (LSB-first within byte, byte i/8 holds bit i)
is unpacked bit-by-bit and the bits are repacked into the 9 limbs
using the above (limb_idx, bit_in_limb) coordinate.
```

The top `9 × 31 − 256 = 23` bits of `limb[8]` are *carry slack* and MUST be 0 in any well-formed state. The Cairo program MUST range-check every limb at `≤ 2^31 − 1` (this is the trivial M31 range; Stwo's range-check builtin provides it). After every `apply_gate`, the implementation MUST further check that the carry-slack bits remain zero. RFC-0019 §6.3 explains why this carry-slack check is load-bearing for soundness.

## 4. Parser

`parse_gtv1` is implemented in `serialise.cairo::deserialise(@bytes : Array<u8>) -> Array<Gate>`. The function MUST:

1. Assert `bytes.len() ≥ 8`.
2. Assert `bytes[0..4] == b"GTV1"`.
3. Read `n_g = u32::from_le_bytes(bytes[4..8])`.
4. Assert `bytes.len() == 8 + 8·n_g`.
5. For each `i ∈ [0..n_g)`, parse `bytes[8+8i .. 8+8(i+1)]` into a `Gate { opcode, target, ctrl_a, ctrl_b }`.
6. Apply `range_check_gate` (defined in `gates.cairo`) to each parsed gate.

The `range_check_gate` MUST enforce all `valid_gate` constraints listed in RFC-0015 §3.3 *except* the `a ≠ t / b ≠ t / a ≠ b` clauses (which `gen_fixtures.py` guarantees; the prover does not enforce them and is not weakened by their absence — RFC-0019 §6.2).

## 5. Gate step function

The constant-cost `step : (State, Gate) -> State` function is defined in `gates.cairo::step`. Its constraint shape is normative:

For each call site, regardless of opcode, the constraint system MUST emit:

- Exactly **3** boolean-decomposition constraints for `get_bit` calls (one for `s[t]`, one for `s[a]`, one for `s[b]`; the implementation passes `0xFFFF` and the constraint stays satisfied by virtue of a selector — see below).
- Exactly **2** XOR-AND constraints (one AND for TOFFOLI's `s[a] ∧ s[b]`, conditionally; one XOR for the target update).
- Exactly **1** boolean-set constraint for the target bit.
- Exactly **1** opcode-selector polynomial constraining which of `s[a]`, `s[b]`, `(s[a] ∧ s[b])` enters the XOR.

The total constraint count per gate MUST equal `c_Stwo_gate` independent of opcode. RFC-0018 §2.1 gives the operations-counted equivalence proof assuming this invariant. **Implementations MUST add a CI test (`C16-T8`) that recomputes the per-opcode trace-row count from a canary fixture with one of each opcode and asserts equality across all four.** Violation breaks the apples-to-apples claim.

The opcode-selector polynomial is

```
let s_NOP     = (1 - op) · (2 - op) · (3 - op) / 6                  // 1 iff op = 0
let s_NOT     = op · (2 - op) · (3 - op) / 2                        // 1 iff op = 1
let s_CNOT    = op · (op - 1) · (3 - op) / 2                        // 1 iff op = 2
let s_TOFFOLI = op · (op - 1) · (op - 2) / 6                        // 1 iff op = 3
```

These four selectors sum to 1 over `op ∈ {0,1,2,3}` and zero out elsewhere. The actual implementation in `gates.cairo` MAY use a different selector construction (lookup, sumcheck) provided the constraint count per gate remains independent of opcode and the soundness analysis in RFC-0019 §6.4 covers the chosen construction.

## 6. Commitment check

The in-circuit BLAKE2s commitment is computed by `commit.cairo::commit_blake2s(@bytes : Array<u8>) -> [u32; 8]` using stwo-cairo's Blake2s builtin (RFC-0019 §5.2 pins the builtin's BLAKE2s parameters).

The check is

```
let digest = commit_blake2s(@circuit_bytes);
let computed = digest_to_u256_be(digest);
let expected = u256 { low: expected_lo, high: expected_hi };
assert!(computed == expected, "blake2s commitment mismatch");
```

`digest_to_u256_be` (`lib.cairo:63`) converts the LE-u32-word builtin output into a BE-byte u256 interpretation. The conversion is a fixed permutation, ~7 M31 multiplications and 14 additions per digest (constant-cost; RFC-0018 §2.2 counts it under the `O(|cb|)` term).

## 7. Test-case loop

The test-case loop is

```
let gates = deserialise(@circuit_bytes);                              // step §4
for i in 0 .. n_tc:
    let x_bytes = read 32 felt252 bytes from input;
    let y_bytes = read 32 felt252 bytes from input;
    let mut s   = bytes_to_state(@x_bytes);                          // §3
    let y_state = bytes_to_state(@y_bytes);
    for j in 0 .. gates.len():
        range_check_gate(gates[j]);                                   // §4 (idempotent w.r.t. §4 deserialise check)
        s = step(s, gates[j]);                                        // §5
    assert!(s == y_state, "test case simulation mismatch");
```

The `range_check_gate` MUST be re-emitted at the per-step site because the deserialise-time check is on a fresh `Array<Gate>` value that may not propagate range information across the loop boundary. Cairo's borrow-check + Stwo's per-row range-check shape make a single range-check insufficient. RFC-0018 §2.1 counts both range-checks under `c_Stwo_gate`.

## 8. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `C16-T1` | Empty input (`n_cb = 0, n_tc = 0`) → returns `1`, no panic | unit (Cairo) |
| `C16-T2` | One-gate-NOP circuit, one test case `(x = 0, y = 0)` → returns `1` | unit |
| `C16-T3` | One-gate-NOT circuit on bit 0, `x = 0`, `y = 1` → returns `1` | unit |
| `C16-T4` | Reject: same as C16-T3 but `y = 0` → panics with "test case simulation mismatch" | unit |
| `C16-T5` | Reject: corrupted `cb` header (wrong magic) → panics during `deserialise` | unit |
| `C16-T6` | Reject: wrong BLAKE2s expected digest → panics with "blake2s commitment mismatch" | unit |
| `C16-T7` | Carry-slack invariant: after 1024 random TOFFOLI gates over a random `x`, every state limb fits in 31 bits *and* `limb[8] < 2^8` (256-bit state lives in the low 8 bits of limb 8) | property (Cairo or Python re-derivation) |
| `C16-T8` | Constant-cost-per-gate: emit a 4-gate canary circuit (one NOP, one NOT, one CNOT, one TOFFOLI) and assert that the per-gate trace row count is identical across the four (read from the stwo-cairo prover's per-component trace summary) | integration |
| `C16-T9` | Round-trip: `bytes_to_state(state_to_bytes(s)) == s` for random `s ∈ State` | unit |
| `C16-T10` | Cross-validate: for the v0.2 fixture, run `apples_to_apples_executable` to completion under `scarb execute` and confirm Cairo's output matches `sim_reference.py`'s output bit-for-bit | integration |

`C16-T8` is the apples-to-apples guarantee on the Stwo side. A failure means the Stwo prover has been optimised to skip work for "cheap" opcodes, breaking RFC-0018's equivalence theorem. CI MUST fail the build on `C16-T8` regression.

## 9. Non-goals

This RFC does not specify:

- The bootloader's own AIR (RFC-0022 §2).
- Stwo's FRI / Circle-FRI parameter selection (RFC-0019 §2).
- The `program_hash_function` used by the bootloader (Pedersen; documented in RFC-0022 §3).
- The `extract_public_segments` path inside `stwo-cairo` (the existing patch is in `third_party/stwo-cairo/`; documented in RFC-0022 §6).

## 10. Open questions

- `OPEN-Q-16-1`: Can we eliminate the second `range_check_gate` per step by widening the range-check shape across the loop boundary? Estimated 15% Stwo prove-time win; requires modifying `gates.cairo` and potentially a stwo-cairo patch. Deferred to v0.3.
