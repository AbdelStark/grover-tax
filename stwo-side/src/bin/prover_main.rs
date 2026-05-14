//! Stwo-side prover binary.
//!
//! Argv contract (matches `bin/run_stwo.sh`):
//!
//!   stwo_prove --fixtures <fixtures_path> --output <output_proof_path>
//!
//! Reads the v0.1 fixture, derives `log_n_rows` from
//! `circuit_byte_serialisation_hex` (rounded up to a power of two),
//! generates a wide-Fibonacci trace, runs Stwo's Circle-STARK prover
//! with a Blake2s channel, and writes the bincode-serialised proof to
//! `--output`. `CONSTRAINTS:` / `TRACE_ROWS:` lines on stdout satisfy
//! `scripts/wrapper_lib.sh::enforce_proverlog_grammar` (M7).
//!
//! The AIR is a constant-width Fibonacci of length `FIB_SEQUENCE_LENGTH`
//! repeated `2^log_n_rows` times. The point of the AIR isn't to model
//! point-addition (that's `python/grover_tax/sim_reference.py` and the
//! fixture's commitment) — it's to give Stwo work proportional to the
//! same `gate_count` the SP1 zkVM program walks, so the prover M1 wall
//! clocks are comparable.
//!
//! Exit codes (per `docs/spec/04-error-model.md`):
//!   0 — proof saved.
//!   1 — `PROVER.*` (witness rejected, prove failure).
//!   2 — `MEASUREMENT.*` per-wrapper (missing fixture, bad argv).

use itertools::Itertools;
use num_traits::One;
use serde::Deserialize;
use std::path::PathBuf;
use std::process::ExitCode;

use stwo::core::channel::Blake2sM31Channel;
use stwo::core::fields::m31::BaseField;
use stwo::core::fields::qm31::SecureField;
use stwo::core::pcs::PcsConfig;
use stwo::core::poly::circle::CanonicCoset;
use stwo::core::vcs_lifted::blake2_merkle::Blake2sM31MerkleChannel;
use stwo::prover::backend::simd::SimdBackend;
use stwo::prover::poly::circle::PolyOps;
use stwo::prover::{prove, CommitmentSchemeProver};
use stwo_constraint_framework::{
    EvalAtRow, FrameworkComponent, FrameworkEval, TraceLocationAllocator,
};

use stwo::core::ColumnVec;
use stwo::prover::backend::{Backend, Col, Column};
use stwo::prover::poly::circle::CircleEvaluation;
use stwo::prover::poly::BitReversedOrder;

const FIB_SEQUENCE_LENGTH: usize = 100;

#[derive(Deserialize)]
struct Fixture {
    n_samples: u64,
    circuit_byte_serialisation_hex: String,
}

fn parse_args() -> Result<(PathBuf, PathBuf), String> {
    let mut argv = std::env::args().skip(1);
    let mut fixtures: Option<PathBuf> = None;
    let mut output: Option<PathBuf> = None;
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--fixtures" => fixtures = argv.next().map(PathBuf::from),
            "--output" => output = argv.next().map(PathBuf::from),
            other => return Err(format!("MEASUREMENT.ENV_VAR_MISS: unknown flag: {other}")),
        }
    }
    match (fixtures, output) {
        (Some(f), Some(o)) => Ok((f, o)),
        _ => Err(String::from(
            "usage: stwo_prove --fixtures <path> --output <path>",
        )),
    }
}

pub struct FibInput {
    pub a: BaseField,
    pub b: BaseField,
}

fn generate_trace<const N: usize, B: Backend>(
    inputs: &[FibInput],
) -> ColumnVec<CircleEvaluation<B, BaseField, BitReversedOrder>> {
    assert!(inputs.len().is_power_of_two());
    let log_size = inputs.len().ilog2();
    let mut trace = (0..N)
        .map(|_| Col::<B, BaseField>::zeros(1 << log_size))
        .collect_vec();
    for (vec_index, input) in inputs.iter().enumerate() {
        let mut a = input.a;
        let mut b = input.b;
        trace[0].set(vec_index, a);
        trace[1].set(vec_index, b);
        trace.iter_mut().skip(2).for_each(|col| {
            (a, b) = (b, a * a + b * b);
            col.set(vec_index, b);
        });
    }
    let domain = CanonicCoset::new(log_size).circle_domain();
    trace
        .into_iter()
        .map(|eval| CircleEvaluation::<B, _, BitReversedOrder>::new(domain, eval))
        .collect_vec()
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

fn run(fixtures_path: PathBuf, output_path: PathBuf) -> Result<(), String> {
    let bytes = std::fs::read(&fixtures_path)
        .map_err(|e| format!("MEASUREMENT.ENV_VAR_MISS: cannot read fixture: {e}"))?;
    let fixture: Fixture = serde_json::from_slice(&bytes)
        .map_err(|e| format!("PROVER.WITNESS_REJECTED: fixture not valid JSON: {e}"))?;
    let circuit_bytes = hex::decode(&fixture.circuit_byte_serialisation_hex)
        .map_err(|e| format!("PROVER.WITNESS_REJECTED: invalid circuit hex: {e}"))?;

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

    // log_n_rows: smallest power-of-two ≥ gate_count, clamped to [4, 20].
    // Stwo needs log_n_rows ≥ 4 for FRI; clamp top end so the prover
    // wall-clock stays in the v0.1 budget.
    let log_n_rows: u32 = (gate_count.max(1).next_power_of_two().trailing_zeros() as u32)
        .clamp(4, 20);

    let inputs: Vec<FibInput> = (0..(1u64 << log_n_rows))
        .map(|i| FibInput {
            a: BaseField::one(),
            // Seed each row with the byte at `i % len`; gives the prover work
            // dependent on the fixture content rather than a constant.
            b: BaseField::from(
                circuit_bytes
                    .get((i as usize) % circuit_bytes.len())
                    .copied()
                    .unwrap_or(0) as u32,
            ),
        })
        .collect();

    let config = PcsConfig::default();
    let twiddles = SimdBackend::precompute_twiddles(
        CanonicCoset::new(log_n_rows + 1 + config.fri_config.log_blowup_factor)
            .circle_domain()
            .half_coset,
    );

    let prover_channel = &mut Blake2sM31Channel::default();
    let mut commitment_scheme =
        CommitmentSchemeProver::<SimdBackend, Blake2sM31MerkleChannel>::new(config, &twiddles);

    let mut tree_builder = commitment_scheme.tree_builder();
    tree_builder.extend_evals(vec![]);
    tree_builder.commit(prover_channel);

    let trace = generate_trace::<FIB_SEQUENCE_LENGTH, _>(&inputs);
    let mut tree_builder = commitment_scheme.tree_builder();
    tree_builder.extend_evals(trace);
    tree_builder.commit(prover_channel);

    let component = FrameworkComponent::<FibEval<FIB_SEQUENCE_LENGTH>>::new(
        &mut TraceLocationAllocator::default(),
        FibEval::<FIB_SEQUENCE_LENGTH> {
            log_n_rows,
        },
        SecureField::default(),
    );

    let proof = prove::<SimdBackend, Blake2sM31MerkleChannel>(
        &[&component],
        prover_channel,
        commitment_scheme,
    )
    .map_err(|e| format!("PROVER.WITNESS_REJECTED: stwo prove failed: {e:?}"))?;

    let serialized = bincode::serialize(&proof)
        .map_err(|e| format!("PROVER.WITNESS_REJECTED: cannot serialize proof: {e}"))?;
    std::fs::write(&output_path, serialized)
        .map_err(|e| format!("PROVER.WITNESS_REJECTED: cannot write proof: {e}"))?;

    // Wrapper-grammar lines: report the AIR's row count + constraint count.
    let constraints = (FIB_SEQUENCE_LENGTH - 2) as u64; // one per Fibonacci step
    let trace_rows = 1u64 << log_n_rows;
    println!("CONSTRAINTS: {constraints}");
    println!("TRACE_ROWS:  {trace_rows}");
    eprintln!(
        "stwo_prove: log_n_rows={log_n_rows} fib_len={FIB_SEQUENCE_LENGTH} n_samples={}",
        fixture.n_samples
    );

    Ok(())
}

fn main() -> ExitCode {
    let (fixtures_path, output_path) = match parse_args() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };
    match run(fixtures_path, output_path) {
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
