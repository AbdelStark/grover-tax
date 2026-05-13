//! Stwo-side prover shim.
//!
//! Contract (matches `bin/run_stwo.sh` invocation):
//!
//!   stwo_prove --fixtures <fixtures_path> --output <output_proof_path>
//!
//! Real Stwo proving is wired up in a follow-up PR (depends on the
//! `stwo-prover` dependency landing in `versions.lock`). Today this is a
//! shim that:
//!
//!   * parses the two flags positionally,
//!   * loads the fixture JSON (verifies it's at least valid JSON),
//!   * emits the M7 grammar lines (`CONSTRAINTS:` / `TRACE_ROWS:`) so
//!     `scripts/wrapper_lib.sh::enforce_proverlog_grammar` accepts the
//!     output,
//!   * writes a marker file at `--output` (non-empty, so the wrapper's
//!     `[[ ! -s "${TMP_PROOF}" ]]` check passes),
//!   * exits 0.
//!
//! The shim keeps the wrapper integration testable end-to-end and the
//! grammar contract honest. A measured run of course requires the real
//! prover; that wiring lives with #20..#24 (Cairo circuit) and a
//! follow-up Rust patch that swaps the stub body for a `stwo_prover`
//! invocation.

use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

const STUB_PROOF_BYTES: &[u8] = b"stwo-stub-proof-v0.1\n";

#[derive(Debug)]
struct Args {
    fixtures_path: PathBuf,
    output_path: PathBuf,
}

fn parse_args(mut argv: impl Iterator<Item = String>) -> Result<Args, String> {
    let _program = argv.next();
    let mut fixtures_path: Option<PathBuf> = None;
    let mut output_path: Option<PathBuf> = None;
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--fixtures" => {
                fixtures_path = argv.next().map(PathBuf::from);
            }
            "--output" => {
                output_path = argv.next().map(PathBuf::from);
            }
            other => {
                return Err(format!("unknown flag: {other}"));
            }
        }
    }
    match (fixtures_path, output_path) {
        (Some(f), Some(o)) => Ok(Args { fixtures_path: f, output_path: o }),
        _ => Err(String::from(
            "usage: stwo_prove --fixtures <path> --output <path>",
        )),
    }
}

fn run(args: &Args) -> Result<(), String> {
    let fixture_bytes = fs::read(&args.fixtures_path).map_err(|e| {
        format!("BUILD.STWO_SHA_DRIFT: cannot read fixture {:?}: {e}", args.fixtures_path)
    })?;

    // Cheap shape check: must be valid JSON. The full schema validation lives
    // on the Python side (`grover_tax.validate_schemas`).
    let _value: serde_json::Value = serde_json::from_slice(&fixture_bytes).map_err(|e| {
        format!("PROVER.WITNESS_REJECTED: fixture not valid JSON: {e}")
    })?;

    // M7 grammar lines — required by `wrapper_lib.sh::enforce_proverlog_grammar`.
    // The integers are placeholders until the real Stwo integration emits the
    // honest constraint and trace-row counts.
    println!("CONSTRAINTS: 0");
    println!("TRACE_ROWS:  0");

    fs::write(&args.output_path, STUB_PROOF_BYTES).map_err(|e| {
        format!("PROVER.WITNESS_REJECTED: cannot write proof to {:?}: {e}", args.output_path)
    })?;
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
            if e.starts_with("BUILD.") {
                ExitCode::from(3)
            } else {
                ExitCode::from(1)
            }
        }
    }
}
