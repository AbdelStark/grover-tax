//! 256-bit value representation over 9 × 31-bit limbs (RFC-0004
//! §"Field and representation").
//!
//! Why 9 × 31? Cairo's STARK field hosts 31-bit primes natively (M31 in
//! Stwo's case, `p = 2^31 - 1`). 9 × 31 = 279 bits of raw capacity — more
//! than the 256 bits we need, leaving ~23 bits of carry slack so a single
//! limb can absorb sums of two 256-bit values without overflowing the
//! 31-bit native ceiling.
//!
//! Limb 0 is the low-order limb; bit `i` of the 256-bit value lives at
//! `(i / 31, i % 31)`. Bit indices 0..=255 are valid; bits 256..=278 are
//! reserved carry slack and must read as 0 in any well-formed state.
//!
//! The Cairo standard `u32` type is used here as the limb container —
//! `u32` is what Cairo `2024_07` exposes for 32-bit unsigned integers,
//! and every limb is range-bounded to `< 2^31` by `assert_limb_in_range`.
//! `assert_state_in_range` checks the whole 9-tuple in one call.

use core::traits::Into;

pub const LIMBS: u32 = 9;
pub const LIMB_BITS: u32 = 31;
pub const BITS_PER_VALUE: u32 = 256;

/// `2^31` — the strict upper bound for a single limb's value.
/// Each limb must satisfy `0 <= limb < LIMB_RANGE` for the state to be
/// well-formed.
pub const LIMB_RANGE: u64 = 0x80000000_u64; // 2^31

#[derive(Drop, Copy, PartialEq)]
pub struct State {
    pub l0: u32,
    pub l1: u32,
    pub l2: u32,
    pub l3: u32,
    pub l4: u32,
    pub l5: u32,
    pub l6: u32,
    pub l7: u32,
    pub l8: u32,
}

pub fn zero_state() -> State {
    State { l0: 0, l1: 0, l2: 0, l3: 0, l4: 0, l5: 0, l6: 0, l7: 0, l8: 0 }
}

/// Read a limb by index 0..=8. Panics for out-of-range indices.
pub fn limb_at(s: State, i: u32) -> u32 {
    if i == 0 { s.l0 }
    else if i == 1 { s.l1 }
    else if i == 2 { s.l2 }
    else if i == 3 { s.l3 }
    else if i == 4 { s.l4 }
    else if i == 5 { s.l5 }
    else if i == 6 { s.l6 }
    else if i == 7 { s.l7 }
    else if i == 8 { s.l8 }
    else { panic!("limb_at: limb index out of range: {}", i) }
}

/// Functional limb update: returns a new state with limb `i` set to `v`.
pub fn with_limb(s: State, i: u32, v: u32) -> State {
    if i == 0 { State { l0: v, l1: s.l1, l2: s.l2, l3: s.l3, l4: s.l4, l5: s.l5, l6: s.l6, l7: s.l7, l8: s.l8 } }
    else if i == 1 { State { l0: s.l0, l1: v, l2: s.l2, l3: s.l3, l4: s.l4, l5: s.l5, l6: s.l6, l7: s.l7, l8: s.l8 } }
    else if i == 2 { State { l0: s.l0, l1: s.l1, l2: v, l3: s.l3, l4: s.l4, l5: s.l5, l6: s.l6, l7: s.l7, l8: s.l8 } }
    else if i == 3 { State { l0: s.l0, l1: s.l1, l2: s.l2, l3: v, l4: s.l4, l5: s.l5, l6: s.l6, l7: s.l7, l8: s.l8 } }
    else if i == 4 { State { l0: s.l0, l1: s.l1, l2: s.l2, l3: s.l3, l4: v, l5: s.l5, l6: s.l6, l7: s.l7, l8: s.l8 } }
    else if i == 5 { State { l0: s.l0, l1: s.l1, l2: s.l2, l3: s.l3, l4: s.l4, l5: v, l6: s.l6, l7: s.l7, l8: s.l8 } }
    else if i == 6 { State { l0: s.l0, l1: s.l1, l2: s.l2, l3: s.l3, l4: s.l4, l5: s.l5, l6: v, l7: s.l7, l8: s.l8 } }
    else if i == 7 { State { l0: s.l0, l1: s.l1, l2: s.l2, l3: s.l3, l4: s.l4, l5: s.l5, l6: s.l6, l7: v, l8: s.l8 } }
    else if i == 8 { State { l0: s.l0, l1: s.l1, l2: s.l2, l3: s.l3, l4: s.l4, l5: s.l5, l6: s.l6, l7: s.l7, l8: v } }
    else { panic!("with_limb: limb index out of range: {}", i) }
}

/// Decompose a 256-bit bit index into (limb_idx, bit_in_limb).
fn bit_pos(i: u32) -> (u32, u32) {
    (i / LIMB_BITS, i % LIMB_BITS)
}

/// `(s >> bit_position) & 1` over the 9-limb representation.
///
/// Returns the bit at position `i` (0..=255). Panics if `i >= 256` so a
/// runaway index never reads a carry-slack limb silently.
pub fn get_bit(s: State, i: u32) -> u32 {
    if i >= BITS_PER_VALUE {
        panic!("get_bit: index out of range: {}", i)
    }
    let (limb_idx, bit_in_limb) = bit_pos(i);
    let limb = limb_at(s, limb_idx);
    (limb / pow2_u32(bit_in_limb)) & 1
}

/// Functional bit set: returns a new state with bit `i` set to `v` (0 or 1).
///
/// Panics on `i >= 256` or `v > 1`.
pub fn set_bit(s: State, i: u32, v: u32) -> State {
    if i >= BITS_PER_VALUE {
        panic!("set_bit: index out of range: {}", i)
    }
    if v > 1 {
        panic!("set_bit: bit value must be 0 or 1, got {}", v)
    }
    let (limb_idx, bit_in_limb) = bit_pos(i);
    let limb = limb_at(s, limb_idx);
    let mask = pow2_u32(bit_in_limb);
    let cleared = limb - (limb & mask);
    let updated = cleared + v * mask;
    with_limb(s, limb_idx, updated)
}

/// Bitwise AND of a single limb with a single-bit mask — used by set_bit.
/// Cairo's `u32` operator `&` is exposed via the corelib; we keep a thin
/// wrapper here so future changes to the underlying operator are local.
fn band(a: u32, b: u32) -> u32 {
    a & b
}

/// `2^k` for `k` in `0..=30`. We avoid Cairo's `pow` corelib at this depth
/// because the static table fits and keeps the constraint cost bounded.
pub fn pow2_u32(k: u32) -> u32 {
    let mut acc: u32 = 1;
    let mut i: u32 = 0;
    loop {
        if i == k { break acc; }
        acc = acc * 2;
        i = i + 1;
    }
}

/// Range-check a single limb. Panics if `limb >= 2^31`.
pub fn assert_limb_in_range(limb: u32) {
    let upper: u64 = LIMB_RANGE;
    let cur: u64 = limb.into();
    if cur >= upper {
        panic!("assert_limb_in_range: limb {} exceeds 2^31 - 1", limb)
    }
}

/// Range-check every limb of a state.
pub fn assert_state_in_range(s: State) {
    assert_limb_in_range(s.l0);
    assert_limb_in_range(s.l1);
    assert_limb_in_range(s.l2);
    assert_limb_in_range(s.l3);
    assert_limb_in_range(s.l4);
    assert_limb_in_range(s.l5);
    assert_limb_in_range(s.l6);
    assert_limb_in_range(s.l7);
    assert_limb_in_range(s.l8);
}

/// Conditional select: returns `a` if `cond == 1`, `b` if `cond == 0`.
///
/// `cond` must be exactly 0 or 1; any other value panics. The unified
/// expression has the same constraint cost regardless of the value of
/// `cond`, matching the constant-cost step() requirement of RFC-0004.
pub fn select_state(cond: u32, a: State, b: State) -> State {
    if cond > 1 {
        panic!("select_state: cond must be 0 or 1, got {}", cond)
    }
    State {
        l0: cond * a.l0 + (1 - cond) * b.l0,
        l1: cond * a.l1 + (1 - cond) * b.l1,
        l2: cond * a.l2 + (1 - cond) * b.l2,
        l3: cond * a.l3 + (1 - cond) * b.l3,
        l4: cond * a.l4 + (1 - cond) * b.l4,
        l5: cond * a.l5 + (1 - cond) * b.l5,
        l6: cond * a.l6 + (1 - cond) * b.l6,
        l7: cond * a.l7 + (1 - cond) * b.l7,
        l8: cond * a.l8 + (1 - cond) * b.l8,
    }
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::{
        assert_limb_in_range,
        assert_state_in_range,
        get_bit,
        select_state,
        set_bit,
        zero_state,
        State,
        BITS_PER_VALUE,
    };

    #[test]
    fn zero_state_reads_all_zeros() {
        let s = zero_state();
        let mut i: u32 = 0;
        loop {
            if i == BITS_PER_VALUE { break; }
            assert!(get_bit(s, i) == 0);
            i = i + 1;
        };
    }

    #[test]
    fn set_then_get_round_trip_for_every_position() {
        // For each of the 256 bit positions, set the bit, read it back, then
        // clear it and read it back. Verifies the limb-and-mask path for
        // every (limb_idx, bit_in_limb) pair.
        let mut i: u32 = 0;
        loop {
            if i == BITS_PER_VALUE { break; }
            let one = set_bit(zero_state(), i, 1);
            assert!(get_bit(one, i) == 1);
            // All other bits remain 0.
            let mut j: u32 = 0;
            loop {
                if j == BITS_PER_VALUE { break; }
                if j != i {
                    assert!(get_bit(one, j) == 0);
                }
                j = j + 1;
            };
            let zero = set_bit(one, i, 0);
            assert!(get_bit(zero, i) == 0);
            i = i + 1;
        };
    }

    #[test]
    #[should_panic]
    fn set_bit_out_of_range_panics() {
        let _ = set_bit(zero_state(), 256, 1);
    }

    #[test]
    #[should_panic]
    fn get_bit_out_of_range_panics() {
        let _ = get_bit(zero_state(), 1000);
    }

    #[test]
    #[should_panic]
    fn set_bit_value_must_be_zero_or_one() {
        let _ = set_bit(zero_state(), 0, 2);
    }

    #[test]
    fn assert_limb_in_range_accepts_max_minus_one() {
        // 2^31 - 1 = 2147483647 — the largest in-range limb value.
        assert_limb_in_range(0x7FFFFFFF_u32);
    }

    #[test]
    #[should_panic]
    fn assert_limb_in_range_rejects_too_large() {
        // 2^31 = 2147483648 — exactly one past the range ceiling.
        assert_limb_in_range(0x80000000_u32);
    }

    #[test]
    fn assert_state_in_range_accepts_zero_state() {
        assert_state_in_range(zero_state());
    }

    #[test]
    #[should_panic]
    fn assert_state_in_range_rejects_high_limb() {
        let bad = State {
            l0: 0,
            l1: 0,
            l2: 0x80000000_u32, // exceeds the range ceiling.
            l3: 0,
            l4: 0,
            l5: 0,
            l6: 0,
            l7: 0,
            l8: 0,
        };
        assert_state_in_range(bad);
    }

    #[test]
    fn select_state_picks_a_when_cond_is_one() {
        let a = set_bit(zero_state(), 0, 1);
        let b = zero_state();
        let chosen = select_state(1, a, b);
        assert!(get_bit(chosen, 0) == 1);
    }

    #[test]
    fn select_state_picks_b_when_cond_is_zero() {
        let a = set_bit(zero_state(), 0, 1);
        let b = zero_state();
        let chosen = select_state(0, a, b);
        assert!(get_bit(chosen, 0) == 0);
    }

    #[test]
    #[should_panic]
    fn select_state_rejects_non_boolean_cond() {
        let a = zero_state();
        let b = zero_state();
        let _ = select_state(7, a, b);
    }
}
