//! grover-tax companion verifier for `stwo-run-and-prove`'s JSON proofs.
//!
//! The standalone `verify` binary shipped in our local `third_party/stwo-cairo/`
//! checkout is built against a different `stwo-cairo-prover` revision than
//! the crates.io `1.2.2` version `proving-utils` pins, which is why running
//! it on a proving-utils-generated proof fails with
//! "Proof of work verification failed".
//!
//! This binary lives inside `proving-utils` so it shares the same workspace
//! dependency graph (`cairo-air = "1.2.2"`) as `stwo-run-and-prove`, which
//! means the proof format and Fiat-Shamir derivation are guaranteed to
//! line up.

use std::path::PathBuf;

use anyhow::Result;
use cairo_air::utils::{deserialize_proof_from_file, ProofFormat};
use cairo_air::verifier::verify_cairo;
use cairo_air::CairoProofForRustVerifier;
use clap::Parser;
use stwo_cairo_prover::stwo::core::vcs_lifted::blake2_merkle::{
    Blake2sMerkleChannel, Blake2sMerkleHasher,
};

#[derive(Parser, Debug)]
#[command(about = "Verify a stwo-run-and-prove emitted Cairo proof.")]
struct Args {
    /// Path to the JSON/binary proof file emitted by stwo-run-and-prove.
    #[arg(long = "proof_path")]
    proof_path: PathBuf,

    /// Proof format. Must match what was used to produce the proof.
    #[arg(long = "proof_format", default_value = "json")]
    proof_format: String,
}

fn parse_format(s: &str) -> Result<ProofFormat> {
    match s.to_ascii_lowercase().as_str() {
        "json" => Ok(ProofFormat::Json),
        "binary" => Ok(ProofFormat::Binary),
        "cairo-serde" | "cairo_serde" => {
            anyhow::bail!("cairo-serde is one-way; the Rust verifier cannot read that format")
        }
        other => anyhow::bail!("unknown proof_format: {other}"),
    }
}

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let args = Args::parse();
    let fmt = parse_format(&args.proof_format)?;

    let proof: CairoProofForRustVerifier<Blake2sMerkleHasher> =
        deserialize_proof_from_file(&args.proof_path, fmt)?;

    verify_cairo::<Blake2sMerkleChannel>(proof)
        .map_err(|e| anyhow::anyhow!("verify_cairo rejected the proof: {e}"))?;

    Ok(())
}
