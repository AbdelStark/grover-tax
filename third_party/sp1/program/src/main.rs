//! grover-tax SP1 zkVM program (apples-to-apples v0.1 / A2).
//!
//! Performs **N modular additions over secp256k1's prime field**
//! starting from a seed derived from the fixture's
//! `circuit_byte_serialisation_hex`. Commits SHA-256 of those bytes
//! (matches the fixture's `circuit_commitment_sha256_hex`).
//!
//! ```text
//! p        = 2^256 − 2^32 − 977
//! σ₀       = SHA-256(circuit_bytes) reduced mod p
//! σ_{i+1}  = (σ_i + (i + 1)) mod p   for i ∈ [0, N)
//! ```
//!
//! Public values committed (in order):
//!   1. SHA-256(circuit_bytes)               — 32 bytes
//!   2. N                                    — u64
//!   3. σ_N (big-endian 32 bytes)            — 32 bytes
//!
//! See `docs/apples-to-apples-v0.1.md` for the rationale.

#![no_main]
sp1_zkvm::entrypoint!(main);

use ruint::aliases::U256;
use sha2::{Digest, Sha256};

/// secp256k1's prime: `p = 2^256 − 2^32 − 977`.
const SECP256K1_P_HEX: &str =
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F";

pub fn main() {
    let circuit_bytes = sp1_zkvm::io::read_vec();
    let n: u64 = sp1_zkvm::io::read::<u64>();

    // Commit SHA-256 of the circuit bytes (= fixture's commitment).
    let commitment: [u8; 32] = Sha256::digest(&circuit_bytes).into();
    sp1_zkvm::io::commit(&commitment);
    sp1_zkvm::io::commit(&n);

    let p: U256 = U256::from_str_radix(SECP256K1_P_HEX, 16)
        .expect("SECP256K1_P parse");

    // σ₀ = SHA-256(circuit_bytes) reduced mod p.
    let mut state: U256 = U256::from_be_bytes::<32>(commitment) % p;

    // N modular additions: σ_{i+1} = (σ_i + (i + 1)) mod p.
    let mut i: u64 = 0;
    while i < n {
        let step: U256 = U256::from(i + 1);
        // ruint's `+` on U256 wraps at 2^256; reduce mod p afterwards.
        // Since both σ_i < p and step < 2^64 ≪ p, σ_i + step never wraps
        // around 2^256, so % p is the only reduction needed.
        state = (state + step) % p;
        i += 1;
    }

    let state_be: [u8; 32] = state.to_be_bytes::<32>();
    sp1_zkvm::io::commit(&state_be);
}
