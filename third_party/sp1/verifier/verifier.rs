//! grover-tax SP1 verifier binary.
//!
//! Argv contract (matches `bin/verify_sp1.sh`):
//!
//!   verifier --fixtures <fixtures_path> --proof <proof_path>
//!
//! Loads the saved `SP1ProofWithPublicValues`, computes the verifying
//! key by re-running `setup(ZKP_ECC_ELF)`, asks `ProverClient::verify`
//! to check the Groth16 proof, and reads back the public values to
//! confirm they match the fixture's metadata.
//!
//! Exit codes:
//!   0 — proof verified.
//!   1 — `PROVER.VERIFIER_REJECTED` (verify failed or public values
//!       disagree with the fixture).
//!   2 — `MEASUREMENT.*` (missing file, bad argv).

use ruint::aliases::U256;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use sp1_sdk::{
    include_elf, Elf, HashableKey, Prover, ProverClient, ProvingKey,
    SP1ProofWithPublicValues,
};

/// secp256k1's prime: `p = 2^256 − 2^32 − 977`.
const SECP256K1_P_HEX: &str =
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F";

/// Re-derive the expected final state σ_N independently of the prover.
/// Mirrors the loop in `third_party/sp1/program/src/main.rs`.
fn expected_sigma_n(commitment: &[u8; 32], n: u64) -> [u8; 32] {
    let p: U256 = U256::from_str_radix(SECP256K1_P_HEX, 16).unwrap();
    let mut state: U256 = U256::from_be_bytes::<32>(*commitment) % p;
    let mut i: u64 = 0;
    while i < n {
        let step: U256 = U256::from(i + 1);
        state = (state + step) % p;
        i += 1;
    }
    state.to_be_bytes::<32>()
}
use std::path::PathBuf;
use std::process::ExitCode;

const ZKP_ECC_ELF: Elf = include_elf!("zkp_ecc-program");

#[derive(Deserialize)]
struct Fixture {
    circuit_byte_serialisation_hex: String,
    circuit_commitment_sha256_hex: String,
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
    let pk = match client.setup(ZKP_ECC_ELF).await {
        Ok(p) => p,
        Err(e) => {
            eprintln!("PROVER.VERIFIER_REJECTED: setup failed: {e}");
            return ExitCode::from(1);
        }
    };
    let vk = pk.verifying_key();
    println!("Verifying key (hex): {}", vk.bytes32());

    if let Err(e) = client.verify(&proof, vk, None) {
        eprintln!("PROVER.VERIFIER_REJECTED: verify failed: {e}");
        return ExitCode::from(1);
    }

    // Recompute the loop count exactly as the prover did: the binary
    // header is `[b"GTV1", gate_count: u32 LE, ...]`.
    let gate_count: u64 = if circuit_bytes.len() >= 8 {
        u32::from_le_bytes([
            circuit_bytes[4], circuit_bytes[5], circuit_bytes[6], circuit_bytes[7],
        ]) as u64
    } else {
        0
    };

    // Cross-check public values vs the fixture + re-derived σ_N.
    let committed_hash = proof.public_values.read::<[u8; 32]>();
    let committed_n = proof.public_values.read::<u64>();
    let committed_sigma_n = proof.public_values.read::<[u8; 32]>();

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
    if committed_n != gate_count {
        eprintln!(
            "PROVER.VERIFIER_REJECTED: committed n ({committed_n}) != fixture gate_count ({gate_count})"
        );
        return ExitCode::from(1);
    }
    let expected = expected_sigma_n(&committed_hash, committed_n);
    if committed_sigma_n != expected {
        eprintln!(
            "PROVER.VERIFIER_REJECTED: committed σ_N does not match re-derived σ_N"
        );
        return ExitCode::from(1);
    }

    println!("Proof verified; σ_N = 0x{}", hex::encode(committed_sigma_n));
    ExitCode::SUCCESS
}
