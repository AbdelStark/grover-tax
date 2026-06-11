//! 512-bit state for the repeated-addition workload (KB-15, #127).
//!
//! `iadd256.kmx` is a 512-qubit circuit (two 256-bit registers), so the
//! v0.2 256-bit `State` cannot hold it. Rather than fork the audited limb
//! code, `State512` is a pair of v0.2 `State`s: wires 0..=255 live in `lo`,
//! wires 256..=511 in `hi`. All limb-level invariants (9 x 31-bit limbs,
//! carry slack, range bounds) are inherited from `grover_tax_circuit::limbs`
//! unchanged; the v0.2 modules stay frozen.
//!
//! `step512` mirrors `gates::step` exactly — same opcode-indicator
//! recombination, same unconditional reads, same NOP pass-through — so the
//! constant-cost-per-gate property of RFC-0016 §5 carries over. The only new
//! branch is on the *wire index* (lo vs hi half); both arms perform identical
//! operations, so per-gate cost remains independent of the opcode
//! distribution.

use core::array::ArrayTrait;
use grover_tax_circuit::Gate;
use grover_tax_circuit::limbs::{State, get_bit, set_bit, zero_state};
use grover_tax_circuit::{NO_CTRL, OP_NOP, OP_NOT, OP_CNOT, OP_TOFFOLI};

/// Valid wire indices are 0..=511.
pub const BITS_PER_VALUE_512: u32 = 512;
/// Largest state byte-width a fixture may carry (512 bits).
pub const MAX_STATE_BYTES: u32 = 64;

#[derive(Drop, Copy, PartialEq)]
pub struct State512 {
    pub lo: State,
    pub hi: State,
}

pub fn zero_state512() -> State512 {
    State512 { lo: zero_state(), hi: zero_state() }
}

/// Read bit `i` (0..=511). Panics on out-of-range indices, like
/// `limbs::get_bit`.
pub fn get_bit512(s: State512, i: u32) -> u32 {
    if i >= BITS_PER_VALUE_512 {
        panic!("get_bit512: index out of range: {}", i)
    }
    if i < 256_u32 {
        get_bit(s.lo, i)
    } else {
        get_bit(s.hi, i - 256_u32)
    }
}

/// Functional bit set: returns a new state with bit `i` (0..=511) set to
/// `v` (0 or 1).
pub fn set_bit512(s: State512, i: u32, v: u32) -> State512 {
    if i >= BITS_PER_VALUE_512 {
        panic!("set_bit512: index out of range: {}", i)
    }
    if i < 256_u32 {
        State512 { lo: set_bit(s.lo, i, v), hi: s.hi }
    } else {
        State512 { lo: s.lo, hi: set_bit(s.hi, i - 256_u32, v) }
    }
}

// -- gate execution (mirrors gates.cairo over the wide state) ----------------

fn is_eq(a: u32, b: u32) -> u32 {
    if a == b { 1 } else { 0 }
}

/// Identical recombination to `gates::compute_new_target`; duplicated here
/// because the original is module-private.
fn compute_new_target(opcode: u32, t: u32, a: u32, b: u32) -> u32 {
    let is_not = is_eq(opcode, OP_NOT);
    let is_cnot = is_eq(opcode, OP_CNOT);
    let is_toff = is_eq(opcode, OP_TOFFOLI);
    let delta = is_not * 1 + is_cnot * a + is_toff * (a * b);
    t + delta - 2 * t * delta
}

fn read_bit_or_zero512(s: State512, i: u32) -> u32 {
    if i == NO_CTRL {
        0
    } else {
        get_bit512(s, i)
    }
}

/// Range-check the wire fields of a gate against the 512-wire bound,
/// per the same opcode-conditional matrix as `gates::range_check_gate`.
pub fn range_check_gate512(gate: Gate) {
    if gate.opcode > OP_TOFFOLI {
        panic!("range_check_gate512: opcode {} not in [0,3]", gate.opcode)
    }
    if gate.opcode == OP_NOP {
        if gate.target != NO_CTRL {
            panic!("range_check_gate512: NOP target must be NO_CTRL, got {}", gate.target)
        }
        if gate.ctrl_a != NO_CTRL {
            panic!("range_check_gate512: NOP ctrl_a must be NO_CTRL, got {}", gate.ctrl_a)
        }
        if gate.ctrl_b != NO_CTRL {
            panic!("range_check_gate512: NOP ctrl_b must be NO_CTRL, got {}", gate.ctrl_b)
        }
    } else if gate.opcode == OP_NOT {
        range_check_wire512(gate.target, 'target', true);
        if gate.ctrl_a != NO_CTRL {
            panic!("range_check_gate512: NOT ctrl_a must be NO_CTRL, got {}", gate.ctrl_a)
        }
        if gate.ctrl_b != NO_CTRL {
            panic!("range_check_gate512: NOT ctrl_b must be NO_CTRL, got {}", gate.ctrl_b)
        }
    } else if gate.opcode == OP_CNOT {
        range_check_wire512(gate.target, 'target', true);
        range_check_wire512(gate.ctrl_a, 'ctrl_a', true);
        if gate.ctrl_b != NO_CTRL {
            panic!("range_check_gate512: CNOT ctrl_b must be NO_CTRL, got {}", gate.ctrl_b)
        }
    } else {
        range_check_wire512(gate.target, 'target', true);
        range_check_wire512(gate.ctrl_a, 'ctrl_a', true);
        range_check_wire512(gate.ctrl_b, 'ctrl_b', true);
    }
}

fn range_check_wire512(wire: u32, kind: felt252, is_required_real: bool) {
    if wire == NO_CTRL {
        if is_required_real {
            panic!("range_check_wire512: slot {} requires a real wire, got NO_CTRL", kind)
        }
    } else {
        if wire >= BITS_PER_VALUE_512 {
            panic!("range_check_wire512: slot {} wire {} out of range [0, 512)", kind, wire)
        }
    }
}

/// Apply one gate over the 512-bit state. Mirrors `gates::step`: reads are
/// unconditional, NOP passes the state through unchanged, and the write-back
/// happens for every non-NOP opcode.
pub fn step512(s: State512, gate: Gate) -> State512 {
    let t_bit = if gate.opcode == OP_NOP || gate.target == NO_CTRL {
        0
    } else {
        get_bit512(s, gate.target)
    };
    let a_bit = read_bit_or_zero512(s, gate.ctrl_a);
    let b_bit = read_bit_or_zero512(s, gate.ctrl_b);
    let new_t = compute_new_target(gate.opcode, t_bit, a_bit, b_bit);
    if gate.opcode == OP_NOP {
        s
    } else {
        set_bit512(s, gate.target, new_t)
    }
}

// -- byte I/O (mirrors io.cairo, variable width) ------------------------------

/// Deserialise up to 64 raw bytes into a `State512`. Bytes beyond
/// `bytes.len()` read as zero, so narrower fixtures (iadd64: 16 bytes,
/// iadd8: 2 bytes) load with their ancillae/unused wires cleared. Bit
/// ordering matches Python's `BitVector`: bit `i` at byte `i/8`, position
/// `i%8` (LSB-first).
pub fn bytes_to_state512(bytes: @Array<u8>) -> State512 {
    let n_bytes: u32 = bytes.len();
    if n_bytes > MAX_STATE_BYTES {
        panic!("bytes_to_state512: {} bytes exceeds the 64-byte state", n_bytes)
    }
    let mut s = zero_state512();
    let mut i: u32 = 0;
    let n_bits: u32 = n_bytes * 8_u32;
    loop {
        if i == n_bits { break; }
        let byte_idx: u32 = i / 8_u32;
        let bit_in_byte: u32 = i % 8_u32;
        let byte_val: u32 = (*bytes.at(byte_idx)).into();
        let shifted: u32 = byte_val / pow2_8(bit_in_byte);
        let bit_val: u32 = shifted & 1_u32;
        s = set_bit512(s, i, bit_val);
        i = i + 1_u32;
    };
    s
}

/// `2^k` for `k` in `0..=7` (byte-level shifts).
fn pow2_8(k: u32) -> u32 {
    if k == 0 { 1_u32 }
    else if k == 1 { 2_u32 }
    else if k == 2 { 4_u32 }
    else if k == 3 { 8_u32 }
    else if k == 4 { 16_u32 }
    else if k == 5 { 32_u32 }
    else if k == 6 { 64_u32 }
    else { 128_u32 }
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use core::array::ArrayTrait;
    use super::{
        bytes_to_state512, get_bit512, set_bit512, step512, zero_state512,
        BITS_PER_VALUE_512,
    };
    use grover_tax_circuit::Gate;
    use grover_tax_circuit::{NO_CTRL, OP_NOT, OP_CNOT, OP_TOFFOLI};

    #[test]
    fn set_then_get_round_trip_across_halves() {
        // One position per limb in each half plus the half boundary.
        let positions = array![0_u32, 30, 31, 255, 256, 287, 511];
        let mut k: u32 = 0;
        loop {
            if k == positions.len() { break; }
            let i = *positions.at(k);
            let s = set_bit512(zero_state512(), i, 1);
            assert!(get_bit512(s, i) == 1);
            if i > 0 { assert!(get_bit512(s, i - 1) == 0); }
            if i + 1 < BITS_PER_VALUE_512 { assert!(get_bit512(s, i + 1) == 0); }
            k = k + 1;
        };
    }

    #[test]
    #[should_panic]
    fn get_bit512_out_of_range_panics() {
        let _ = get_bit512(zero_state512(), 512);
    }

    #[test]
    fn cnot_across_the_half_boundary() {
        // Control on wire 300 (hi half), target on wire 5 (lo half).
        let s = set_bit512(zero_state512(), 300, 1);
        let gate = Gate { opcode: OP_CNOT, target: 5, ctrl_a: 300, ctrl_b: NO_CTRL };
        let out = step512(s, gate);
        assert!(get_bit512(out, 5) == 1);
        assert!(get_bit512(out, 300) == 1);
    }

    #[test]
    fn toffoli_on_high_wires() {
        let s = set_bit512(set_bit512(zero_state512(), 400, 1), 511, 1);
        let gate = Gate { opcode: OP_TOFFOLI, target: 256, ctrl_a: 400, ctrl_b: 511 };
        let out = step512(s, gate);
        assert!(get_bit512(out, 256) == 1);
    }

    #[test]
    fn not_flips_high_wire() {
        let gate = Gate { opcode: OP_NOT, target: 510, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        let out = step512(zero_state512(), gate);
        assert!(get_bit512(out, 510) == 1);
        let back = step512(out, gate);
        assert!(get_bit512(back, 510) == 0);
    }

    #[test]
    fn bytes_to_state512_full_width() {
        // 64 bytes: byte 0 = 0x01 (bit 0), byte 63 = 0x80 (bit 511).
        let mut bytes: Array<u8> = ArrayTrait::new();
        bytes.append(0x01_u8);
        let mut i: u32 = 1;
        loop { if i == 63 { break; } bytes.append(0_u8); i = i + 1; };
        bytes.append(0x80_u8);
        let s = bytes_to_state512(@bytes);
        assert!(get_bit512(s, 0) == 1);
        assert!(get_bit512(s, 511) == 1);
        assert!(get_bit512(s, 1) == 0);
        assert!(get_bit512(s, 510) == 0);
    }

    #[test]
    fn bytes_to_state512_short_input_zero_pads() {
        // iadd64-style 16-byte state: wires 128.. read as zero.
        let mut bytes: Array<u8> = ArrayTrait::new();
        let mut i: u32 = 0;
        loop { if i == 16 { break; } bytes.append(0xFF_u8); i = i + 1; };
        let s = bytes_to_state512(@bytes);
        assert!(get_bit512(s, 127) == 1);
        assert!(get_bit512(s, 128) == 0);
        assert!(get_bit512(s, 511) == 0);
    }
}
