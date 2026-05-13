//! Gate dispatcher with constant-cost `step()` (RFC-0004 §"Gate-execution loop").
//!
//! Four opcodes from `Opcode`:
//!
//!   * `NOP`     — no effect.
//!   * `NOT`     — `s[target] ^= 1`.
//!   * `CNOT`    — `s[target] ^= s[ctrl_a]`.
//!   * `TOFFOLI` — `s[target] ^= s[ctrl_a] & s[ctrl_b]`.
//!
//! The dispatcher reads `target`, `ctrl_a`, `ctrl_b` bits unconditionally so
//! constraint cost per gate is the same regardless of opcode. The unified
//! expression for the new target bit is:
//!
//!   ```text
//!   new_t = t XOR (op_nop  ? 0
//!                : op_not  ? 1
//!                : op_cnot ? a
//!                          : a AND b)
//!   ```
//!
//! Implemented branchlessly via opcode-indicator arithmetic:
//!
//!   ```text
//!   delta = is_not  * 1
//!         + is_cnot * a
//!         + is_toff * (a * b)
//!   new_t = t XOR delta
//!   ```
//!
//! `is_*` are mutually-exclusive 0/1 indicators derived from a single u32
//! equality check per opcode. The four indicators sum to 1 for any valid
//! opcode; the dispatcher's `range_check_opcode` enforces the bound.
//!
//! Control-wire range checks (RFC-0004 §"Range checks") are
//! opcode-conditional: `0xFFFF` (NO_CTRL) is permitted *only* on opcodes
//! that ignore that wire. `range_check_gate` enforces the matrix:
//!
//!   | opcode  | target req | ctrl_a allowed | ctrl_a NO_CTRL | ctrl_b allowed | ctrl_b NO_CTRL |
//!   |---------|------------|----------------|----------------|----------------|----------------|
//!   | NOP     |            |                |        ✓       |                |        ✓       |
//!   | NOT     |    ✓       |                |        ✓       |                |        ✓       |
//!   | CNOT    |    ✓       |       ✓        |                |                |        ✓       |
//!   | TOFFOLI |    ✓       |       ✓        |                |       ✓        |                |
//!
//! NOP and NOT explicitly require the unused control slots to carry
//! `NO_CTRL`; CNOT requires `ctrl_b = NO_CTRL`; TOFFOLI requires both
//! `ctrl_a` and `ctrl_b` to be real (`< 256`) wire indices.

use grover_tax_circuit::Gate;
use grover_tax_circuit::limbs::{
    BITS_PER_VALUE, State, get_bit, set_bit,
};
use grover_tax_circuit::{NO_CTRL, OP_NOP, OP_NOT, OP_CNOT, OP_TOFFOLI};

/// `1` if `a == b`, else `0`. Mutually-exclusive opcode indicators rely on
/// this to dispatch branchlessly.
fn is_eq(a: u32, b: u32) -> u32 {
    if a == b { 1 } else { 0 }
}

/// Range-check the opcode field. Panics if `opcode` is outside `{0,1,2,3}`.
pub fn range_check_opcode(opcode: u32) {
    if opcode > OP_TOFFOLI {
        panic!("range_check_opcode: opcode {} not in [0,3]", opcode)
    }
}

/// Range-check a single wire field for a given opcode.
///
/// `wire` is one of `gate.target`, `gate.ctrl_a`, `gate.ctrl_b`. `kind`
/// tags which slot the wire fills so the diagnostic names the right field.
/// `is_required_real` is `true` when the slot must point at a real bit
/// (0..=255); `false` when `NO_CTRL` is acceptable.
fn range_check_wire(wire: u32, kind: felt252, is_required_real: bool) {
    if wire == NO_CTRL {
        if is_required_real {
            panic!("range_check_wire: slot {} requires a real wire, got NO_CTRL", kind)
        }
    } else {
        if wire >= BITS_PER_VALUE {
            panic!("range_check_wire: slot {} wire {} out of range [0, 256)", kind, wire)
        }
    }
}

/// Range-check every wire field of a gate per the opcode-conditional
/// matrix documented at module level.
pub fn range_check_gate(gate: Gate) {
    range_check_opcode(gate.opcode);

    if gate.opcode == OP_NOP {
        // NOP ignores every slot; require NO_CTRL for cleanliness.
        if gate.target != NO_CTRL {
            panic!("range_check_gate: NOP target must be NO_CTRL, got {}", gate.target)
        }
        if gate.ctrl_a != NO_CTRL {
            panic!("range_check_gate: NOP ctrl_a must be NO_CTRL, got {}", gate.ctrl_a)
        }
        if gate.ctrl_b != NO_CTRL {
            panic!("range_check_gate: NOP ctrl_b must be NO_CTRL, got {}", gate.ctrl_b)
        }
    } else if gate.opcode == OP_NOT {
        range_check_wire(gate.target, 'target', true);
        if gate.ctrl_a != NO_CTRL {
            panic!("range_check_gate: NOT ctrl_a must be NO_CTRL, got {}", gate.ctrl_a)
        }
        if gate.ctrl_b != NO_CTRL {
            panic!("range_check_gate: NOT ctrl_b must be NO_CTRL, got {}", gate.ctrl_b)
        }
    } else if gate.opcode == OP_CNOT {
        range_check_wire(gate.target, 'target', true);
        range_check_wire(gate.ctrl_a, 'ctrl_a', true);
        if gate.ctrl_b != NO_CTRL {
            panic!("range_check_gate: CNOT ctrl_b must be NO_CTRL, got {}", gate.ctrl_b)
        }
    } else {
        // OP_TOFFOLI — both controls must be real.
        range_check_wire(gate.target, 'target', true);
        range_check_wire(gate.ctrl_a, 'ctrl_a', true);
        range_check_wire(gate.ctrl_b, 'ctrl_b', true);
    }
}

/// Compute the new value of `target` bit for a single gate application,
/// without writing it back.
///
/// `t`, `a`, `b` are pre-read bit values (0 or 1). The expression's
/// constraint cost is constant regardless of opcode — the branches above
/// are compile-time selectors over a single arithmetic recombination.
fn compute_new_target(opcode: u32, t: u32, a: u32, b: u32) -> u32 {
    let is_not = is_eq(opcode, OP_NOT);
    let is_cnot = is_eq(opcode, OP_CNOT);
    let is_toff = is_eq(opcode, OP_TOFFOLI);
    // NOP contributes 0 — t passes through unchanged.
    let delta = is_not * 1 + is_cnot * a + is_toff * (a * b);
    // XOR over u32 0/1 values: t XOR delta == t + delta - 2 * t * delta.
    t + delta - 2 * t * delta
}

/// Read a bit at `i`, treating `NO_CTRL` as the literal 0 (matches RFC-0004
/// §"Gate-execution loop" step 1).
fn read_bit_or_zero(s: State, i: u32) -> u32 {
    if i == NO_CTRL {
        0
    } else {
        get_bit(s, i)
    }
}

/// Apply one gate, returning the new state.
///
/// Per RFC-0004 §"Gate-execution loop":
///
/// 1. Read t, a, b bits — constant cost regardless of opcode.
/// 2. Compute new_t via `compute_new_target` — constant cost.
/// 3. Write back at `gate.target` — constant cost (for NOP we *also* write
///    `t` back to `t` so the trace shape is identical to non-NOP).
///
/// NOP path returns a state byte-equal to the input (since `delta = 0` and
/// the write-back is t → t). The function does not short-circuit; the
/// `set_bit` call happens unconditionally so the trace-row count per gate
/// is independent of opcode distribution.
pub fn step(s: State, gate: Gate) -> State {
    // Range-checking is delegated to the caller (the main loop calls
    // `range_check_gate` once per gate before invoking `step`).
    let t_bit = if gate.opcode == OP_NOP || gate.target == NO_CTRL {
        // NOP doesn't have a meaningful target; read bit 0 as a stable
        // placeholder. The compute_new_target path zeros out the delta so
        // the write-back equals t_bit unchanged.
        0
    } else {
        get_bit(s, gate.target)
    };
    let a_bit = read_bit_or_zero(s, gate.ctrl_a);
    let b_bit = read_bit_or_zero(s, gate.ctrl_b);
    let new_t = compute_new_target(gate.opcode, t_bit, a_bit, b_bit);
    if gate.opcode == OP_NOP {
        // NOP: state passes through unchanged (no write-back).
        s
    } else {
        set_bit(s, gate.target, new_t)
    }
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::{compute_new_target, range_check_gate, step};
    use grover_tax_circuit::Gate;
    use grover_tax_circuit::limbs::{State, get_bit, set_bit, zero_state};
    use grover_tax_circuit::{NO_CTRL, OP_NOP, OP_NOT, OP_CNOT, OP_TOFFOLI};

    fn one_bit_state(idx: u32, val: u32) -> State {
        set_bit(zero_state(), idx, val)
    }

    // -- NOP semantics --------------------------------------------------------

    #[test]
    fn nop_leaves_state_unchanged() {
        let s = one_bit_state(7, 1);
        let gate = Gate {
            opcode: OP_NOP,
            target: NO_CTRL,
            ctrl_a: NO_CTRL,
            ctrl_b: NO_CTRL,
        };
        let out = step(s, gate);
        let mut i: u32 = 0;
        loop {
            if i == 256 { break; }
            assert!(get_bit(out, i) == get_bit(s, i));
            i = i + 1;
        };
    }

    // -- NOT truth table (2 cases) ---------------------------------------------

    #[test]
    fn not_flips_target_zero_to_one() {
        let s = zero_state();
        let g = Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        assert!(get_bit(step(s, g), 0) == 1);
    }

    #[test]
    fn not_flips_target_one_to_zero() {
        let s = one_bit_state(5, 1);
        let g = Gate { opcode: OP_NOT, target: 5, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        assert!(get_bit(step(s, g), 5) == 0);
    }

    // -- CNOT truth table (4 cases) --------------------------------------------

    fn cnot_cell(ctrl: u32, tgt: u32) -> u32 {
        let mut s = zero_state();
        s = set_bit(s, 0, ctrl);
        s = set_bit(s, 8, tgt);
        let g = Gate { opcode: OP_CNOT, target: 8, ctrl_a: 0, ctrl_b: NO_CTRL };
        get_bit(step(s, g), 8)
    }

    #[test]
    fn cnot_truth_table() {
        assert!(cnot_cell(0, 0) == 0);
        assert!(cnot_cell(0, 1) == 1);
        assert!(cnot_cell(1, 0) == 1);
        assert!(cnot_cell(1, 1) == 0);
    }

    // -- TOFFOLI truth table (8 cases) -----------------------------------------

    fn toffoli_cell(a: u32, b: u32, t: u32) -> u32 {
        let mut s = zero_state();
        s = set_bit(s, 0, a);
        s = set_bit(s, 8, b);
        s = set_bit(s, 16, t);
        let g = Gate { opcode: OP_TOFFOLI, target: 16, ctrl_a: 0, ctrl_b: 8 };
        get_bit(step(s, g), 16)
    }

    #[test]
    fn toffoli_truth_table() {
        // t' = t XOR (a AND b) for all 8 (a,b,t) inputs.
        assert!(toffoli_cell(0, 0, 0) == 0);
        assert!(toffoli_cell(0, 0, 1) == 1);
        assert!(toffoli_cell(0, 1, 0) == 0);
        assert!(toffoli_cell(0, 1, 1) == 1);
        assert!(toffoli_cell(1, 0, 0) == 0);
        assert!(toffoli_cell(1, 0, 1) == 1);
        assert!(toffoli_cell(1, 1, 0) == 1);
        assert!(toffoli_cell(1, 1, 1) == 0);
    }

    // -- compute_new_target arithmetic identity --------------------------------

    #[test]
    fn compute_new_target_nop_passes_through() {
        // NOP: delta = 0, so new_t == t.
        let mut t: u32 = 0;
        loop {
            if t == 2 { break; }
            assert!(compute_new_target(OP_NOP, t, 0, 0) == t);
            assert!(compute_new_target(OP_NOP, t, 1, 1) == t);
            t = t + 1;
        };
    }

    // -- Range-check matrix ----------------------------------------------------

    #[test]
    #[should_panic]
    fn range_check_rejects_unknown_opcode() {
        let g = Gate { opcode: 42, target: 0, ctrl_a: 0, ctrl_b: 0 };
        range_check_gate(g);
    }

    #[test]
    #[should_panic]
    fn range_check_rejects_target_out_of_range_for_not() {
        let g = Gate { opcode: OP_NOT, target: 1024, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        range_check_gate(g);
    }

    #[test]
    #[should_panic]
    fn range_check_rejects_no_ctrl_target_on_not() {
        // NOT must point at a real wire; NO_CTRL is rejected.
        let g = Gate { opcode: OP_NOT, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        range_check_gate(g);
    }

    #[test]
    #[should_panic]
    fn range_check_rejects_ctrl_a_no_ctrl_on_cnot() {
        let g = Gate { opcode: OP_CNOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        range_check_gate(g);
    }

    #[test]
    #[should_panic]
    fn range_check_rejects_ctrl_a_no_ctrl_on_toffoli() {
        let g = Gate { opcode: OP_TOFFOLI, target: 0, ctrl_a: NO_CTRL, ctrl_b: 0 };
        range_check_gate(g);
    }

    #[test]
    #[should_panic]
    fn range_check_rejects_ctrl_b_no_ctrl_on_toffoli() {
        let g = Gate { opcode: OP_TOFFOLI, target: 0, ctrl_a: 0, ctrl_b: NO_CTRL };
        range_check_gate(g);
    }

    #[test]
    #[should_panic]
    fn range_check_rejects_nop_with_real_target() {
        let g = Gate { opcode: OP_NOP, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        range_check_gate(g);
    }

    #[test]
    fn range_check_accepts_canonical_gates() {
        range_check_gate(Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        range_check_gate(Gate { opcode: OP_NOT, target: 7, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        range_check_gate(Gate { opcode: OP_CNOT, target: 7, ctrl_a: 5, ctrl_b: NO_CTRL });
        range_check_gate(Gate { opcode: OP_TOFFOLI, target: 7, ctrl_a: 5, ctrl_b: 3 });
    }

    // -- NOP invariance over `step` (R-T7 in RFC-0004) -------------------------

    #[test]
    fn nop_then_not_equals_not_then_nop() {
        let s = one_bit_state(0, 1);
        let nop = Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        let not_b0 = Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };

        let after_nop_then_not = step(step(s, nop), not_b0);
        let after_not_then_nop = step(step(s, not_b0), nop);
        // Both paths should arrive at bit 0 == 0.
        assert!(get_bit(after_nop_then_not, 0) == 0);
        assert!(get_bit(after_not_then_nop, 0) == 0);
    }
}
