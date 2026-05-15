//! grover-tax Cairo program (apples-to-apples v0.1 / A2).
//!
//! Mirrors the SP1 side at `third_party/sp1/program/src/main.rs`:
//!
//! ```text
//! p        = 2^256 − 2^32 − 977            (secp256k1 prime)
//! σ₀       = Blake2s(circuit_bytes) reduced mod p   (Stwo side — RFC-0005)
//! σ_{i+1}  = (σ_i + (i + 1)) mod p          for i ∈ [0, gate_count)
//! ```
//!
//! Public outputs: `(commitment: u256 from Blake2s, sigma_n: u256)`.
//!
//! The program is callable both:
//!   * as a Cairo unit test entry point (via `apples_to_apples()`), and
//!   * as a cairo-vm-executable function for `stwo-cairo`'s `run_and_prove`.

pub mod limbs;
pub mod gates;
pub mod serialise;
pub mod commit;
pub mod c_tests;

use core::array::ArrayTrait;
use grover_tax_circuit::commit::commit_blake2s;

#[derive(Drop, Copy)]
pub struct Gate {
    pub opcode: u32,
    pub target: u32,
    pub ctrl_a: u32,
    pub ctrl_b: u32,
}

#[derive(Drop, Copy)]
pub struct TestCase {
    pub x_lo: u256,
    pub x_hi: u256,
    pub y: u256,
}

pub const NO_CTRL: u32 = 0xFFFF;
pub const OP_NOP: u32 = 0;
pub const OP_NOT: u32 = 1;
pub const OP_CNOT: u32 = 2;
pub const OP_TOFFOLI: u32 = 3;

/// secp256k1 prime `p = 2^256 − 2^32 − 977`.
///
/// Hex: `0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F`.
/// Cairo's `u256` is `{ low: u128, high: u128 }` where `low` holds bits 0..127
/// and `high` holds bits 128..255.
fn secp256k1_p() -> u256 {
    u256 {
        low: 0xFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F_u128,
        high: 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF_u128,
    }
}

/// Convert 8 little-endian u32 words (= Blake2s output) to a big-endian
/// `u256`. The 32-byte digest is interpreted exactly as SP1's side does
/// with `U256::from_be_bytes` of the raw digest bytes.
fn digest_to_u256_be(d: [u32; 8]) -> u256 {
    let [d0, d1, d2, d3, d4, d5, d6, d7] = d;
    // d0..d7 are little-endian u32 words of the digest bytes b0..b31.
    // The big-endian u256 reads bytes b0 (MSB) through b31 (LSB).
    // Word d_i contains bytes b_{4i}..b_{4i+3} as the low-to-high byte.
    // u256 layout in Cairo: `low` = bytes 16..31 (low 128 bits),
    //                       `high` = bytes 0..15 (high 128 bits).
    // Each u32 word reversed back to its 4 BE bytes:
    let be_w0: u128 = swap_u32_endian(d0).into();
    let be_w1: u128 = swap_u32_endian(d1).into();
    let be_w2: u128 = swap_u32_endian(d2).into();
    let be_w3: u128 = swap_u32_endian(d3).into();
    let be_w4: u128 = swap_u32_endian(d4).into();
    let be_w5: u128 = swap_u32_endian(d5).into();
    let be_w6: u128 = swap_u32_endian(d6).into();
    let be_w7: u128 = swap_u32_endian(d7).into();
    let high = be_w0 * 0x1000000000000000000000000_u128
             + be_w1 * 0x10000000000000000_u128
             + be_w2 * 0x100000000_u128
             + be_w3;
    let low = be_w4 * 0x1000000000000000000000000_u128
            + be_w5 * 0x10000000000000000_u128
            + be_w6 * 0x100000000_u128
            + be_w7;
    u256 { low, high }
}

/// Byte-swap a u32 (little-endian → big-endian word).
fn swap_u32_endian(w: u32) -> u32 {
    let b0 = w / 0x1000000_u32;
    let b1 = (w / 0x10000_u32) & 0xFF_u32;
    let b2 = (w / 0x100_u32) & 0xFF_u32;
    let b3 = w & 0xFF_u32;
    b3 * 0x1000000_u32 + b2 * 0x10000_u32 + b1 * 0x100_u32 + b0
}

/// Modular addition `(a + b) mod p`. Safe when `a < p` and `b` is small
/// (≪ 2^64): `a + b < 2^256` always, so Cairo's u256 `+` does not
/// overflow. We then conditionally subtract `p`.
fn mod_add_p(a: u256, b: u256, p: u256) -> u256 {
    let sum = a + b;
    if sum >= p { sum - p } else { sum }
}

/// Apples-to-apples kernel: N modular additions over secp256k1's prime.
///
/// Returns `(commitment, sigma_n)`. The caller is expected to publish
/// both as cairo-vm output for `stwo-cairo` to lift into public inputs.
pub fn apples_to_apples(circuit_bytes: @Array<u8>, n: u64) -> (u256, u256) {
    let digest = commit_blake2s(circuit_bytes);
    let commitment = digest_to_u256_be(digest);
    let p = secp256k1_p();
    let mut sigma = commitment % p;
    let mut i: u64 = 0;
    loop {
        if i == n { break; }
        let step: u256 = (i + 1).into();
        sigma = mod_add_p(sigma, step, p);
        i = i + 1;
    };
    (commitment, sigma)
}

/// Skeleton main retained for backward compatibility with existing
/// tests. Real execution goes through `apples_to_apples` driven by
/// `stwo-cairo`.
fn main(
    public_test_cases: Array<TestCase>,
    public_h_c: u256,
    secret_c: Array<Gate>,
) {
    let _ = public_test_cases.len();
    let _ = public_h_c;
    let _ = secret_c.len();
}

#[cfg(test)]
mod tests {
    use core::array::ArrayTrait;
    use super::{apples_to_apples, secp256k1_p, mod_add_p};

    #[test]
    fn mod_add_p_basic() {
        let p = secp256k1_p();
        let a: u256 = 1_u256;
        let b: u256 = 2_u256;
        let r = mod_add_p(a, b, p);
        assert!(r == 3_u256);
    }

    #[test]
    fn mod_add_p_wrap() {
        // (p - 1) + 2 = p + 1 ≡ 1  (mod p)
        let p = secp256k1_p();
        let r = mod_add_p(p - 1_u256, 2_u256, p);
        assert!(r == 1_u256);
    }

    #[test]
    fn apples_empty_circuit_n_zero() {
        let bytes = ArrayTrait::<u8>::new();
        let (commitment, sigma) = apples_to_apples(@bytes, 0_u64);
        // n=0 → sigma = commitment mod p (Blake2s digest of empty input,
        // reduced mod secp256k1's prime).
        // We don't pin the exact value here — `apples_to_apples_python_match`
        // (Python-side cross-check) is the authoritative gate.
        let p = secp256k1_p();
        assert!(sigma == commitment % p);
    }

    #[test]
    fn apples_short_input_n_one() {
        // Single-step loop adds 1.
        let mut bytes = ArrayTrait::<u8>::new();
        bytes.append('a');
        bytes.append('b');
        bytes.append('c');
        let (_, sigma_0) = apples_to_apples(@bytes, 0_u64);
        let (_, sigma_1) = apples_to_apples(@bytes, 1_u64);
        let p = secp256k1_p();
        assert!(sigma_1 == mod_add_p(sigma_0, 1_u256, p));
    }
}
