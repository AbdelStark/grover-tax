//! In-proof Fiat-Shamir test-case derivation (KB-9, #121).
//!
//! The reference benchmark (`tanujkhattar/zkp_ecc`) does **not** let the prover
//! choose its own test inputs — it derives them inside the proof from the
//! circuit hash via the Fiat-Shamir heuristic (a SHAKE/CSPRNG seeded by
//! `H(circuit)`), so a cheating prover cannot dodge inputs its circuit gets
//! wrong (`getting_started.md` §"Using Fuzz Testing as a Proof Strategy").
//!
//! This module supplies that derivation on the SP1 side: a dependency-free,
//! pure-Rust **SHAKE-256** XOF seeded by the circuit hash, from which
//! `num_samples` register-input pairs `(x, y)` are read — `x` then `y`, each
//! `ceil(width/8)` little-endian bytes masked to `width` bits, matching the
//! supplied-case layout of KB-3 (`grover_tax.registers.iadd_test_cases`).
//!
//! Cross-stack equality: the Python reference (`grover_tax.fiat_shamir`) and
//! this Rust derivation produce byte-identical case streams for a given circuit
//! hash; both are pinned to `hashlib.shake_256`. The Cairo side derives the same
//! cases once its in-circuit XOF is aligned under KB-13 (#125).

/// SHAKE-256 rate in bytes (1088-bit rate, 512-bit capacity).
const RATE: usize = 136;

const KECCAK_RC: [u64; 24] = [
    0x0000_0000_0000_0001,
    0x0000_0000_0000_8082,
    0x8000_0000_0000_808a,
    0x8000_0000_8000_8000,
    0x0000_0000_0000_808b,
    0x0000_0000_8000_0001,
    0x8000_0000_8000_8081,
    0x8000_0000_0000_8009,
    0x0000_0000_0000_008a,
    0x0000_0000_0000_0088,
    0x0000_0000_8000_8009,
    0x0000_0000_8000_000a,
    0x0000_0000_8000_808b,
    0x8000_0000_0000_008b,
    0x8000_0000_0000_8089,
    0x8000_0000_0000_8003,
    0x8000_0000_0000_8002,
    0x8000_0000_0000_0080,
    0x0000_0000_0000_800a,
    0x8000_0000_8000_000a,
    0x8000_0000_8000_8081,
    0x8000_0000_0000_8080,
    0x0000_0000_8000_0001,
    0x8000_0000_8000_8008,
];

const KECCAK_ROTC: [u32; 24] = [
    1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14, 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
];

const KECCAK_PILN: [usize; 24] = [
    10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4, 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
];

/// The Keccak-f[1600] permutation over a 25-lane state.
fn keccak_f1600(st: &mut [u64; 25]) {
    for &rc in KECCAK_RC.iter() {
        // Theta.
        let mut bc = [0u64; 5];
        for i in 0..5 {
            bc[i] = st[i] ^ st[i + 5] ^ st[i + 10] ^ st[i + 15] ^ st[i + 20];
        }
        for i in 0..5 {
            let t = bc[(i + 4) % 5] ^ bc[(i + 1) % 5].rotate_left(1);
            let mut j = 0;
            while j < 25 {
                st[j + i] ^= t;
                j += 5;
            }
        }
        // Rho + Pi.
        let mut t = st[1];
        for i in 0..24 {
            let j = KECCAK_PILN[i];
            let tmp = st[j];
            st[j] = t.rotate_left(KECCAK_ROTC[i]);
            t = tmp;
        }
        // Chi.
        let mut k = 0;
        while k < 25 {
            bc.copy_from_slice(&st[k..k + 5]);
            for i in 0..5 {
                st[k + i] ^= (!bc[(i + 1) % 5]) & bc[(i + 2) % 5];
            }
            k += 5;
        }
        // Iota.
        st[0] ^= rc;
    }
}

/// SHAKE-256: absorb `input`, squeeze `out_len` bytes. Matches
/// `hashlib.shake_256(input).digest(out_len)`.
pub fn shake256(input: &[u8], out_len: usize) -> Vec<u8> {
    let mut st = [0u64; 25];

    // Pad: append the SHAKE domain byte 0x1F, zero-fill to a rate multiple,
    // then set the high bit of the final byte (the 0x80 pad terminator).
    let mut msg = input.to_vec();
    let pad = RATE - (msg.len() % RATE);
    msg.push(0x1f);
    msg.resize(msg.len() + (pad - 1), 0);
    let last = msg.len() - 1;
    msg[last] |= 0x80;

    // Absorb.
    let mut p = 0;
    while p < msg.len() {
        for i in 0..RATE / 8 {
            let mut lane = 0u64;
            for b in 0..8 {
                lane |= (msg[p + i * 8 + b] as u64) << (8 * b);
            }
            st[i] ^= lane;
        }
        keccak_f1600(&mut st);
        p += RATE;
    }

    // Squeeze.
    let mut out = Vec::with_capacity(out_len);
    while out.len() < out_len {
        let take = core::cmp::min(RATE, out_len - out.len());
        for i in 0..take {
            let lane = st[i / 8];
            out.push(((lane >> (8 * (i % 8))) & 0xff) as u8);
        }
        if out.len() < out_len {
            keccak_f1600(&mut st);
        }
    }
    out
}

fn le_u128(bytes: &[u8]) -> u128 {
    let mut v: u128 = 0;
    for (i, &b) in bytes.iter().enumerate() {
        v |= (b as u128) << (8 * i);
    }
    v
}

/// Derive `num_samples` register-input pairs `(x, y)` from `circuit_hash` via
/// Fiat-Shamir (SHAKE-256). Each operand is `ceil(width/8)` little-endian bytes
/// masked to `width` bits; `x` is read before `y`.
///
/// Panics if `width` is 0 or > 128, or `num_samples` is 0.
pub fn derive_cases(circuit_hash: &[u8], width: u32, num_samples: usize) -> Vec<(u128, u128)> {
    assert!((1..=128).contains(&width), "width must be in 1..=128");
    assert!(num_samples > 0, "num_samples must be positive");

    let nbytes = width.div_ceil(8) as usize;
    let buf = shake256(circuit_hash, num_samples * 2 * nbytes);
    let mask: u128 = if width == 128 {
        u128::MAX
    } else {
        (1u128 << width) - 1
    };

    let mut cases = Vec::with_capacity(num_samples);
    for k in 0..num_samples {
        let base = k * 2 * nbytes;
        let x = le_u128(&buf[base..base + nbytes]) & mask;
        let y = le_u128(&buf[base + nbytes..base + 2 * nbytes]) & mask;
        cases.push((x, y));
    }
    cases
}

#[cfg(test)]
mod tests {
    use super::{derive_cases, shake256};

    fn hex(bytes: &[u8]) -> String {
        let mut s = String::with_capacity(bytes.len() * 2);
        for b in bytes {
            s.push_str(&format!("{b:02x}"));
        }
        s
    }

    // Cross-vectors against Python's hashlib.shake_256 (the authoritative XOF).

    #[test]
    fn shake256_empty_matches_hashlib() {
        assert_eq!(
            hex(&shake256(b"", 32)),
            "46b9dd2b0ba88d13233b3feb743eeb243fcd52ea62b81b82b50c27646ed5762f"
        );
    }

    #[test]
    fn shake256_abc_matches_hashlib() {
        assert_eq!(
            hex(&shake256(b"abc", 32)),
            "483366601360a8771c6863080cc4114d8db44530f8f1e1ee4f94ea37e78b5739"
        );
    }

    #[test]
    fn shake256_multi_block_squeeze_matches_hashlib() {
        // 200 bytes > rate (136): exercises a squeeze-time permutation.
        let out = shake256(b"abc", 200);
        assert_eq!(
            hex(&out[168..200]),
            "9442b99903f4dcfd8559ed3950faf40fe6f3b5d710ed3b677513771af6bfe119"
        );
    }

    #[test]
    fn derive_cases_matches_python_reference() {
        // seed = sha256(b"iadd64-demo"); see grover_tax.fiat_shamir test.
        let seed = [
            0x95, 0xe8, 0xec, 0x6d, 0xc1, 0xe3, 0x0b, 0x67, 0xb2, 0xa3, 0xf1, 0xcf, 0x28, 0x5e,
            0x34, 0x12, 0x8b, 0x6a, 0xd3, 0xee, 0x12, 0x1f, 0x69, 0xaa, 0x6e, 0x24, 0x74, 0x9d,
            0x6e, 0x62, 0xc8, 0xf2,
        ];
        let cases = derive_cases(&seed, 64, 4);
        assert_eq!(
            cases,
            vec![
                (4113191057548519565u128, 17909937566100645171u128),
                (1222146416732106357, 15712575212200367868),
                (3544430547654831529, 45149841657852178),
                (18158939369488272335, 16905458393758049869),
            ]
        );
    }

    #[test]
    fn derive_cases_is_deterministic() {
        let seed = [7u8; 32];
        assert_eq!(derive_cases(&seed, 64, 8), derive_cases(&seed, 64, 8));
    }

    #[test]
    fn derive_cases_changes_with_circuit_hash() {
        // Fiat-Shamir property: different circuit -> different inputs.
        let a = derive_cases(&[1u8; 32], 64, 4);
        let b = derive_cases(&[2u8; 32], 64, 4);
        assert_ne!(a, b);
    }
}
