//! Canonical byte serialisation + NOP padding.
//!
//! Mirrors `grover_tax.serialise` (Python, #11) byte-for-byte. The Python
//! serialiser is the load-bearing source; this module is the Cairo
//! verifier-side reproduction. `circuit_byte_serialisation_hex` in
//! `fixtures/v0.1.json` is the public commitment to the secret gate list,
//! so the in-circuit Blake2s pass (#23) must compute the *exact same bytes*
//! that Python computed at fixture-generation time.
//!
//! Wire format (`GateListV1`, RFC-0002 §"Canonical byte serialisation"):
//!
//! ```text
//! +-------+------------------+
//! | b"GTV1"  (4 bytes)       |
//! | n_gates  u32 LE (4 bytes)|
//! +--------------------------+
//! | gate[0]  (8 bytes)       |
//! | gate[1]  (8 bytes)       |
//! | ...                      |
//! +--------------------------+
//!
//! Each Gate:
//!   opcode  u8        (1 byte)
//!   pad     u8 = 0    (1 byte)
//!   target  u16 LE    (2 bytes)
//!   ctrl_a  u16 LE    (2 bytes)
//!   ctrl_b  u16 LE    (2 bytes)
//! ```
//!
//! NOP padding (RFC-0004 §"Padding"): the gate list is padded with NOP
//! gates (opcode=0, target=ctrl_a=ctrl_b=NO_CTRL=0xFFFF) so the *padded*
//! length is the next power of two. NOPs have no semantic effect on the
//! state (proven by #21's `nop_leaves_state_unchanged` test), so padding
//! is observation-preserving. The padded length is committed via the
//! serialised `n_gates` so the verifier sees the same `|C|_padded`.

use core::array::ArrayTrait;
use grover_tax_circuit::Gate;
use grover_tax_circuit::{NO_CTRL, OP_NOP};

pub const GATE_BYTES: u32 = 8;
pub const HEADER_BYTES: u32 = 8;

/// Push the four magic bytes `b"GTV1"` onto `buf`.
fn push_magic(ref buf: Array<u8>) {
    buf.append('G');
    buf.append('T');
    buf.append('V');
    buf.append('1');
}

/// Push `value` as little-endian `u32` (4 bytes) onto `buf`.
fn push_u32_le(ref buf: Array<u8>, value: u32) {
    let b0: u8 = (value & 0xFF).try_into().unwrap();
    let b1: u8 = ((value / 0x100) & 0xFF).try_into().unwrap();
    let b2: u8 = ((value / 0x10000) & 0xFF).try_into().unwrap();
    let b3: u8 = ((value / 0x1000000) & 0xFF).try_into().unwrap();
    buf.append(b0);
    buf.append(b1);
    buf.append(b2);
    buf.append(b3);
}

/// Push `value` as little-endian `u16` (2 bytes) onto `buf`.
///
/// Cairo's `u32` is used as the container; the high two bytes must already
/// be zero (enforced by `range_check_gate` for real wires + the `0xFFFF`
/// NO_CTRL sentinel which already fits in 16 bits).
fn push_u16_le(ref buf: Array<u8>, value: u32) {
    let b0: u8 = (value & 0xFF).try_into().unwrap();
    let b1: u8 = ((value / 0x100) & 0xFF).try_into().unwrap();
    buf.append(b0);
    buf.append(b1);
}

/// Serialise one `Gate` into the 8-byte wire form.
fn push_gate(ref buf: Array<u8>, gate: Gate) {
    let opcode_byte: u8 = (gate.opcode & 0xFF).try_into().unwrap();
    buf.append(opcode_byte);
    buf.append(0_u8); // pad
    push_u16_le(ref buf, gate.target);
    push_u16_le(ref buf, gate.ctrl_a);
    push_u16_le(ref buf, gate.ctrl_b);
}

/// Smallest power of two ≥ `n`. Inputs above ~`2^30` saturate at `0`
/// (overflow) — for grover-tax v0.1 the gate-list length is bounded well
/// under `2^24`, so the simple doubling loop is correct in practice.
pub fn next_pow2(n: u32) -> u32 {
    if n <= 1 {
        return 1;
    }
    let mut p: u32 = 1;
    loop {
        if p >= n { break p; }
        p = p * 2;
    }
}

/// Build a canonical-NOP gate (used by padding).
fn nop_gate() -> Gate {
    Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL }
}

/// Pad `gates` to the next power-of-two length with NOP gates and return
/// the padded sequence.
///
/// The padded length is the *committed* gate count — both the public
/// `circuit_byte_serialisation_hex` and the public `circuit_commitment_*`
/// fields in `fixtures/v0.1.json` bind the padded form. The witness
/// `secret_C` arrives at the prover in its padded shape.
pub fn pad_to_pow2(gates: @Array<Gate>) -> Array<Gate> {
    let n = gates.len();
    let target = next_pow2(n);
    let mut out = ArrayTrait::<Gate>::new();
    let mut i: u32 = 0;
    loop {
        if i == n { break; }
        out.append(*gates.at(i));
        i = i + 1;
    };
    let pad = nop_gate();
    loop {
        if out.len() == target { break; }
        out.append(pad);
    };
    out
}

/// Canonical byte serialisation of `gates`.
///
/// `gates` is assumed already padded (callers run `pad_to_pow2` first);
/// the serialiser writes the length as-is into the header.
pub fn canonical_serialise(gates: @Array<Gate>) -> Array<u8> {
    let mut out = ArrayTrait::<u8>::new();
    push_magic(ref out);
    push_u32_le(ref out, gates.len());
    let mut i: u32 = 0;
    let n = gates.len();
    loop {
        if i == n { break; }
        push_gate(ref out, *gates.at(i));
        i = i + 1;
    };
    out
}

// -- Deserialiser -----------------------------------------------------------

/// Read a `u32` little-endian from 4 bytes at `off`.
fn read_u32_le(bytes: @Array<u8>, off: u32) -> u32 {
    let b0: u32 = (*bytes.at(off)).into();
    let b1: u32 = (*bytes.at(off + 1_u32)).into();
    let b2: u32 = (*bytes.at(off + 2_u32)).into();
    let b3: u32 = (*bytes.at(off + 3_u32)).into();
    b0 + b1 * 0x100_u32 + b2 * 0x10000_u32 + b3 * 0x1000000_u32
}

/// Read a `u16` as `u32` little-endian from 2 bytes at `off`.
fn read_u16_le(bytes: @Array<u8>, off: u32) -> u32 {
    let b0: u32 = (*bytes.at(off)).into();
    let b1: u32 = (*bytes.at(off + 1_u32)).into();
    b0 + b1 * 0x100_u32
}

/// Deserialise `GateListV1` bytes into an `Array<Gate>`.
///
/// Mirrors `grover_tax.serialise.deserialise` (Python) byte-for-byte.
/// Panics on bad magic, non-zero pad bytes, or invalid input length.
pub fn deserialise(bytes: @Array<u8>) -> Array<Gate> {
    // Check magic b"GTV1" = [71, 84, 86, 49].
    assert!(*bytes.at(0) == 71_u8, "deserialise: magic[0]");
    assert!(*bytes.at(1) == 84_u8, "deserialise: magic[1]");
    assert!(*bytes.at(2) == 86_u8, "deserialise: magic[2]");
    assert!(*bytes.at(3) == 49_u8, "deserialise: magic[3]");

    let n_gates: u32 = read_u32_le(bytes, 4_u32);

    let mut out: Array<Gate> = ArrayTrait::new();
    let mut i: u32 = 0_u32;
    loop {
        if i == n_gates { break; }
        let base: u32 = HEADER_BYTES + i * GATE_BYTES;
        let opcode: u32 = (*bytes.at(base)).into();
        let pad: u8 = *bytes.at(base + 1_u32);
        assert!(pad == 0_u8, "deserialise: non-zero pad");
        let target: u32  = read_u16_le(bytes, base + 2_u32);
        let ctrl_a: u32  = read_u16_le(bytes, base + 4_u32);
        let ctrl_b: u32  = read_u16_le(bytes, base + 6_u32);
        out.append(Gate { opcode, target, ctrl_a, ctrl_b });
        i = i + 1_u32;
    };
    out
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use core::array::ArrayTrait;
    use super::{canonical_serialise, next_pow2, pad_to_pow2, HEADER_BYTES, GATE_BYTES};
    use grover_tax_circuit::Gate;
    use grover_tax_circuit::{NO_CTRL, OP_NOP, OP_NOT, OP_CNOT, OP_TOFFOLI};

    fn make_gates_v1() -> Array<Gate> {
        // The exact 4-gate vector pinned by Python's
        // `test_regression_vector_four_gates` (#11).
        let mut g = ArrayTrait::<Gate>::new();
        g.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_CNOT, target: 1, ctrl_a: 0, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_TOFFOLI, target: 2, ctrl_a: 0, ctrl_b: 1 });
        g.append(Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g
    }

    #[test]
    fn next_pow2_table() {
        assert!(next_pow2(0) == 1);
        assert!(next_pow2(1) == 1);
        assert!(next_pow2(2) == 2);
        assert!(next_pow2(3) == 4);
        assert!(next_pow2(4) == 4);
        assert!(next_pow2(5) == 8);
        assert!(next_pow2(7) == 8);
        assert!(next_pow2(8) == 8);
        assert!(next_pow2(9) == 16);
        assert!(next_pow2(100) == 128);
    }

    #[test]
    fn pad_to_pow2_no_op_when_already_pow2() {
        let g = make_gates_v1();
        let original_len = g.len();
        let padded = pad_to_pow2(@g);
        assert!(padded.len() == 4);
        assert!(padded.len() == original_len);
    }

    #[test]
    fn pad_to_pow2_pads_to_next_pow2() {
        let mut g = ArrayTrait::<Gate>::new();
        g.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_NOT, target: 1, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_NOT, target: 2, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        let padded = pad_to_pow2(@g);
        assert!(padded.len() == 4);
        // The last element is a NOP.
        assert!(*(padded.at(3)).opcode == OP_NOP);
    }

    #[test]
    fn serialise_empty_gate_list_emits_header_only() {
        let empty = ArrayTrait::<Gate>::new();
        let bytes = canonical_serialise(@empty);
        assert!(bytes.len() == HEADER_BYTES);
        // Magic b"GTV1".
        assert!(*bytes.at(0) == 'G');
        assert!(*bytes.at(1) == 'T');
        assert!(*bytes.at(2) == 'V');
        assert!(*bytes.at(3) == '1');
        // n_gates = 0, little-endian.
        assert!(*bytes.at(4) == 0_u8);
        assert!(*bytes.at(5) == 0_u8);
        assert!(*bytes.at(6) == 0_u8);
        assert!(*bytes.at(7) == 0_u8);
    }

    #[test]
    fn serialise_four_gate_regression_vector() {
        // The exact bytes Python's #11 regression test asserts on. If this
        // test ever changes, the wire format has drifted and every prior
        // fixture is invalid.
        let bytes = canonical_serialise(@make_gates_v1());
        let expected_len = HEADER_BYTES + 4 * GATE_BYTES;
        assert!(bytes.len() == expected_len);

        // Header.
        assert!(*bytes.at(0) == 'G');
        assert!(*bytes.at(1) == 'T');
        assert!(*bytes.at(2) == 'V');
        assert!(*bytes.at(3) == '1');
        assert!(*bytes.at(4) == 4_u8); // n_gates = 4, LE.
        assert!(*bytes.at(5) == 0_u8);
        assert!(*bytes.at(6) == 0_u8);
        assert!(*bytes.at(7) == 0_u8);

        // Gate 0: NOT, target=0, ctrl_a=NO_CTRL, ctrl_b=NO_CTRL.
        // Bytes: 01 00 00 00 ff ff ff ff
        assert!(*bytes.at(8)  == 1_u8);
        assert!(*bytes.at(9)  == 0_u8);
        assert!(*bytes.at(10) == 0_u8);
        assert!(*bytes.at(11) == 0_u8);
        assert!(*bytes.at(12) == 0xFF_u8);
        assert!(*bytes.at(13) == 0xFF_u8);
        assert!(*bytes.at(14) == 0xFF_u8);
        assert!(*bytes.at(15) == 0xFF_u8);

        // Gate 1: CNOT, target=1, ctrl_a=0, ctrl_b=NO_CTRL.
        // Bytes: 02 00 01 00 00 00 ff ff
        assert!(*bytes.at(16) == 2_u8);
        assert!(*bytes.at(17) == 0_u8);
        assert!(*bytes.at(18) == 1_u8);
        assert!(*bytes.at(19) == 0_u8);
        assert!(*bytes.at(20) == 0_u8);
        assert!(*bytes.at(21) == 0_u8);
        assert!(*bytes.at(22) == 0xFF_u8);
        assert!(*bytes.at(23) == 0xFF_u8);

        // Gate 2: TOFFOLI, target=2, ctrl_a=0, ctrl_b=1.
        // Bytes: 03 00 02 00 00 00 01 00
        assert!(*bytes.at(24) == 3_u8);
        assert!(*bytes.at(25) == 0_u8);
        assert!(*bytes.at(26) == 2_u8);
        assert!(*bytes.at(27) == 0_u8);
        assert!(*bytes.at(28) == 0_u8);
        assert!(*bytes.at(29) == 0_u8);
        assert!(*bytes.at(30) == 1_u8);
        assert!(*bytes.at(31) == 0_u8);

        // Gate 3: NOP, target=NO_CTRL, ctrl_a=NO_CTRL, ctrl_b=NO_CTRL.
        // Bytes: 00 00 ff ff ff ff ff ff
        assert!(*bytes.at(32) == 0_u8);
        assert!(*bytes.at(33) == 0_u8);
        assert!(*bytes.at(34) == 0xFF_u8);
        assert!(*bytes.at(35) == 0xFF_u8);
        assert!(*bytes.at(36) == 0xFF_u8);
        assert!(*bytes.at(37) == 0xFF_u8);
        assert!(*bytes.at(38) == 0xFF_u8);
        assert!(*bytes.at(39) == 0xFF_u8);
    }

    #[test]
    fn serialise_includes_padding_in_header_length() {
        let mut g = ArrayTrait::<Gate>::new();
        g.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_NOT, target: 1, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_NOT, target: 2, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });

        let padded = pad_to_pow2(@g);
        let bytes = canonical_serialise(@padded);
        // Padded length is 4, header records it.
        assert!(*bytes.at(4) == 4_u8);
        assert!(bytes.len() == HEADER_BYTES + 4 * GATE_BYTES);
    }
}
