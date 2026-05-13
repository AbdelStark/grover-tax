//! Stwo-side verifier shim.
//!
//! Contract (matches `bin/verify_stwo.sh` invocation):
//!
//!   stwo_verify --fixtures <fixtures_path> --proof <proof_path>
//!
//! Real Stwo verification is wired up in a follow-up PR. Today the shim:
//!
//!   * parses the two flags positionally,
//!   * loads the fixture JSON (must be valid JSON),
//!   * loads the proof file (must be non-empty and match the shim's
//!     stub-proof signature so the wrapper round-trips correctly),
//!   * exits 0 on agreement, 1 on rejection.
//!
//! Stdout is empty on success (RFC-0007 contract). Stderr carries the
//! diagnostic on failure.

use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

const STUB_PROOF_BYTES: &[u8] = b"stwo-stub-proof-v0.1\n";

#[derive(Debug)]
struct Args {
    fixtures_path: PathBuf,
    proof_path: PathBuf,
}

fn parse_args(mut argv: impl Iterator<Item = String>) -> Result<Args, String> {
    let _program = argv.next();
    let mut fixtures_path: Option<PathBuf> = None;
    let mut proof_path: Option<PathBuf> = None;
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--fixtures" => {
                fixtures_path = argv.next().map(PathBuf::from);
            }
            "--proof" => {
                proof_path = argv.next().map(PathBuf::from);
            }
            other => {
                return Err(format!("unknown flag: {other}"));
            }
        }
    }
    match (fixtures_path, proof_path) {
        (Some(f), Some(p)) => Ok(Args { fixtures_path: f, proof_path: p }),
        _ => Err(String::from(
            "usage: stwo_verify --fixtures <path> --proof <path>",
        )),
    }
}

fn run(args: &Args) -> Result<(), String> {
    let fixture_bytes = fs::read(&args.fixtures_path).map_err(|e| {
        format!("cannot read fixture {:?}: {e}", args.fixtures_path)
    })?;
    let _value: serde_json::Value = serde_json::from_slice(&fixture_bytes)
        .map_err(|e| format!("fixture not valid JSON: {e}"))?;

    let proof_bytes = fs::read(&args.proof_path)
        .map_err(|e| format!("cannot read proof {:?}: {e}", args.proof_path))?;
    if proof_bytes.is_empty() {
        return Err(String::from("PROVER.VERIFIER_REJECTED: proof is empty"));
    }
    if proof_bytes != STUB_PROOF_BYTES {
        // A real prover would compare against the deserialised proof structure.
        // The shim accepts only the matching stub signature.
        return Err(String::from(
            "PROVER.VERIFIER_REJECTED: proof bytes do not match stub signature",
        ));
    }
    Ok(())
}

fn main() -> ExitCode {
    let args = match parse_args(std::env::args()) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("MEASUREMENT.ENV_VAR_MISS: {e}");
            return ExitCode::from(2);
        }
    };
    match run(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("{e}");
            ExitCode::from(1)
        }
    }
}
