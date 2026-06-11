//! Resource-certification public outputs + verifier assertions (KB-10, #122).
//!
//! The reference benchmark's verifier doesn't only check that the circuit
//! passes its fuzz tests — it also asserts the circuit stays within *demanded
//! resource bounds*: it uses no more than Q qubits, executes no more than T
//! non-Clifford gates, contains no more than I instructions, and ran at least N
//! samples (`getting_started.md`, `verifier/verifier.rs`). Without this a prover
//! could pass a trivially-small or pathological circuit.
//!
//! This module computes those counts from a parsed [`Circuit`](crate::Circuit),
//! lays them out as ordered public outputs (with the upstream sentinel `42`),
//! and certifies them against the demanded bounds — mirroring
//! `example_zkp_verify`. The Cairo side (`stwo-side/cairo/src/kickmix.cairo`)
//! and the Python harness (`grover_tax.resource_cert`) implement the identical
//! comparison so a circuit is accepted/rejected the same way on both stacks.

use crate::{Circuit, Instruction};

/// The upstream sentinel committed alongside the resource counts.
pub const SENTINEL: u64 = 42;

/// The actual resource usage of a proven circuit (committed by the prover).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ResourceCounts {
    pub num_samples: u64,
    pub max_qubit_count: u64,
    pub max_non_clifford_count: u64,
    pub max_circuit_instructions: u64,
}

/// The bounds the verifier demands (carried in the fixture, KB-4).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DemandedBounds {
    pub num_samples: u64,
    pub max_qubit_count: u64,
    pub max_non_clifford_count: u64,
    pub max_circuit_instructions: u64,
}

/// A single failed certification check.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Violation {
    /// Fewer samples were run than demanded.
    TooFewSamples { committed: u64, demanded: u64 },
    /// The circuit used more qubits than the cap.
    QubitCapExceeded { committed: u64, demanded: u64 },
    /// The circuit used more non-Clifford gates than the cap.
    NonCliffordCapExceeded { committed: u64, demanded: u64 },
    /// The circuit contained more instructions than the cap.
    InstructionCapExceeded { committed: u64, demanded: u64 },
    /// The committed sentinel was not `42`.
    BadSentinel { committed: u64 },
}

/// `true` if an instruction is a non-Clifford gate (the doubly-controlled
/// `CCX`/`CCZ`, the T-count proxy the reference certifies).
fn is_non_clifford(inst: &Instruction) -> bool {
    inst.name == "CCX" || inst.name == "CCZ"
}

/// Count the resources of `circuit` given the `num_samples` it was fuzzed on.
pub fn count_resources(circuit: &Circuit, num_samples: u64) -> ResourceCounts {
    let non_clifford = circuit
        .instructions
        .iter()
        .filter(|i| is_non_clifford(i))
        .count();
    ResourceCounts {
        num_samples,
        max_qubit_count: circuit.num_qubits as u64,
        max_non_clifford_count: non_clifford as u64,
        max_circuit_instructions: circuit.instructions.len() as u64,
    }
}

/// The ordered public-output vector the prover commits: the circuit hash
/// (32 bytes, opaque here), the four counts, then the sentinel `42` — matching
/// the reference layout. Returns the five integer outputs; the hash is committed
/// separately by the prover and passed to [`certify`] as context.
pub fn public_outputs(counts: &ResourceCounts) -> [u64; 5] {
    [
        counts.num_samples,
        counts.max_qubit_count,
        counts.max_non_clifford_count,
        counts.max_circuit_instructions,
        SENTINEL,
    ]
}

/// Certify committed `counts` (with `sentinel`) against `demanded`.
///
/// `num_samples` must be **at least** demanded (`>=`); each resource count must
/// be **at most** demanded (`<=`); the sentinel must be `42`. Returns every
/// violation found (empty = accepted), mirroring `example_zkp_verify`.
pub fn certify(
    counts: &ResourceCounts,
    sentinel: u64,
    demanded: &DemandedBounds,
) -> Vec<Violation> {
    let mut v = Vec::new();
    if counts.num_samples < demanded.num_samples {
        v.push(Violation::TooFewSamples {
            committed: counts.num_samples,
            demanded: demanded.num_samples,
        });
    }
    if counts.max_qubit_count > demanded.max_qubit_count {
        v.push(Violation::QubitCapExceeded {
            committed: counts.max_qubit_count,
            demanded: demanded.max_qubit_count,
        });
    }
    if counts.max_non_clifford_count > demanded.max_non_clifford_count {
        v.push(Violation::NonCliffordCapExceeded {
            committed: counts.max_non_clifford_count,
            demanded: demanded.max_non_clifford_count,
        });
    }
    if counts.max_circuit_instructions > demanded.max_circuit_instructions {
        v.push(Violation::InstructionCapExceeded {
            committed: counts.max_circuit_instructions,
            demanded: demanded.max_circuit_instructions,
        });
    }
    if sentinel != SENTINEL {
        v.push(Violation::BadSentinel {
            committed: sentinel,
        });
    }
    v
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Circuit;

    fn iadd64() -> Circuit {
        let mut path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        path.pop();
        path.push("third_party/sp1/docs/example_data/iadd64.kmx");
        Circuit::parse(&std::fs::read_to_string(&path).unwrap()).unwrap()
    }

    #[test]
    fn counts_iadd64() {
        // The kickmix instruction count includes REGISTER/APPEND_TO_REGISTER
        // metadata: 502 CX + 125 CCX + 128 APPEND + 2 REGISTER = 757, matching
        // the upstream "iadd64: 757 ops, 128 qubits, 125 non-Clifford" figure.
        let c = iadd64();
        let counts = count_resources(&c, 128);
        assert_eq!(counts.num_samples, 128);
        assert_eq!(counts.max_qubit_count, 128);
        assert_eq!(counts.max_non_clifford_count, 125); // 125 CCX
        assert_eq!(counts.max_circuit_instructions, 757);
    }

    #[test]
    fn public_outputs_layout_with_sentinel() {
        let counts = count_resources(&iadd64(), 128);
        assert_eq!(public_outputs(&counts), [128, 128, 125, 757, 42]);
    }

    fn demanded() -> DemandedBounds {
        DemandedBounds {
            num_samples: 128,
            max_qubit_count: 128,
            max_non_clifford_count: 125,
            max_circuit_instructions: 757,
        }
    }

    #[test]
    fn conforming_circuit_passes() {
        let counts = count_resources(&iadd64(), 128);
        assert!(certify(&counts, SENTINEL, &demanded()).is_empty());
    }

    #[test]
    fn more_samples_than_demanded_passes() {
        let counts = count_resources(&iadd64(), 1000); // >= demanded
        assert!(certify(&counts, SENTINEL, &demanded()).is_empty());
    }

    #[test]
    fn too_few_samples_rejected() {
        let counts = count_resources(&iadd64(), 64); // < demanded 128
        let v = certify(&counts, SENTINEL, &demanded());
        assert!(matches!(v[0], Violation::TooFewSamples { .. }));
    }

    #[test]
    fn qubit_cap_exceeded_rejected() {
        let counts = count_resources(&iadd64(), 128);
        let d = DemandedBounds {
            max_qubit_count: 64,
            ..demanded()
        };
        let v = certify(&counts, SENTINEL, &d);
        assert!(v
            .iter()
            .any(|x| matches!(x, Violation::QubitCapExceeded { .. })));
    }

    #[test]
    fn non_clifford_cap_exceeded_rejected() {
        let counts = count_resources(&iadd64(), 128);
        let d = DemandedBounds {
            max_non_clifford_count: 100,
            ..demanded()
        };
        let v = certify(&counts, SENTINEL, &d);
        assert!(v
            .iter()
            .any(|x| matches!(x, Violation::NonCliffordCapExceeded { .. })));
    }

    #[test]
    fn instruction_cap_exceeded_rejected() {
        let counts = count_resources(&iadd64(), 128);
        let d = DemandedBounds {
            max_circuit_instructions: 700,
            ..demanded()
        };
        let v = certify(&counts, SENTINEL, &d);
        assert!(v
            .iter()
            .any(|x| matches!(x, Violation::InstructionCapExceeded { .. })));
    }

    #[test]
    fn bad_sentinel_rejected() {
        let counts = count_resources(&iadd64(), 128);
        let v = certify(&counts, 41, &demanded());
        assert!(v.iter().any(|x| matches!(x, Violation::BadSentinel { .. })));
    }
}
