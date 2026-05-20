//! grover-tax SP1 verifier binary (v0.2: gate-execution circuit).
//!
//! Argv contract (matches `bin/verify_sp1.sh`):
//!
//!   verifier --fixtures <fixtures_path> --proof <proof_path>
//!
//! Loads the saved `SP1ProofWithPublicValues`, derives the verifying key
//! (from cache if `SP1_VK_CACHE` env var is set and the file exists;
//! otherwise via `setup(ZKP_ECC_ELF)`), asks `ProverClient::verify` to
//! check the proof, and reads back the public values committed by the
//! v0.2 zkVM program (`third_party/sp1/program/src/main.rs`):
//!
//!   1. `commitment : [u8; 32]`  — SHA-256(circuit_bytes)
//!   2. `n_cases    : u64`        — number of test cases proved
//!
//! Cross-checks both against the fixture and exits 0 iff verification
//! succeeded AND both committed values match.
//!
//! Per-phase timing is emitted to stderr (`[setup] N ms`, `[verify] N ms`)
//! when env var `SP1_VERIFIER_TIMING=1` is set. This is the diagnostic
//! used to separate the deterministic-setup cost from the verify-only
//! wall-clock (M5 in RFC-0008, amended by RFC-0024 for v0.3).
//!
//! Exit codes:
//!   0 — proof verified, public values consistent with fixture.
//!   1 — `PROVER.VERIFIER_REJECTED` (verify failed, public-value mismatch,
//!       or unreadable proof).
//!   2 — `MEASUREMENT.*` (missing fixture, bad argv).

use serde::Deserialize;
use sha2::{Digest, Sha256};
use sp1_sdk::{
    include_elf, Elf, HashableKey, Prover, ProverClient, ProvingKey,
    SP1ProofWithPublicValues, SP1VerifyingKey,
};
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

const ZKP_ECC_ELF: Elf = include_elf!("zkp_ecc-program");

#[derive(Deserialize)]
struct Fixture {
    circuit_byte_serialisation_hex: String,
    circuit_commitment_sha256_hex: String,
    n_samples: u64,
}

fn parse_args() -> Result<(PathBuf, PathBuf), String> {
    let mut argv = std::env::args().skip(1);
    let mut fixtures: Option<PathBuf> = None;
    let mut proof: Option<PathBuf> = None;
    while let Some(arg) = argv.next() {
        match arg.as_str() {
            "--fixtures" => fixtures = argv.next().map(PathBuf::from),
            "--proof" => proof = argv.next().map(PathBuf::from),
            other => {
                return Err(format!(
                    "MEASUREMENT.ENV_VAR_MISS: unknown flag: {other}"
                ));
            }
        }
    }
    match (fixtures, proof) {
        (Some(f), Some(p)) => Ok((f, p)),
        _ => Err(String::from(
            "usage: verifier --fixtures <path> --proof <path>",
        )),
    }
}

fn timing_enabled() -> bool {
    std::env::var("SP1_VERIFIER_TIMING").ok().as_deref() == Some("1")
}

#[tokio::main]
async fn main() -> ExitCode {
    let (fixtures_path, proof_path) = match parse_args() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };

    let bytes = match std::fs::read(&fixtures_path) {
        Ok(b) => b,
        Err(e) => {
            eprintln!("MEASUREMENT.ENV_VAR_MISS: cannot read fixture: {e}");
            return ExitCode::from(2);
        }
    };
    let fixture: Fixture = match serde_json::from_slice(&bytes) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("PROVER.VERIFIER_REJECTED: fixture not valid JSON: {e}");
            return ExitCode::from(1);
        }
    };
    let circuit_bytes = match hex::decode(&fixture.circuit_byte_serialisation_hex) {
        Ok(b) => b,
        Err(e) => {
            eprintln!("PROVER.VERIFIER_REJECTED: invalid circuit hex: {e}");
            return ExitCode::from(1);
        }
    };
    let expected_commitment: [u8; 32] = Sha256::digest(&circuit_bytes).into();

    let mut proof = match SP1ProofWithPublicValues::load(&proof_path) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("PROVER.VERIFIER_REJECTED: cannot load proof: {e}");
            return ExitCode::from(1);
        }
    };

    let client = ProverClient::from_env().await;

    // Derive the verifying key. If SP1_VK_CACHE points to an existing
    // file, deserialise the VK from disk (sub-second). Otherwise run
    // ProverClient::setup (≈150-180 s on c3-highmem-22) and write the
    // VK to the cache path if specified.
    let cache_path: Option<PathBuf> = std::env::var("SP1_VK_CACHE").ok().map(PathBuf::from);
    let t_setup = Instant::now();
    let (vk, setup_was_cached): (SP1VerifyingKey, bool) = match &cache_path {
        Some(p) if p.exists() => {
            let bytes = match std::fs::read(p) {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("PROVER.VERIFIER_REJECTED: cannot read VK cache: {e}");
                    return ExitCode::from(1);
                }
            };
            match bincode::deserialize::<SP1VerifyingKey>(&bytes) {
                Ok(vk) => (vk, true),
                Err(e) => {
                    eprintln!("PROVER.VERIFIER_REJECTED: cannot deserialise cached VK: {e}");
                    return ExitCode::from(1);
                }
            }
        }
        Some(p) => {
            let pk = match client.setup(ZKP_ECC_ELF).await {
                Ok(pk) => pk,
                Err(e) => {
                    eprintln!("PROVER.VERIFIER_REJECTED: setup failed: {e}");
                    return ExitCode::from(1);
                }
            };
            let vk = pk.verifying_key().clone();
            match bincode::serialize(&vk) {
                Ok(bytes) => {
                    if let Err(e) = std::fs::write(p, &bytes) {
                        eprintln!(
                            "MEASUREMENT.ENV_VAR_MISS: cannot write VK cache to {}: {e}",
                            p.display()
                        );
                        // Non-fatal: continue with the in-memory VK.
                    }
                }
                Err(e) => eprintln!("warning: cannot serialise VK for caching: {e}"),
            }
            (vk, false)
        }
        None => {
            let pk = match client.setup(ZKP_ECC_ELF).await {
                Ok(pk) => pk,
                Err(e) => {
                    eprintln!("PROVER.VERIFIER_REJECTED: setup failed: {e}");
                    return ExitCode::from(1);
                }
            };
            (pk.verifying_key().clone(), false)
        }
    };
    let setup_dur = t_setup.elapsed();
    if timing_enabled() {
        eprintln!(
            "[setup] {} ms (cached={})",
            setup_dur.as_millis(),
            setup_was_cached
        );
    }
    println!("Verifying key (hex): {}", vk.bytes32());

    let t_verify = Instant::now();
    if let Err(e) = client.verify(&proof, &vk, None) {
        eprintln!("PROVER.VERIFIER_REJECTED: verify failed: {e}");
        return ExitCode::from(1);
    }
    let verify_dur = t_verify.elapsed();
    if timing_enabled() {
        eprintln!("[verify] {} ms", verify_dur.as_millis());
    }

    // v0.2 public-value layout: (commitment: [u8; 32], n_cases: u64).
    let committed_hash: [u8; 32] = proof.public_values.read::<[u8; 32]>();
    let committed_n: u64 = proof.public_values.read::<u64>();

    let fixture_commitment_bytes: [u8; 32] =
        match hex::decode(&fixture.circuit_commitment_sha256_hex) {
            Ok(b) if b.len() == 32 => b.try_into().unwrap(),
            _ => {
                eprintln!(
                    "PROVER.VERIFIER_REJECTED: fixture commitment_sha256_hex is malformed"
                );
                return ExitCode::from(1);
            }
        };

    if committed_hash != expected_commitment {
        eprintln!(
            "PROVER.VERIFIER_REJECTED: committed hash does not match SHA-256(circuit_bytes)"
        );
        return ExitCode::from(1);
    }
    if committed_hash != fixture_commitment_bytes {
        eprintln!(
            "PROVER.VERIFIER_REJECTED: committed hash does not match fixture commitment"
        );
        return ExitCode::from(1);
    }
    if committed_n != fixture.n_samples {
        eprintln!(
            "PROVER.VERIFIER_REJECTED: committed n_cases ({committed_n}) != fixture n_samples ({})",
            fixture.n_samples
        );
        return ExitCode::from(1);
    }

    println!(
        "Proof verified; commitment = 0x{}, n_cases = {committed_n}",
        hex::encode(committed_hash)
    );
    ExitCode::SUCCESS
}
