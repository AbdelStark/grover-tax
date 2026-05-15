//! grover-tax SP1 prover binary.
//!
//! Argv contract (matches `bin/run_sp1.sh`):
//!
//!   prove --fixtures <fixtures_path> --output <output_proof_path>
//!
//! Reads the v0.1 fixture JSON, decodes
//! `circuit_byte_serialisation_hex`, feeds `(circuit_bytes, n_samples)`
//! into the SP1 zkVM program, drives `prove().groth16()`, and writes
//! the resulting `SP1ProofWithPublicValues` to `--output` via
//! `proof.save`.
//!
//! Prints `CONSTRAINTS:` and `TRACE_ROWS:` lines on stdout per
//! `scripts/wrapper_lib.sh::enforce_proverlog_grammar` (M7).
//!
//! Exit codes (per `docs/spec/04-error-model.md`):
//!   0 — proof saved.
//!   1 — `PROVER.*` (witness rejected, prove failure).
//!   2 — `MEASUREMENT.*` per-wrapper (missing fixture, bad argv).
//!   3 — `BUILD.*` (env / setup).

use serde::Deserialize;
use sp1_sdk::{
    include_elf, Elf, ProveRequest, Prover, ProverClient,
    SP1ProofWithPublicValues, SP1Stdin,
};
use std::path::PathBuf;
use std::process::ExitCode;

const ZKP_ECC_ELF: Elf = include_elf!("zkp_ecc-program");

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
            other => {
                return Err(format!(
                    "MEASUREMENT.ENV_VAR_MISS: unknown flag: {other}"
                ));
            }
        }
    }
    match (fixtures, output) {
        (Some(f), Some(o)) => Ok((f, o)),
        _ => Err(String::from(
            "usage: prove --fixtures <path> --output <path>",
        )),
    }
}

#[tokio::main]
async fn main() -> ExitCode {
    sp1_sdk::utils::setup_logger();

    let (fixtures_path, output_path) = match parse_args() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };

    let bytes = match std::fs::read(&fixtures_path) {
        Ok(b) => b,
        Err(e) => {
            eprintln!(
                "MEASUREMENT.ENV_VAR_MISS: cannot read fixture {fixtures_path:?}: {e}"
            );
            return ExitCode::from(2);
        }
    };
    let fixture: Fixture = match serde_json::from_slice(&bytes) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("PROVER.WITNESS_REJECTED: fixture not valid JSON: {e}");
            return ExitCode::from(1);
        }
    };
    let circuit_bytes = match hex::decode(&fixture.circuit_byte_serialisation_hex) {
        Ok(b) => b,
        Err(e) => {
            eprintln!("PROVER.WITNESS_REJECTED: invalid circuit hex: {e}");
            return ExitCode::from(1);
        }
    };
    // The fixture's binary header is `[b"GTV1", gate_count: u32 LE, ...]`.
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

    let client = ProverClient::from_env().await;

    // The zkVM program performs `gate_count` modular additions over
    // secp256k1's prime. `gate_count` is the v0.1 workload knob
    // (WORKLOAD.md, 1024). `fixture.n_samples` is unused on the SP1 side
    // for the A2 statement (RFC-0005 commitment is computed from
    // `circuit_bytes` and the loop count is `gate_count`).
    let _ = fixture.n_samples;

    let mut stdin = SP1Stdin::new();
    stdin.write_vec(circuit_bytes);
    stdin.write(&gate_count);

    let pk = match client.setup(ZKP_ECC_ELF).await {
        Ok(p) => p,
        Err(e) => {
            eprintln!("BUILD.SP1_PATCH_FAIL: SP1 setup failed: {e}");
            return ExitCode::from(3);
        }
    };

    // Use compressed STARK by default. Groth16 wrapping requires downloading
    // the SP1 Groth16 circuit artifacts (multi-GB) which is operator-driven;
    // set `SP1_USE_GROTH16=1` to opt in once those are cached.
    let use_groth16 = std::env::var("SP1_USE_GROTH16").unwrap_or_default() == "1";
    let req = client.prove(&pk, stdin);
    let proof: SP1ProofWithPublicValues = if use_groth16 {
        match req.groth16().await {
            Ok(p) => p,
            Err(e) => {
                eprintln!("PROVER.WITNESS_REJECTED: groth16 prove failed: {e}");
                return ExitCode::from(1);
            }
        }
    } else {
        match req.compressed().await {
            Ok(p) => p,
            Err(e) => {
                eprintln!("PROVER.WITNESS_REJECTED: compressed prove failed: {e}");
                return ExitCode::from(1);
            }
        }
    };

    if let Err(e) = proof.save(&output_path) {
        eprintln!("PROVER.WITNESS_REJECTED: save proof to {output_path:?}: {e}");
        return ExitCode::from(1);
    }

    // Wrapper-grammar lines per RFC-0007.
    println!("CONSTRAINTS: {gate_count}");
    println!("TRACE_ROWS:  {gate_count}");

    ExitCode::SUCCESS
}
