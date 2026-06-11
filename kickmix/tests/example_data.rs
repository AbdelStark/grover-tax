//! Acceptance tests for the kickmix simulator (KB-8, #120): reproduce upstream
//! `example_sample` / `example_fuzz` behaviour on every `docs/example_data`
//! circuit, including the `inc3_wrong_*` rejection cases.

use std::path::PathBuf;

use kickmix::{
    check_case, fuzz, load_register, read_register, run, Circuit, FuzzCase, FuzzFailure,
    SplitMix64, State,
};

fn example(name: &str) -> Circuit {
    // tests/ -> kickmix/ -> repo root.
    let mut path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    path.pop();
    path.push("third_party/sp1/docs/example_data");
    path.push(name);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {path:?}: {e}"));
    Circuit::parse(&text).unwrap_or_else(|e| panic!("parse {name}: {e}"))
}

/// Mirror `example_sample`: load registers in id order, run once, read back.
fn sample(circuit: &Circuit, values: &[u128]) -> Vec<u128> {
    let mut state = State::new(circuit.num_qubits, circuit.num_bits);
    for (i, &reg) in circuit.registers.keys().enumerate() {
        load_register(&mut state, circuit, reg, values[i]);
    }
    let mut measure = SplitMix64::new(0);
    run(circuit, &mut state, &mut measure);
    circuit
        .registers
        .keys()
        .map(|&reg| read_register(&state, circuit, reg))
        .collect()
}

// -- parsing ----------------------------------------------------------------

#[test]
fn iadd64_parses_to_expected_shape() {
    let c = example("iadd64.kmx");
    assert_eq!(c.num_qubits, 128);
    assert_eq!(c.registers[&0], (0..64).collect::<Vec<_>>());
    assert_eq!(c.registers[&1], (64..128).collect::<Vec<_>>());
    let ccx = c.instructions.iter().filter(|i| i.name == "CCX").count();
    let cx = c.instructions.iter().filter(|i| i.name == "CX").count();
    assert_eq!((cx, ccx), (502, 125));
}

#[test]
fn all_example_circuits_parse() {
    for name in [
        "inc3.kmx",
        "iadd8.kmx",
        "iadd64.kmx",
        "iadd8_with_ancillae.kmx",
        "iadd8_with_classical_offset_and_dirty_ancillae.kmx",
        "table_lookup_3x3.kmx",
        "inc3_wrong_order.kmx",
        "inc3_wrong_garbage.kmx",
        "inc3_wrong_phase.kmx",
    ] {
        let _ = example(name);
    }
}

// -- example_sample parity --------------------------------------------------

#[test]
fn sample_inc3_increments() {
    let c = example("inc3.kmx");
    for v in 0..8u128 {
        assert_eq!(sample(&c, &[v]), vec![(v + 1) % 8]);
    }
}

#[test]
fn sample_iadd64_getting_started() {
    // getting_started.md: `iadd64 101 123` -> `224 123`.
    let c = example("iadd64.kmx");
    assert_eq!(sample(&c, &[101, 123]), vec![224, 123]);
}

#[test]
fn sample_iadd8_wraps_mod_256() {
    let c = example("iadd8.kmx");
    assert_eq!(sample(&c, &[200, 100]), vec![44, 100]); // (200+100)%256 = 44
    assert_eq!(sample(&c, &[1, 10]), vec![11, 10]);
}

// -- example_fuzz parity: correct circuits PASS -----------------------------

fn adder_cases(width: u32, n: usize, seed: u64) -> Vec<FuzzCase> {
    let mut rng = SplitMix64::new(seed);
    let modulus = 1u128 << width;
    let mask = modulus - 1;
    // Two width-bit operands per case, drawn from the PRNG.
    (0..n)
        .map(|_| {
            let x = next_u128(&mut rng) & mask;
            let y = next_u128(&mut rng) & mask;
            FuzzCase {
                inputs: vec![x, y],
                outputs: vec![(x + y) % modulus, y],
            }
        })
        .collect()
}

fn next_u128(rng: &mut SplitMix64) -> u128 {
    use kickmix::MeasureSource;
    // Assemble 128 bits from the bit source for a uniform-ish operand.
    let mut v: u128 = 0;
    for _ in 0..128 {
        v = (v << 1) | (rng.next_bit() as u128);
    }
    v
}

#[test]
fn fuzz_iadd64_passes() {
    let c = example("iadd64.kmx");
    let cases = adder_cases(64, 200, 0xA11CE);
    assert!(fuzz(&c, &cases, 1, 1).is_ok());
}

#[test]
fn fuzz_iadd8_passes() {
    let c = example("iadd8.kmx");
    let cases = adder_cases(8, 256, 7);
    assert!(fuzz(&c, &cases, 1, 1).is_ok());
}

#[test]
fn fuzz_inc3_passes() {
    let c = example("inc3.kmx");
    let cases: Vec<FuzzCase> = (0..8u128)
        .map(|v| FuzzCase {
            inputs: vec![v],
            outputs: vec![(v + 1) % 8],
        })
        .collect();
    assert!(fuzz(&c, &cases, 1, 1).is_ok());
}

#[test]
fn fuzz_iadd8_with_ancillae_passes() {
    // The HMR/phase-kickback adder must pass over many trajectories — this is
    // the whole point of the full simulator (R/HMR/CZ phase handling).
    let c = example("iadd8_with_ancillae.kmx");
    let cases = adder_cases(8, 64, 3);
    assert!(
        fuzz(&c, &cases, 32, 0xF00D).is_ok(),
        "correct ancilla adder should pass fuzzing"
    );
}

// -- example_fuzz parity: broken circuits FAIL ------------------------------

#[test]
fn fuzz_inc3_wrong_order_fails_on_output() {
    let c = example("inc3_wrong_order.kmx");
    let cases: Vec<FuzzCase> = (0..8u128)
        .map(|v| FuzzCase {
            inputs: vec![v],
            outputs: vec![(v + 1) % 8],
        })
        .collect();
    let err = fuzz(&c, &cases, 1, 1).unwrap_err();
    assert!(
        matches!(err.1, FuzzFailure::WrongOutput { .. }),
        "got {:?}",
        err.1
    );
}

#[test]
fn fuzz_inc3_wrong_garbage_fails_on_ancilla() {
    let c = example("inc3_wrong_garbage.kmx");
    // Pick an input that actually dirties the ancilla (q0 ON -> CX q0 q3).
    let cases = vec![FuzzCase {
        inputs: vec![1],
        outputs: vec![2],
    }];
    let err = fuzz(&c, &cases, 1, 1).unwrap_err();
    assert!(
        matches!(err.1, FuzzFailure::UnclearedAncilla { .. }),
        "got {:?}",
        err.1
    );
}

#[test]
fn fuzz_inc3_wrong_phase_fails_probabilistically() {
    // The wrong phase correction leaves the phase inverted on ~half the
    // trajectories where q3 was measured ON; many shots make detection certain.
    let c = example("inc3_wrong_phase.kmx");
    let cases: Vec<FuzzCase> = (0..8u128)
        .map(|v| FuzzCase {
            inputs: vec![v],
            outputs: vec![(v + 1) % 8],
        })
        .collect();
    let err = fuzz(&c, &cases, 200, 0xDEAD).unwrap_err();
    assert!(
        matches!(
            err.1,
            FuzzFailure::InvertedPhase | FuzzFailure::UnclearedAncilla { .. }
        ),
        "got {:?}",
        err.1
    );
}

// -- determinism ------------------------------------------------------------

#[test]
fn check_case_is_deterministic_given_measure_stream() {
    let c = example("iadd8_with_ancillae.kmx");
    let case = FuzzCase {
        inputs: vec![100, 50],
        outputs: vec![150, 50],
    };
    let a = {
        let mut m = SplitMix64::new(42);
        check_case(&c, &case, &mut m)
    };
    let b = {
        let mut m = SplitMix64::new(42);
        check_case(&c, &case, &mut m)
    };
    assert_eq!(a, b);
}
