//! Cairo unit-test suite C-T1..C-T8 per RFC-0004 §"Testing Strategy".
//!
//! Most C-T* bullets are individually covered by the unit tests in
//! `limbs`, `gates`, `serialise`, `commit`. This module is the *suite-level*
//! integration: each C-T appears here once, named C_T<n>, so the test
//! runner output makes the spec coverage obvious. Tests that need
//! cross-impl agreement (C-T6 / bit-layout interop with Python) live in
//! `python/tests/test_cairo_python_interop.py` (#18).

#[cfg(test)]
mod tests {
    use core::array::ArrayTrait;
    use grover_tax_circuit::Gate;
    use grover_tax_circuit::commit::commit_blake2s;
    use grover_tax_circuit::gates::step;
    use grover_tax_circuit::limbs::{
        State, assert_limb_in_range, assert_state_in_range, get_bit, set_bit, zero_state,
    };
    use grover_tax_circuit::serialise::{canonical_serialise, pad_to_pow2};
    use grover_tax_circuit::{NO_CTRL, OP_NOP, OP_NOT, OP_CNOT, OP_TOFFOLI};

    fn run_circuit(s: State, gates: @Array<Gate>) -> State {
        let mut current = s;
        let mut i: u32 = 0;
        let n = gates.len();
        loop {
            if i == n { break; }
            current = step(current, *gates.at(i));
            i = i + 1;
        };
        current
    }

    // -- C-T1: per-opcode semantics over the truth tables ---------------------
    //
    // Already exhaustively covered by `gates::tests::{nop_leaves_state_unchanged,
    // not_flips_target_*, cnot_truth_table, toffoli_truth_table}`. The suite-level
    // assertion below ties the bundle together so a single regression on any
    // opcode is reported at the C-T1 name.

    #[test]
    fn c_t1_opcode_table_sweep() {
        let s_zero = zero_state();
        let s_one = set_bit(zero_state(), 0, 1);

        // NOP — identity.
        let nop = Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        assert!(get_bit(step(s_one, nop), 0) == 1);

        // NOT — flip.
        let not_b0 = Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL };
        assert!(get_bit(step(s_zero, not_b0), 0) == 1);
        assert!(get_bit(step(s_one, not_b0), 0) == 0);

        // CNOT — XOR target with ctrl.
        let mut tcase = zero_state();
        tcase = set_bit(tcase, 0, 1); // ctrl
        tcase = set_bit(tcase, 8, 0); // target
        let cnot = Gate { opcode: OP_CNOT, target: 8, ctrl_a: 0, ctrl_b: NO_CTRL };
        assert!(get_bit(step(tcase, cnot), 8) == 1);

        // TOFFOLI — XOR target with (a AND b).
        let mut tt = zero_state();
        tt = set_bit(tt, 0, 1);  // ctrl_a
        tt = set_bit(tt, 8, 1);  // ctrl_b
        tt = set_bit(tt, 16, 0); // target
        let toff = Gate { opcode: OP_TOFFOLI, target: 16, ctrl_a: 0, ctrl_b: 8 };
        assert!(get_bit(step(tt, toff), 16) == 1);
    }

    // -- C-T2: limb arithmetic ------------------------------------------------
    //
    // Range-check primitives + bit-level read/write across all 256 positions
    // are exhaustively covered in `limbs::tests`. This suite-level check
    // exercises the round-trip path one more time so the C-T2 name appears
    // in the runner output.

    #[test]
    fn c_t2_limb_arithmetic_round_trip() {
        let mut s = zero_state();
        s = set_bit(s, 0, 1);
        s = set_bit(s, 30, 1);  // last bit of limb 0
        s = set_bit(s, 31, 1);  // first bit of limb 1
        s = set_bit(s, 255, 1); // last bit of state
        assert!(get_bit(s, 0) == 1);
        assert!(get_bit(s, 30) == 1);
        assert!(get_bit(s, 31) == 1);
        assert!(get_bit(s, 255) == 1);
        // Range check still passes.
        assert_state_in_range(s);
        assert_limb_in_range(0x7FFFFFFF_u32);
    }

    // -- C-T3: hand-crafted small C over 4 (x, y) pairs -----------------------
    //
    // A 16-gate circuit that performs the deterministic transformation
    // "flip bit 0, copy bit 0 → bit 1, AND-fold bit 0 and bit 1 into bit 2".
    // Verified over all 4 starting bit-0 / bit-1 input combinations.

    fn build_small_circuit_16_gates() -> Array<Gate> {
        let mut g = ArrayTrait::<Gate>::new();
        // Step 1: NOT bit 0.
        g.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        // Step 2: CNOT bit 0 -> bit 1 (so bit 1 becomes initial-bit-1 XOR bit 0).
        g.append(Gate { opcode: OP_CNOT, target: 1, ctrl_a: 0, ctrl_b: NO_CTRL });
        // Step 3: TOFFOLI(bit 0, bit 1) -> bit 2.
        g.append(Gate { opcode: OP_TOFFOLI, target: 2, ctrl_a: 0, ctrl_b: 1 });
        // Steps 4-16: 13 NOPs (state unchanged). Brings the circuit to 16
        // gates total without touching state.
        let mut k: u32 = 0;
        loop {
            if k == 13 { break; }
            g.append(Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
            k = k + 1;
        };
        g
    }

    #[test]
    fn c_t3_hand_crafted_circuit_known_outputs() {
        let circuit = build_small_circuit_16_gates();

        // Compute expected outputs (b0, b1, b2) for each starting (b0_in, b1_in):
        //   b0_out = NOT b0_in
        //   b1_out = b1_in XOR b0_out = b1_in XOR (NOT b0_in)
        //   b2_out = b0_out AND b1_out
        let cases: Array<(u32, u32)> = ArrayTrait::new();
        let mut starts: Array<(u32, u32)> = ArrayTrait::new();
        starts.append((0, 0));
        starts.append((0, 1));
        starts.append((1, 0));
        starts.append((1, 1));
        let _ = cases;

        let mut i: u32 = 0;
        loop {
            if i == starts.len() { break; }
            let (b0_in, b1_in) = *starts.at(i);
            let mut s = zero_state();
            s = set_bit(s, 0, b0_in);
            s = set_bit(s, 1, b1_in);
            let out = run_circuit(s, @circuit);

            let b0_out = 1 - b0_in;        // NOT
            let b1_out = (b1_in + b0_out) % 2; // XOR
            let b2_out = b0_out * b1_out;  // AND (each is 0/1)
            assert!(get_bit(out, 0) == b0_out);
            assert!(get_bit(out, 1) == b1_out);
            assert!(get_bit(out, 2) == b2_out);
            i = i + 1;
        };
    }

    // -- C-T4: canonical-serialisation byte-equality (cross-impl regression) --
    //
    // The exact 4-gate vector pinned by Python's `test_regression_vector_four_gates`
    // (#11). `serialise::tests::serialise_four_gate_regression_vector` already
    // performs the byte-by-byte check; this is the suite-level entry that
    // names it C_T4 so the runner output makes coverage obvious.

    #[test]
    fn c_t4_canonical_serialisation_regression() {
        let mut g = ArrayTrait::<Gate>::new();
        g.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_CNOT, target: 1, ctrl_a: 0, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_TOFFOLI, target: 2, ctrl_a: 0, ctrl_b: 1 });
        g.append(Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        let bytes = canonical_serialise(@g);
        // 8-byte header + 4 gates × 8 bytes/gate = 40 bytes.
        assert!(bytes.len() == 40_u32);
        // First byte must be 'G' (magic[0]); last byte must be 0xFF (NOP ctrl_b high).
        assert!(*bytes.at(0) == 'G');
        assert!(*bytes.at(39) == 0xFF_u8);
    }

    // -- C-T5: Blake2s test vector --------------------------------------------
    //
    // `commit::tests::three_byte_input_matches_python` exercises this for
    // `b"abc"`; the suite-level entry repeats one byte-level assertion so
    // the runner output names C-T5 explicitly.

    #[test]
    fn c_t5_blake2s_abc_vector() {
        let mut bytes = ArrayTrait::<u8>::new();
        bytes.append('a');
        bytes.append('b');
        bytes.append('c');
        let [w0, _, _, _, _, _, _, _] = commit_blake2s(@bytes);
        // First word matches Python.
        assert!(w0 == 0x8c5e8c50_u32);
    }

    // -- C-T6: bit-layout interop with Python (placeholder) --------------------
    //
    // The actual cross-impl test lives on the Python side (`#18`): given the
    // same input bytes, Python's `grover_tax.sim_reference.BitVector` and
    // Cairo's `State` produce identical bit-by-bit decodings. The Cairo-side
    // structural guarantee — bit `i` lives at limb `i/31`, position `i%31`,
    // LSB-first — is exercised by `set_then_get_round_trip_for_every_position`
    // in `limbs::tests`. This entry names C_T6 in the runner output as a
    // pointer to that Python-side test.

    #[test]
    fn c_t6_bit_layout_pointer() {
        // A token assertion that exercises the same `(limb_idx, bit_in_limb)`
        // decomposition the Python BitVector uses on the same input shape.
        let s = set_bit(zero_state(), 100, 1);
        assert!(get_bit(s, 100) == 1);
        assert!(get_bit(s, 99) == 0);
        assert!(get_bit(s, 101) == 0);
    }

    // -- C-T7: NOP no-op invariance ------------------------------------------
    //
    // Inserting a NOP gate anywhere in a circuit does not change the final
    // state. Exercised by running a small circuit with and without an
    // inserted NOP and comparing the final states.

    #[test]
    fn c_t7_nop_invariance() {
        let mut g_without: Array<Gate> = ArrayTrait::new();
        g_without.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g_without.append(Gate { opcode: OP_NOT, target: 1, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });

        let mut g_with: Array<Gate> = ArrayTrait::new();
        g_with.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g_with.append(Gate { opcode: OP_NOP, target: NO_CTRL, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g_with.append(Gate { opcode: OP_NOT, target: 1, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });

        let s0 = zero_state();
        let without = run_circuit(s0, @g_without);
        let with = run_circuit(s0, @g_with);
        // Both should have bit 0 = 1 and bit 1 = 1; all other bits 0.
        assert!(get_bit(without, 0) == 1);
        assert!(get_bit(with, 0) == 1);
        assert!(get_bit(without, 1) == 1);
        assert!(get_bit(with, 1) == 1);
        let mut i: u32 = 2;
        loop {
            if i == 32 { break; }
            assert!(get_bit(without, i) == get_bit(with, i));
            i = i + 1;
        };
    }

    // -- C-T8: padding correctness --------------------------------------------
    //
    // |C|_original and |C|_padded produce identical final states. The
    // padding NOPs by construction have no effect; this is the
    // observation-preservation guarantee that lets the verifier accept
    // either form.

    #[test]
    fn c_t8_padding_preserves_final_state() {
        let mut g: Array<Gate> = ArrayTrait::new();
        g.append(Gate { opcode: OP_NOT, target: 0, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_NOT, target: 1, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });
        g.append(Gate { opcode: OP_NOT, target: 2, ctrl_a: NO_CTRL, ctrl_b: NO_CTRL });

        let padded = pad_to_pow2(@g);
        assert!(padded.len() == 4); // next power of two

        let s0 = zero_state();
        let unpadded_out = run_circuit(s0, @g);
        let padded_out = run_circuit(s0, @padded);

        let mut i: u32 = 0;
        loop {
            if i == 32 { break; }
            assert!(get_bit(unpadded_out, i) == get_bit(padded_out, i));
            i = i + 1;
        };
    }
}
