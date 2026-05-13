# RFC-0004: Cairo circuit design (Stwo side)

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

This RFC fixes the design of `stwo-side/circuit.cairo`: the M31-based representation of 256-bit secp256k1 state, the gate-list encoding, the gate-execution loop, the bit-stripe handling, and the in-circuit Blake2s commitment check. The design's goal is to be honest representative of what a Stwo deployment of this proof statement would look like, not to be artificially competitive.

## Motivation

Cairo runs natively over the M31 prime field (`p = 2^31 - 1`). The proof statement involves 256-bit elliptic-curve operations, which do not fit in a single M31 element. The representation choice — limb count, limb width, carry strategy — affects:

- the constraint count (M7),
- the wall-clock (M1),
- the trace rows (M7).

This RFC locks the choice so that future "the Cairo program got faster" commits cannot silently change what we are measuring.

## Goals

- A single, locked 256-bit representation usable by every gate operation.
- A gate-execution loop whose constraint count is `O(|C|)` with a small constant.
- A bit-stripe handling that matches `sim.rs` at the pinned `W`.
- An in-circuit Blake2s check that binds the witness to the public commitment.
- Stable selector-style branching inside the gate-execution dispatcher (so constraint cost per gate is the same regardless of opcode).

## Non-Goals

- Optimising for minimum Cairo size. A representative implementation is preferred over a hand-tuned one. See "Drawbacks".
- Supporting variable-length gate lists. `|C|` is padded to a power of two; see "Padding".
- Multi-instance batching. One proof attests one `C` against one `T`.

## Proposed Design

### Field and representation

- Base field: M31 (`p = 2^31 - 1`), as Stwo natively requires.
- 256-bit element representation: `[u31; 9]`. 9 limbs of 31 bits each = 279 bits of raw capacity, leaving ~23 bits of slack for carry handling during addition / subtraction. Limb 0 is the low-order limb (little-endian).
- Bit access on a 256-bit value uses limb-and-position decoding:
  ```
  fn get_bit(state: [u31; 9], i: u32) -> u31 {
      let limb_idx = i / 31;
      let bit_in_limb = i % 31;
      (state[limb_idx] >> bit_in_limb) & 1
  }
  ```
- Bit set similarly, with carry-free OR / XOR.

### Gate encoding

Matches the canonical byte serialisation of `RFC-0002`:

```
struct Gate {
    opcode:  u32,    // M31-encoded; values 0..=3
    target:  u32,    // bit index 0..255
    ctrl_a:  u32,    // bit index 0..255, or 0xFFFF if unused
    ctrl_b:  u32,    // bit index 0..255, or 0xFFFF if unused
}
```

Cairo loads the gate list as a fixed-size array `[Gate; G]` where `G = ceil_pow2(|C|)`.

### Gate-execution loop

```
fn step(state: [u31; 9], gate: Gate) -> [u31; 9] {
    // 1. Read target, ctrl_a, ctrl_b bits (constant cost regardless of opcode).
    let t_bit = get_bit(state, gate.target);
    let a_bit = if gate.ctrl_a == NO_CTRL { 0 } else { get_bit(state, gate.ctrl_a) };
    let b_bit = if gate.ctrl_b == NO_CTRL { 0 } else { get_bit(state, gate.ctrl_b) };

    // 2. Compute the new target bit via a constant-cost expression
    //    parameterised on opcode.
    //
    //    NOP:    new_t = t_bit
    //    NOT:    new_t = t_bit XOR 1
    //    CNOT:   new_t = t_bit XOR a_bit
    //    TOFF:   new_t = t_bit XOR (a_bit AND b_bit)
    //
    //    Implemented as a unified expression:
    //       new_t = t_bit XOR (op_is_nop ? 0
    //                                    : op_is_not  ? 1
    //                                    : op_is_cnot ? a_bit
    //                                                : a_bit AND b_bit)
    //    Each branch flag is derived from a 4-way decoding of `opcode`.
    let new_t_bit = compute_new_target(gate.opcode, t_bit, a_bit, b_bit);

    // 3. Write back.
    set_bit(state, gate.target, new_t_bit)
}

fn main(public_T: Array<TestCase>, public_H_C: [u8; 32], secret_C: Array<Gate>) {
    // a. Range-check all gate fields.
    range_check_gates(secret_C);

    // b. For each test case, simulate.
    for tc in public_T {
        let state_initial = expand_x(tc.x);
        let mut state = state_initial;
        for gate in secret_C {
            state = step(state, gate);
        }
        let y_expected = expand_y(tc.y);
        assert(state == y_expected);
    }

    // c. Commit check.
    let C_bytes = canonical_serialise(secret_C);
    let computed_commitment = blake2s(C_bytes);
    assert(computed_commitment == public_H_C);
}
```

The `step` function's constraint cost is *constant per gate*, regardless of opcode. This is essential: a workload whose constraint cost varies by opcode is a workload whose total constraints depend on `C`'s opcode distribution, which would couple our headline to that distribution rather than to gate count.

### Bit-stripe handling

`sim.rs` processes state in stripes of width `W`. Cairo mirrors this exactly: the inner loop operates `W` bits at a time, with `W` pinned from `WORKLOAD.md`. If `W = 1`, the loop is per-bit; if `W = 8`, the loop is per-byte; the choice is upstream's, not ours.

### Padding

`|C|` is rounded up to the next power of two with NOP gates. NOP semantics: `new_t_bit == t_bit`. This guarantees:

- Power-of-two array length, friendly to Cairo's loop unrolling and to Stwo's trace alignment.
- Constraint count visible from `|C|_padded`, not from `|C|_original`.
- `RESULTS.md` reports both `|C|_original` and `|C|_padded` for transparency.

### Range checks

Every limb is asserted in `0..2^31` after every gate. Implemented via Stwo's built-in range check primitive.

Every bit index (`target`, `ctrl_a`, `ctrl_b`) is asserted in `0..=255 ∪ {0xFFFF}`. The `0xFFFF` sentinel is allowed *only* for opcodes that ignore the corresponding control (`NOT` ignores `ctrl_a`/`ctrl_b`; `CNOT` ignores `ctrl_b`; `NOP` ignores both; `TOFFOLI` allows neither). The assertion is opcode-conditional.

### Blake2s in-circuit

Stwo Cairo provides a Blake2s built-in. We use it with default initialisation (no personalisation, no key, 32-byte output). The canonical byte serialisation is computed in-circuit from the witness `secret_C` and the Blake2s built-in is invoked on the resulting byte array.

## Alternatives Considered

### A1. 8 × 32-bit limbs (`[u32; 8]`)

Rejected: M31 is 31-bit; using 32-bit limbs in Cairo wastes the top bit of each limb and forces extra range checks. The 9 × 31-bit layout is the natural fit.

### A2. 16 × 16-bit limbs (`[u16; 16]`)

Smaller per-limb, more limbs. Rejected: doubles the number of limb-level operations per add/sub, slower in practice.

### A3. Single big-int limb with overflow checks

Rejected: M31 cannot represent values larger than `2^31 - 1` in a single limb. Multi-limb is structural to M31 + 256-bit.

### A4. Opcode-specific gate cost (variable cost per gate)

A "fast path" for NOP that takes zero constraints. Rejected: makes constraint count depend on opcode distribution, biasing the comparison. The unified `step` is honest.

### A5. Implement SHA-256 in Cairo instead of Blake2s

This would eliminate the commitment-hash divergence. Rejected — see `RFC-0005` for full justification. Briefly: SHA-256 in Cairo would dominate the Stwo wall-clock and confound the comparison.

### A6. No padding; variable-length gate list

Stwo can handle variable-length data, but trace-row alignment to power-of-two is friendlier and matches what a production Cairo program would do. Pad with NOP.

## Drawbacks

- The unified `step` is slower than an opcode-specialised dispatcher for "all-NOP" `C`. Acceptable: real `C` has very few NOPs.
- Hex-encoding the gate list in the fixture and re-deriving the canonical byte serialisation in Cairo is duplicated work. Acceptable: the duplication is the integrity check.
- We do not optimise the Cairo program below "competent implementation" level. A team that spent months tuning could go faster. That is a known limitation; the comparison is "representative implementation vs representative implementation", not "PhD-optimised vs PhD-optimised". `RESULTS.md` says so explicitly.

## Migration / Rollout

First implementation. The Cairo program lands once `RFC-0001` (workload pin) and `RFC-0002` (fixture) are merged, since the Cairo constants reference `WORKLOAD.md` values.

## Testing Strategy

- **C-T1**: Cairo unit test for each opcode, all 2/4/8-bit input combinations. Same table as `RFC-0003.R-T1`.
- **C-T2**: Cairo unit test for limb arithmetic. Add, sub, conditional select; range-check assertions.
- **C-T3**: Cairo unit test: a hand-crafted small `C` (e.g., 16 gates that perform a known bit-flip pattern) and 4 hand-crafted `(x, y)` pairs. Assert the in-circuit simulation produces `y`.
- **C-T4**: Round-trip: load a fixture's `circuit_byte_serialisation_hex`, re-serialise in-circuit, assert byte equality with the public input.
- **C-T5**: Blake2s built-in test: a 64-byte test vector (matches `P-1.2`).
- **C-T6**: Bit-layout interop with Python (`R-T4`): assert same `x` bytes produce same bit vector.
- **C-T7**: NOP no-op invariance (matches `R-T5`): inserting a NOP gate into `C` does not change the final state.
- **C-T8**: Padding correctness: `|C|_original` vs `|C|_padded` produce identical final state.

## Open Questions

**OPEN-Q-4.1** — Limb-count choice (9 vs 11). 11 × 31-bit gives more slack for repeated additions before reduction; 9 is the minimum. We choose 9 for transparency with PRD §5.3, but if downstream testing reveals excessive reduction overhead, this is the first knob to revisit. Owner: maintainer. Resolution target: by end of Cairo-implementation phase. If revisited, that triggers a minor bump.

## References

- `docs/spec/02-public-api.md` (Cairo program is consumer of the fixture)
- `docs/spec/03-data-model.md` (canonical byte serialisation)
- `RFC-0001`, `RFC-0002`, `RFC-0003`
- `RFC-0005` (why Blake2s, not SHA-256, in-circuit)
- PRD `PRD.md` §5.3
