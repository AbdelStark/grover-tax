//! Stwo-side verifier binary.
//!
//! Argv contract (matches `bin/verify_stwo.sh`):
//!
//!   stwo_verify --fixtures <fixtures_path> --proof <proof_path>
//!
//! Loads the bincode-serialised Stwo proof, recomputes `log_n_rows` from
//! the fixture, sets up the matching `CommitmentSchemeVerifier`, and
//! runs the Circle-STARK verifier with a Blake2s channel.
//!
//! Exit codes:
//!   0 — proof verified.
//!   1 — `PROVER.VERIFIER_REJECTED`.
//!   2 — `MEASUREMENT.*` (missing file, bad argv).

use serde::Deserialize;
use std::path::PathBuf;
use std::process::ExitCode;

use stwo::core::air::Component;
use stwo::core::channel::Blake2sM31Channel;
use stwo::core::fields::qm31::SecureField;
use stwo::core::pcs::{CommitmentSchemeVerifier, PcsConfig};
use stwo::core::vcs_lifted::blake2_merkle::Blake2sM31MerkleChannel;
use stwo::core::verifier::verify;
use stwo::prover::backend::simd::SimdBackend;
use stwo_constraint_framework::{
    EvalAtRow, FrameworkComponent, FrameworkEval, TraceLocationAllocator,
};

const FIB_SEQUENCE_LENGTH: usize = 100;

#[derive(Deserialize)]
struct Fixture {
    circuit_byte_serialisation_hex: String,
}

fn parse_args() -> Result<(PathBuf, PathBuf), String> {
    let mut argv = std::env::args().skip(1);
    let mut fixtures: Option<PathBuf> = None;
    let mut proof: Option<PathBuf> = None;
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--fixtures" => fixtures = argv.next().map(PathBuf::from),
            "--proof" => proof = argv.next().map(PathBuf::from),
            other => return Err(format!("MEASUREMENT.ENV_VAR_MISS: unknown flag: {other}")),
        }
    }
    match (fixtures, proof) {
        (Some(f), Some(p)) => Ok((f, p)),
        _ => Err(String::from(
            "usage: stwo_verify --fixtures <path> --proof <path>",
        )),
    }
}

#[derive(Clone)]
pub struct FibEval<const N: usize> {
    pub log_n_rows: u32,
}

impl<const N: usize> FrameworkEval for FibEval<N> {
    fn log_size(&self) -> u32 {
        self.log_n_rows
    }
    fn max_constraint_log_degree_bound(&self) -> u32 {
        self.log_n_rows + 1
    }
    fn evaluate<E: EvalAtRow>(&self, mut eval: E) -> E {
        let mut a = eval.next_trace_mask();
        let mut b = eval.next_trace_mask();
        for _ in 2..N {
            let c = eval.next_trace_mask();
            let a_sq = a.clone() * a.clone();
            let b_sq = b.clone() * b.clone();
            eval.add_constraint(c.clone() - (a_sq + b_sq));
            a = b;
            b = c;
        }
        eval
    }
}

fn run(fixtures_path: PathBuf, proof_path: PathBuf) -> Result<(), String> {
    let bytes = std::fs::read(&fixtures_path)
        .map_err(|e| format!("MEASUREMENT.ENV_VAR_MISS: cannot read fixture: {e}"))?;
    let fixture: Fixture = serde_json::from_slice(&bytes)
        .map_err(|e| format!("PROVER.VERIFIER_REJECTED: fixture not valid JSON: {e}"))?;
    let circuit_bytes = hex::decode(&fixture.circuit_byte_serialisation_hex)
        .map_err(|e| format!("PROVER.VERIFIER_REJECTED: invalid circuit hex: {e}"))?;

    let gate_count: u64 = if circuit_bytes.len() >= 8 {
        u32::from_le_bytes([
            circuit_bytes[4],
            circuit_bytes[5],
            circuit_bytes[6],
            circuit_bytes[7],
        ]) as u64
    } else {
        0
    };
    let log_n_rows: u32 = (gate_count.max(1).next_power_of_two().trailing_zeros() as u32)
        .clamp(4, 20);

    let proof_bytes = std::fs::read(&proof_path)
        .map_err(|e| format!("MEASUREMENT.ENV_VAR_MISS: cannot read proof: {e}"))?;
    let proof: stwo::core::proof::StarkProof<
        stwo::core::vcs_lifted::blake2_merkle::Blake2sM31MerkleHasher,
    > = bincode::deserialize(&proof_bytes)
        .map_err(|e| format!("PROVER.VERIFIER_REJECTED: cannot deserialise proof: {e}"))?;

    let config = PcsConfig::default();
    let verifier_channel = &mut Blake2sM31Channel::default();
    let commitment_scheme =
        &mut CommitmentSchemeVerifier::<Blake2sM31MerkleChannel>::new(config);

    let component = FrameworkComponent::<FibEval<FIB_SEQUENCE_LENGTH>>::new(
        &mut TraceLocationAllocator::default(),
        FibEval::<FIB_SEQUENCE_LENGTH> { log_n_rows },
        SecureField::default(),
    );

    let sizes = component.trace_log_degree_bounds();
    commitment_scheme.commit(proof.commitments[0], &sizes[0], verifier_channel);
    commitment_scheme.commit(proof.commitments[1], &sizes[1], verifier_channel);
    verify(&[&component], verifier_channel, commitment_scheme, proof)
        .map_err(|e| format!("PROVER.VERIFIER_REJECTED: stwo verify failed: {e:?}"))?;

    Ok(())
}

fn main() -> ExitCode {
    let (fixtures_path, proof_path) = match parse_args() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };
    // Suppress unused warning from `SimdBackend` import (kept for symmetry with prover).
    let _ = std::marker::PhantomData::<SimdBackend>;
    match run(fixtures_path, proof_path) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("{e}");
            if e.starts_with("MEASUREMENT.") {
                ExitCode::from(2)
            } else {
                ExitCode::from(1)
            }
        }
    }
}
