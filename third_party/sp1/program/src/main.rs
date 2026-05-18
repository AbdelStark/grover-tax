//! grover-tax SP1 zkVM program (apples-to-apples v0.2).
//!
//! Proves gate circuit execution: for each test case (x, y),
//! simulate(C, x_bytes) == y_bytes, where C is the secret gate list.
//! Commits SHA-256(circuit_bytes) as public output (matches fixture's
//! `circuit_commitment_sha256_hex`).
//!
//! Stdin layout:
//!   1. circuit_bytes: Vec<u8>   (read_vec)
//!   2. n_cases:       u64       (read)
//!   per test case:
//!     3. x_bytes:     [u8; 32]  (read) — first 32 bytes of P.X
//!     4. y_expected:  [u8; 32]  (read) — expected circuit output
//!
//! Public outputs committed (in order):
//!   1. SHA-256(circuit_bytes)   — [u8; 32]
//!   2. n_cases                  — u64

#![no_main]
sp1_zkvm::entrypoint!(main);

use sha2::{Digest, Sha256};

pub fn main() {
    let circuit_bytes = sp1_zkvm::io::read_vec();
    let n_cases: u64 = sp1_zkvm::io::read::<u64>();

    // Commit SHA-256 of the circuit bytes (= fixture's SHA-256 commitment).
    let commitment: [u8; 32] = Sha256::digest(&circuit_bytes).into();
    sp1_zkvm::io::commit(&commitment);
    sp1_zkvm::io::commit(&n_cases);

    // Deserialise gate list.
    let gates = parse_gtv1(&circuit_bytes).expect("invalid GTV1 circuit");

    // Simulate each test case and assert the result matches y_expected.
    for _ in 0..n_cases {
        let x: [u8; 32] = sp1_zkvm::io::read::<[u8; 32]>();
        let y_expected: [u8; 32] = sp1_zkvm::io::read::<[u8; 32]>();
        let y_got = simulate(&gates, &x);
        assert_eq!(y_got, y_expected, "simulation mismatch");
    }
}

// -- Gate representation ----------------------------------------------------

struct Gate {
    opcode: u8,
    target: u16,
    ctrl_a: u16,
    ctrl_b: u16,
}

const NO_CTRL: u16 = 0xFFFF;

// -- GTV1 parser ------------------------------------------------------------

fn parse_gtv1(bytes: &[u8]) -> Option<Vec<Gate>> {
    if bytes.len() < 8 {
        return None;
    }
    if &bytes[0..4] != b"GTV1" {
        return None;
    }
    let n_gates = u32::from_le_bytes([bytes[4], bytes[5], bytes[6], bytes[7]]) as usize;
    let expected_len = 8 + n_gates * 8;
    if bytes.len() != expected_len {
        return None;
    }
    let mut gates = Vec::with_capacity(n_gates);
    for i in 0..n_gates {
        let off = 8 + i * 8;
        let opcode = bytes[off];
        // bytes[off+1] = pad byte, ignored
        let target = u16::from_le_bytes([bytes[off + 2], bytes[off + 3]]);
        let ctrl_a = u16::from_le_bytes([bytes[off + 4], bytes[off + 5]]);
        let ctrl_b = u16::from_le_bytes([bytes[off + 6], bytes[off + 7]]);
        gates.push(Gate { opcode, target, ctrl_a, ctrl_b });
    }
    Some(gates)
}

// -- Bit manipulation -------------------------------------------------------

fn get_bit(state: &[u8; 32], i: usize) -> u8 {
    (state[i / 8] >> (i % 8)) & 1
}

fn set_bit(state: &mut [u8; 32], i: usize, v: u8) {
    if v == 1 {
        state[i / 8] |= 1u8 << (i % 8);
    } else {
        state[i / 8] &= !(1u8 << (i % 8));
    }
}

// -- Circuit simulator ------------------------------------------------------

fn simulate(gates: &[Gate], x: &[u8; 32]) -> [u8; 32] {
    let mut state = *x;
    for gate in gates {
        match gate.opcode {
            0 => {} // NOP — no effect
            1 => {
                // NOT: state[target] ^= 1
                let t = gate.target as usize;
                let v = get_bit(&state, t) ^ 1;
                set_bit(&mut state, t, v);
            }
            2 => {
                // CNOT: state[target] ^= state[ctrl_a]
                let t = gate.target as usize;
                let a = get_bit(&state, gate.ctrl_a as usize);
                let v = get_bit(&state, t) ^ a;
                set_bit(&mut state, t, v);
            }
            3 => {
                // TOFFOLI: state[target] ^= state[ctrl_a] & state[ctrl_b]
                let t = gate.target as usize;
                let a = get_bit(&state, gate.ctrl_a as usize);
                let b = get_bit(&state, gate.ctrl_b as usize);
                let v = get_bit(&state, t) ^ (a & b);
                set_bit(&mut state, t, v);
            }
            _ => panic!("unknown gate opcode: {}", gate.opcode),
        }
    }
    state
}
