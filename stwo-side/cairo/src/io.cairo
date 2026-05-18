//! Byte ↔ State conversion bridging the 256-bit gate circuit state
//! between GTV1 fixture bytes (bit i at byte i/8, position i%8, LSB-first)
//! and Cairo's limb layout (bit i at limb i/31, position i%31).

use core::array::ArrayTrait;
use grover_tax_circuit::limbs::{State, zero_state, get_bit, set_bit};

/// Deserialise 32 raw bytes (256 bits) into a gate `State`.
/// Bit ordering matches Python's `BitVector`: bit `i` at byte `i/8`, position `i%8` (LSB-first).
pub fn bytes_to_state(bytes: @Array<u8>) -> State {
    let mut s = zero_state();
    let mut i: u32 = 0;
    loop {
        if i == 256_u32 { break; }
        let byte_idx: u32 = i / 8_u32;
        let bit_in_byte: u32 = i % 8_u32;
        let byte_val: u32 = (*bytes.at(byte_idx)).into();
        // Extract bit: (byte_val >> bit_in_byte) & 1
        // Use pow2 for the shift since Cairo has no >> operator on u32
        let shifted: u32 = byte_val / pow2_8(bit_in_byte);
        let bit_val: u32 = shifted & 1_u32;
        s = set_bit(s, i, bit_val);
        i = i + 1_u32;
    };
    s
}

/// Serialise a gate `State` back to 32 bytes (256 bits).
/// Inverse of `bytes_to_state`.
pub fn state_to_bytes(s: State) -> Array<u8> {
    let mut out: Array<u8> = ArrayTrait::new();
    let mut byte_idx: u32 = 0_u32;
    loop {
        if byte_idx == 32_u32 { break; }
        let mut byte_val: u32 = 0_u32;
        let mut bit_in_byte: u32 = 0_u32;
        loop {
            if bit_in_byte == 8_u32 { break; }
            let bit_i: u32 = byte_idx * 8_u32 + bit_in_byte;
            let b: u32 = get_bit(s, bit_i);
            byte_val = byte_val | (b * pow2_8(bit_in_byte));
            bit_in_byte = bit_in_byte + 1_u32;
        };
        let byte_u8: u8 = byte_val.try_into().unwrap();
        out.append(byte_u8);
        byte_idx = byte_idx + 1_u32;
    };
    out
}

/// `2^k` for `k` in `0..=7` (byte-level shifts).
fn pow2_8(k: u32) -> u32 {
    if k == 0 { 1_u32 }
    else if k == 1 { 2_u32 }
    else if k == 2 { 4_u32 }
    else if k == 3 { 8_u32 }
    else if k == 4 { 16_u32 }
    else if k == 5 { 32_u32 }
    else if k == 6 { 64_u32 }
    else { 128_u32 }
}

#[cfg(test)]
mod tests {
    use super::{bytes_to_state, state_to_bytes};
    use grover_tax_circuit::limbs::get_bit;

    #[test]
    fn round_trip_zero_bytes() {
        let mut bytes: Array<u8> = core::array::ArrayTrait::new();
        let mut i: u32 = 0;
        loop { if i == 32 { break; } bytes.append(0_u8); i = i + 1; };
        let s = bytes_to_state(@bytes);
        let out = state_to_bytes(s);
        let mut j: u32 = 0;
        loop { if j == 32 { break; } assert!(*out.at(j) == 0_u8); j = j + 1; };
    }

    #[test]
    fn round_trip_ff_bytes() {
        let mut bytes: Array<u8> = core::array::ArrayTrait::new();
        let mut i: u32 = 0;
        loop { if i == 32 { break; } bytes.append(0xFF_u8); i = i + 1; };
        let s = bytes_to_state(@bytes);
        let out = state_to_bytes(s);
        let mut j: u32 = 0;
        loop { if j == 32 { break; } assert!(*out.at(j) == 0xFF_u8); j = j + 1; };
    }

    #[test]
    fn bit_zero_is_lsb_of_byte_zero() {
        // byte 0 = 0x01 means bit 0 = 1, bits 1..7 = 0
        let mut bytes: Array<u8> = core::array::ArrayTrait::new();
        bytes.append(0x01_u8);
        let mut i: u32 = 1;
        loop { if i == 32 { break; } bytes.append(0_u8); i = i + 1; };
        let s = bytes_to_state(@bytes);
        assert!(get_bit(s, 0) == 1_u32);
        assert!(get_bit(s, 1) == 0_u32);
        assert!(get_bit(s, 7) == 0_u32);
        assert!(get_bit(s, 8) == 0_u32);
    }

    #[test]
    fn bit_seven_is_msb_of_byte_zero() {
        // byte 0 = 0x80 means bit 7 = 1, bits 0..6 = 0
        let mut bytes: Array<u8> = core::array::ArrayTrait::new();
        bytes.append(0x80_u8);
        let mut i: u32 = 1;
        loop { if i == 32 { break; } bytes.append(0_u8); i = i + 1; };
        let s = bytes_to_state(@bytes);
        assert!(get_bit(s, 7) == 1_u32);
        assert!(get_bit(s, 0) == 0_u32);
        assert!(get_bit(s, 6) == 0_u32);
        assert!(get_bit(s, 8) == 0_u32);
    }
}
