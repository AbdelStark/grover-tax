//! In-circuit Blake2s commitment check (RFC-0004 §"Blake2s in-circuit",
//! RFC-0005 §"Commitment divergence").
//!
//! Computes Blake2s with default parameters (32-byte output, no key, no
//! personalisation) over a byte sequence and compares against the public
//! commitment carried in the fixture.
//!
//! Uses the corelib `core::blake::blake2s_compress` and
//! `core::blake::blake2s_finalize` primitives. The state-init constants
//! are the standard Blake2s IV XOR-ed with the parameter block
//! `0x01010020` (the encoded `(depth=1, fanout=1, leaf_length=0,
//! digest_length=0x20, key_length=0)` per RFC-7693 §2.5) on `h[0]`.

use core::array::ArrayTrait;
use core::blake::{blake2s_compress, blake2s_finalize};
use core::box::BoxTrait;

/// Blake2s IV with `h[0] = IV[0] XOR 0x01010020`.
///
/// 0x6A09E667 XOR 0x01010020 = 0x6B08E647 — the canonical first word for
/// a 32-byte-output, no-key Blake2s instance.
fn initial_state() -> Box<[u32; 8]> {
    BoxTrait::new(
        [
            0x6B08E647_u32, 0xBB67AE85_u32, 0x3C6EF372_u32, 0xA54FF53A_u32,
            0x510E527F_u32, 0x9B05688C_u32, 0x1F83D9AB_u32, 0x5BE0CD19_u32,
        ]
    )
}

/// Pack one 64-byte block of `bytes` (starting at `offset`) into the
/// 16-word little-endian message representation Blake2s expects. Bytes
/// beyond `bytes.len()` are zero-padded.
fn pack_block(bytes: @Array<u8>, offset: u32) -> Box<[u32; 16]> {
    let n = bytes.len();
    let mut words: Array<u32> = ArrayTrait::new();
    let mut i: u32 = 0;
    loop {
        if i == 16 { break; }
        let base = offset + i * 4;
        let b0: u32 = byte_or_zero(bytes, n, base + 0);
        let b1: u32 = byte_or_zero(bytes, n, base + 1);
        let b2: u32 = byte_or_zero(bytes, n, base + 2);
        let b3: u32 = byte_or_zero(bytes, n, base + 3);
        let word = b0 + b1 * 0x100 + b2 * 0x10000 + b3 * 0x1000000;
        words.append(word);
        i = i + 1;
    };
    BoxTrait::new(
        [
            *words.at(0), *words.at(1), *words.at(2), *words.at(3),
            *words.at(4), *words.at(5), *words.at(6), *words.at(7),
            *words.at(8), *words.at(9), *words.at(10), *words.at(11),
            *words.at(12), *words.at(13), *words.at(14), *words.at(15),
        ]
    )
}

fn byte_or_zero(bytes: @Array<u8>, n: u32, i: u32) -> u32 {
    if i < n {
        let b: u8 = *bytes.at(i);
        b.into()
    } else {
        0_u32
    }
}

/// Blake2s digest of `bytes` — returns 8 little-endian 32-bit words.
///
/// Handles inputs of any length:
///
/// * One full 64-byte block per `blake2s_compress`.
/// * Final (possibly partial) block via `blake2s_finalize`. An empty
///   input goes straight to `blake2s_finalize(state, 0, zeros)`.
pub fn commit_blake2s(bytes: @Array<u8>) -> [u32; 8] {
    let n = bytes.len();
    let mut state = initial_state();

    // Process full 64-byte blocks except the last one (the last block is
    // always handled by `blake2s_finalize`, even when the input is an
    // exact multiple of 64 — Blake2s treats the final block specially).
    if n > 64 {
        let mut offset: u32 = 0;
        let last_block_start = ((n - 1) / 64) * 64;
        loop {
            if offset == last_block_start { break; }
            let block = pack_block(bytes, offset);
            let bytes_so_far = offset + 64;
            state = blake2s_compress(state, bytes_so_far, block);
            offset = offset + 64;
        };
    }

    // Final block. Offset is `((n - 1) / 64) * 64` for non-empty `n`,
    // or 0 for empty input.
    let final_offset = if n == 0 { 0 } else { ((n - 1) / 64) * 64 };
    let final_block = pack_block(bytes, final_offset);
    state = blake2s_finalize(state, n, final_block);
    state.unbox()
}

/// Assert that `commit_blake2s(bytes) == expected`. The expected digest
/// is 8 little-endian 32-bit words — matches `hashlib.blake2s(...)`
/// digest bytes interpreted little-endian per 4 bytes.
pub fn assert_commitment_matches(bytes: @Array<u8>, expected: [u32; 8]) {
    let got = commit_blake2s(bytes);
    let [g0, g1, g2, g3, g4, g5, g6, g7] = got;
    let [e0, e1, e2, e3, e4, e5, e6, e7] = expected;
    if g0 != e0 || g1 != e1 || g2 != e2 || g3 != e3
       || g4 != e4 || g5 != e5 || g6 != e6 || g7 != e7
    {
        panic!("assert_commitment_matches: Blake2s digest mismatch")
    }
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use core::array::ArrayTrait;
    use super::{assert_commitment_matches, commit_blake2s};

    /// Python: `hashlib.blake2s(b"").hexdigest()`
    /// = "69217a3079908094e11121d042354a7c1f55b6482ca1a51e1b250dfd1ed0eef9"
    /// LE-packed into 8 × u32:
    ///   0x307a2169, 0x94809079, 0xd02111e1, 0x7c4a3542,
    ///   0x48b6551f, 0x1ea5a12c, 0xfd0d251b, 0xf9eed01e
    #[test]
    fn empty_input_matches_python() {
        let bytes = ArrayTrait::<u8>::new();
        let [w0, w1, w2, w3, w4, w5, w6, w7] = commit_blake2s(@bytes);
        assert!(w0 == 0x307a2169_u32);
        assert!(w1 == 0x94809079_u32);
        assert!(w2 == 0xd02111e1_u32);
        assert!(w3 == 0x7c4a3542_u32);
        assert!(w4 == 0x48b6551f_u32);
        assert!(w5 == 0x1ea5a12c_u32);
        assert!(w6 == 0xfd0d251b_u32);
        assert!(w7 == 0xf9eed01e_u32);
    }

    /// Python: `hashlib.blake2s(b"abc").hexdigest()`
    /// = "508c5e8c327c14e2e1a72ba34eeb452f37458b209ed63a294d999b4c86675982"
    /// LE-packed (matches `python3 -c "...for i in range(8): print(int.from_bytes(d[i*4:(i+1)*4], 'little'))"`):
    ///   0x8c5e8c50, 0xe2147c32, 0xa32ba7e1, 0x2f45eb4e,
    ///   0x208b4537, 0x293ad69e, 0x4c9b994d, 0x82596786
    #[test]
    fn three_byte_input_matches_python() {
        let mut bytes = ArrayTrait::<u8>::new();
        bytes.append('a');
        bytes.append('b');
        bytes.append('c');
        let [w0, w1, w2, w3, w4, w5, w6, w7] = commit_blake2s(@bytes);
        assert!(w0 == 0x8c5e8c50_u32);
        assert!(w1 == 0xe2147c32_u32);
        assert!(w2 == 0xa32ba7e1_u32);
        assert!(w3 == 0x2f45eb4e_u32);
        assert!(w4 == 0x208b4537_u32);
        assert!(w5 == 0x293ad69e_u32);
        assert!(w6 == 0x4c9b994d_u32);
        assert!(w7 == 0x82596786_u32);
    }

    #[test]
    fn assert_commitment_matches_passes_on_equal_digest() {
        let mut bytes = ArrayTrait::<u8>::new();
        bytes.append('a');
        bytes.append('b');
        bytes.append('c');
        let expected: [u32; 8] = [
            0x8c5e8c50_u32, 0xe2147c32_u32, 0xa32ba7e1_u32, 0x2f45eb4e_u32,
            0x208b4537_u32, 0x293ad69e_u32, 0x4c9b994d_u32, 0x82596786_u32,
        ];
        assert_commitment_matches(@bytes, expected);
    }

    #[test]
    #[should_panic]
    fn assert_commitment_matches_rejects_one_bit_flip() {
        let mut bytes = ArrayTrait::<u8>::new();
        bytes.append('a');
        bytes.append('b');
        bytes.append('c');
        // Flip the low bit of the expected first word.
        let expected: [u32; 8] = [
            0x8c5e8c51_u32, 0xe2147c32_u32, 0xa32ba7e1_u32, 0x2f45eb4e_u32,
            0x208b4537_u32, 0x293ad69e_u32, 0x4c9b994d_u32, 0x82596786_u32,
        ];
        assert_commitment_matches(@bytes, expected);
    }
}
