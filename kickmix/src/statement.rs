//! The Tier-2 kickmix proof statement (KB-12, #124).
//!
//! This is the computation the SP1 zkVM program executes — and a byte-faithful
//! equivalent of the upstream kickmix fuzzer, so the only delta between the two
//! stacks is the proving backend, not the program. It glues the three Tier-2
//! pieces together:
//!
//! 1. **Fiat-Shamir** (KB-9): derive `num_samples` register-input pairs from the
//!    circuit hash, so the prover cannot choose its inputs.
//! 2. **Simulation** (KB-8): for each derived `(x, y)`, run the kickmix circuit
//!    and check it computes the adder spec `((x + reps*y) mod 2^w, y)`, with
//!    ancillae cleared and the phase uninverted.
//! 3. **Resource certification** (KB-10): commit the circuit's resource counts
//!    (+ sentinel `42`) and assert they satisfy the demanded bounds.
//!
//! `run_statement` returns the committed public outputs on success — exactly
//! what the zkVM program commits and the verifier checks. The thin SP1
//! `#[no_main]` wrapper (stdin in, `commit` out, built on the reference rig) is
//! specified in `docs/spec/v0.3/SP1-KICKMIX-PROGRAM.md`; this module is the
//! portable, natively-tested core it calls.

use crate::fiat_shamir::derive_cases;
use crate::resource::{certify, count_resources, public_outputs, DemandedBounds, Violation};
use crate::{check_case, Circuit, FuzzCase, FuzzFailure, SplitMix64};

/// Parameters of the Tier-2 statement.
#[derive(Clone, Copy, Debug)]
pub struct StatementParams {
    /// Adder repetition count K: the circuit must be K copies of the base adder,
    /// computing `(x + K*y) mod 2^width`.
    pub repetitions: u128,
    /// Register width in bits (each of the two registers).
    pub width: u32,
    /// Number of Fiat-Shamir-derived fuzz cases to check.
    pub num_samples: usize,
    /// The resource bounds the verifier demands.
    pub demanded: DemandedBounds,
}

/// Why the statement did not hold.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StatementError {
    /// A Fiat-Shamir-derived fuzz case failed.
    FuzzFailed {
        case_index: usize,
        failure: FuzzFailure,
    },
    /// The circuit violated one or more demanded resource bounds.
    ResourceViolations(Vec<Violation>),
}

/// Seed a per-case measurement trajectory deterministically from the circuit
/// hash and the case index, so `HMR` circuits are reproducible and the
/// trajectory is itself a function of the circuit (not prover-chosen).
fn case_measure(circuit_hash: &[u8], index: usize) -> SplitMix64 {
    let mut seed: u64 = 0;
    for (i, &b) in circuit_hash.iter().take(8).enumerate() {
        seed |= (b as u64) << (8 * i);
    }
    SplitMix64::new(seed ^ (index as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15))
}

/// Execute the Tier-2 statement; return the committed public outputs
/// (`[num_samples, max_qubit_count, max_non_clifford_count,
/// max_circuit_instructions, 42]`) on success.
pub fn run_statement(
    circuit: &Circuit,
    circuit_hash: &[u8],
    params: StatementParams,
) -> Result<[u64; 5], StatementError> {
    let modulus = if params.width >= 128 {
        0u128
    } else {
        1u128 << params.width
    };
    let mask = modulus.wrapping_sub(1);

    let cases = derive_cases(circuit_hash, params.width, params.num_samples);
    for (i, &(x, y)) in cases.iter().enumerate() {
        // The adder spec: r0 := (x + K*y) mod 2^width, r1 := y (preserved).
        let acc = (x.wrapping_add(params.repetitions.wrapping_mul(y))) & mask;
        let case = FuzzCase {
            inputs: vec![x, y],
            outputs: vec![acc, y],
        };
        let mut measure = case_measure(circuit_hash, i);
        if let Some(failure) = check_case(circuit, &case, &mut measure) {
            return Err(StatementError::FuzzFailed {
                case_index: i,
                failure,
            });
        }
    }

    let counts = count_resources(circuit, params.num_samples as u64);
    let outputs = public_outputs(&counts);
    let violations = certify(&counts, outputs[4], &params.demanded);
    if !violations.is_empty() {
        return Err(StatementError::ResourceViolations(violations));
    }
    Ok(outputs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Circuit;

    fn example(name: &str) -> Circuit {
        let mut path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        path.pop();
        path.push("third_party/sp1/docs/example_data");
        path.push(name);
        Circuit::parse(&std::fs::read_to_string(&path).unwrap()).unwrap()
    }

    fn iadd64_demanded() -> DemandedBounds {
        DemandedBounds {
            num_samples: 128,
            max_qubit_count: 128,
            max_non_clifford_count: 125,
            max_circuit_instructions: 757,
        }
    }

    #[test]
    fn iadd64_statement_holds() {
        // The whole Tier-2 statement on the real adder: FS-derived inputs,
        // simulated, resource-certified — yields the upstream public outputs.
        let c = example("iadd64.kmx");
        let outputs = run_statement(
            &c,
            &[0xab; 32],
            StatementParams {
                repetitions: 1,
                width: 64,
                num_samples: 128,
                demanded: iadd64_demanded(),
            },
        )
        .unwrap();
        assert_eq!(outputs, [128, 128, 125, 757, 42]);
    }

    #[test]
    fn iadd8_statement_holds() {
        let c = example("iadd8.kmx");
        let outputs = run_statement(
            &c,
            &[0x01; 32],
            StatementParams {
                repetitions: 1,
                width: 8,
                num_samples: 256,
                demanded: DemandedBounds {
                    num_samples: 256,
                    max_qubit_count: 16,
                    max_non_clifford_count: 13,
                    max_circuit_instructions: 85, // 54 CX + 13 CCX + 16 APPEND + 2 REGISTER
                },
            },
        )
        .unwrap();
        assert_eq!(outputs, [256, 16, 13, 85, 42]);
    }

    #[test]
    fn broken_circuit_fails_the_statement() {
        // inc3_wrong_order does not compute the incrementer spec -> a FS-derived
        // case fails. (spec for inc3: r0 := (r0 + 1) mod 8, single register.)
        let c = example("inc3_wrong_order.kmx");
        let err = run_statement(
            &c,
            &[0x07; 32],
            StatementParams {
                repetitions: 1,
                width: 3,
                num_samples: 16,
                demanded: DemandedBounds {
                    num_samples: 16,
                    max_qubit_count: 3,
                    max_non_clifford_count: 1,
                    max_circuit_instructions: 6,
                },
            },
        )
        .unwrap_err();
        // inc3 is a single-register incrementer, not a two-register adder, so the
        // derived second operand drives a spec mismatch on the broken circuit.
        assert!(
            matches!(err, StatementError::FuzzFailed { .. }),
            "got {err:?}"
        );
    }

    #[test]
    fn over_tight_resource_bound_rejects() {
        let c = example("iadd64.kmx");
        let demanded = DemandedBounds {
            max_non_clifford_count: 100,
            ..iadd64_demanded()
        };
        let err = run_statement(
            &c,
            &[0xab; 32],
            StatementParams {
                repetitions: 1,
                width: 64,
                num_samples: 128,
                demanded,
            },
        )
        .unwrap_err();
        assert!(
            matches!(err, StatementError::ResourceViolations(_)),
            "got {err:?}"
        );
    }

    #[test]
    fn statement_is_deterministic() {
        let c = example("iadd64.kmx");
        let p = StatementParams {
            repetitions: 1,
            width: 64,
            num_samples: 64,
            demanded: iadd64_demanded(),
        };
        assert_eq!(
            run_statement(&c, &[0x55; 32], p),
            run_statement(&c, &[0x55; 32], p)
        );
    }
}
