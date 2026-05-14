//! grover-tax SP1 zkVM program.
//!
//! Reads the v0.1 fixture's `circuit_byte_serialisation_hex` (RFC-0005),
//! commits SHA-256 of those bytes (= the fixture's
//! `circuit_commitment_sha256_hex`), and walks the gate list applying a
//! cheap state transition per byte so the prover's wall-clock scales
//! with the circuit size rather than with constant overhead.
//!
//! Public values committed (in order):
//!   1. circuit hash (32 bytes, SHA-256)
//!   2. n_samples (u64)
//!   3. gate_count (u64)
//!   4. running state (u64) — witness that the gate-walk happened
//!
//! The body is intentionally small: the v0.1 measurement substrate is
//! the *cost of proving N proportional gates inside SP1+Groth16*, not
//! the cost of proving a specific elliptic-curve circuit (which is
//! upstream's full-fat workload, too heavy for a single-laptop run).

#![no_main]
sp1_zkvm::entrypoint!(main);

use sha2::{Digest, Sha256};

pub fn main() {
    let circuit_bytes = sp1_zkvm::io::read_vec();
    let n_samples = sp1_zkvm::io::read::<u64>();

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

    let commitment: [u8; 32] = Sha256::digest(&circuit_bytes).into();
    sp1_zkvm::io::commit(&commitment);
    sp1_zkvm::io::commit(&n_samples);
    sp1_zkvm::io::commit(&gate_count);

    // Cheap per-byte state transition over the whole gate list. Lifts the
    // cycle count above the SP1 fixed-cost floor so M1 reflects the circuit
    // size, not just the proving setup overhead.
    let mut state: u64 = 0;
    for byte in circuit_bytes.iter() {
        state = state
            .wrapping_add(*byte as u64)
            .rotate_left(7)
            ^ 0xA5A5_A5A5_A5A5_A5A5;
    }
    sp1_zkvm::io::commit(&state);
}
