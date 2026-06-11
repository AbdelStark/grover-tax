//! Full kickmix simulator in Cairo — the Stwo-side mirror (KB-11, #123).
//!
//! Statement-equal to the Rust simulator (`kickmix` crate, KB-8/#120): the same
//! state machine (qubits + phase + classical bits + condition stack), the same
//! `HMR` phase-kickback semantics, and the **same SplitMix64 measurement
//! stream**, so a given (circuit, initial qubits, seed) yields bit-for-bit
//! identical results on both sides.
//!
//! Like the GTV1 gate path, the Cairo program consumes a **pre-parsed**
//! instruction list (text `.kmx` parsing stays host-side in `grover_tax.kmx` /
//! the Rust parser); registers are supplied as qubit-index arrays. The
//! instruction encoding here matches that structured form.
//!
//! Coordinated with Tanuj's forthcoming Cairo codebase under KB-13 (#125); this
//! is the grover-tax reference until that statement-equality is confirmed.

use core::array::ArrayTrait;
use core::dict::{Felt252Dict, Felt252DictTrait};

// Opcodes (structured instruction stream — host strips REGISTER/APPEND/DEBUG).
pub const OP_X: u32 = 1;
pub const OP_CX: u32 = 2;
pub const OP_CCX: u32 = 3;
pub const OP_Z: u32 = 4;
pub const OP_CZ: u32 = 5;
pub const OP_CCZ: u32 = 6;
pub const OP_NEG: u32 = 7;
pub const OP_SWAP: u32 = 8;
pub const OP_R: u32 = 9;
pub const OP_HMR: u32 = 10;
pub const OP_BIT_INVERT: u32 = 11;
pub const OP_BIT_STORE0: u32 = 12;
pub const OP_BIT_STORE1: u32 = 13;
pub const OP_PUSH_CONDITION: u32 = 14;
pub const OP_POP_CONDITION: u32 = 15;

pub const NO_TARGET: u32 = 0xFFFFFFFF;
pub const NO_COND: u32 = 0xFFFFFFFF;

const TWO64: u128 = 0x10000000000000000; // 2^64
const GAMMA: u64 = 0x9E3779B97F4A7C15;
const MUL1: u64 = 0xBF58476D1CE4E5B9;
const MUL2: u64 = 0x94D049BB133111EB;

/// One structured kickmix instruction. Unused target slots carry `NO_TARGET`;
/// `cond == NO_COND` means unconditional. For `HMR`, `t0` is the qubit and `t1`
/// the output bit; for `PUSH_CONDITION`, `cond` is the bit whose value is pushed.
#[derive(Copy, Drop)]
pub struct Inst {
    pub opcode: u32,
    pub t0: u32,
    pub t1: u32,
    pub t2: u32,
    pub cond: u32,
}

/// SplitMix64 — identical to the Rust `kickmix::SplitMix64`. Measurement bits
/// are `next_u64() & 1`.
#[derive(Copy, Drop)]
pub struct Rng {
    pub state: u64,
}

pub fn rng_new(seed: u64) -> Rng {
    Rng { state: seed }
}

fn wadd64(a: u64, b: u64) -> u64 {
    let s: u128 = a.into() + b.into();
    (s % TWO64).try_into().unwrap()
}

fn wmul64(a: u64, b: u64) -> u64 {
    // Two u64 operands: product < 2^128, fits u128; reduce mod 2^64.
    let p: u128 = a.into() * b.into();
    (p % TWO64).try_into().unwrap()
}

pub fn next_u64(ref rng: Rng) -> u64 {
    rng.state = wadd64(rng.state, GAMMA);
    let mut z: u64 = rng.state;
    z = wmul64(z ^ (z / 0x40000000_u64), MUL1); // ^ (z >> 30)
    z = wmul64(z ^ (z / 0x8000000_u64), MUL2); //  ^ (z >> 27)
    z ^ (z / 0x80000000_u64) //                    ^ (z >> 31)
}

fn next_bit(ref rng: Rng) -> u8 {
    let v = next_u64(ref rng);
    (v % 2).try_into().unwrap()
}

/// Mutable simulator state. `phase` is a single sign bit (0 = +1, 1 = -1).
/// The condition stack is a dict `0..cond_len` of pushed bit values.
#[derive(Destruct)]
pub struct State {
    pub qubits: Felt252Dict<u8>,
    pub bits: Felt252Dict<u8>,
    pub phase: u8,
    pub cond: Felt252Dict<u8>,
    pub cond_len: u32,
}

pub fn new_state() -> State {
    State {
        qubits: Default::default(),
        bits: Default::default(),
        phase: 0,
        cond: Default::default(),
        cond_len: 0,
    }
}

/// Pin the `u32 -> felt252` conversion (otherwise ambiguous with `-> bytes31`).
fn felt_key(i: u32) -> felt252 {
    i.into()
}

pub fn get_q(ref s: State, idx: u32) -> u8 {
    s.qubits.get(felt_key(idx))
}

pub fn get_b(ref s: State, idx: u32) -> u8 {
    s.bits.get(felt_key(idx))
}

/// Whether a (non-control-flow) instruction is active: every pushed condition
/// is true and the optional `if` bit is true.
fn active(ref s: State, cond: u32) -> bool {
    let mut ok = true;
    let mut i: u32 = 0;
    while i < s.cond_len {
        if s.cond.get(felt_key(i)) == 0 {
            ok = false;
        }
        i = i + 1;
    }
    if ok && cond != NO_COND {
        ok = get_b(ref s, cond) == 1;
    }
    ok
}

/// Apply one instruction, mutating `s` and drawing from `rng` for HMR / misused R.
pub fn step(ref s: State, ref rng: Rng, inst: Inst) {
    // Control flow ignores the condition stack.
    if inst.opcode == OP_PUSH_CONDITION {
        let v = get_b(ref s, inst.cond);
        s.cond.insert(felt_key(s.cond_len), v);
        s.cond_len = s.cond_len + 1;
        return;
    }
    if inst.opcode == OP_POP_CONDITION {
        if s.cond_len > 0 {
            s.cond_len = s.cond_len - 1;
        }
        return;
    }

    if !active(ref s, inst.cond) {
        return;
    }

    let op = inst.opcode;
    if op == OP_X {
        let v = get_q(ref s, inst.t0);
        s.qubits.insert(felt_key(inst.t0), 1 - v);
    } else if op == OP_CX {
        if get_q(ref s, inst.t0) == 1 {
            let v = get_q(ref s, inst.t1);
            s.qubits.insert(felt_key(inst.t1), 1 - v);
        }
    } else if op == OP_CCX {
        if get_q(ref s, inst.t0) == 1 && get_q(ref s, inst.t1) == 1 {
            let v = get_q(ref s, inst.t2);
            s.qubits.insert(felt_key(inst.t2), 1 - v);
        }
    } else if op == OP_Z {
        if get_q(ref s, inst.t0) == 1 {
            s.phase = 1 - s.phase;
        }
    } else if op == OP_CZ {
        if get_q(ref s, inst.t0) == 1 && get_q(ref s, inst.t1) == 1 {
            s.phase = 1 - s.phase;
        }
    } else if op == OP_CCZ {
        if get_q(ref s, inst.t0) == 1 && get_q(ref s, inst.t1) == 1 && get_q(ref s, inst.t2) == 1 {
            s.phase = 1 - s.phase;
        }
    } else if op == OP_NEG {
        s.phase = 1 - s.phase;
    } else if op == OP_SWAP {
        let a = get_q(ref s, inst.t0);
        let b = get_q(ref s, inst.t1);
        s.qubits.insert(felt_key(inst.t0), b);
        s.qubits.insert(felt_key(inst.t1), a);
    } else if op == OP_R {
        // Reset to |0>; resetting a |1> randomizes the phase (a misuse the
        // fuzzer catches) — consume a trajectory bit then, exactly as Rust.
        if get_q(ref s, inst.t0) == 1 && next_bit(ref rng) == 1 {
            s.phase = 1 - s.phase;
        }
        s.qubits.insert(felt_key(inst.t0), 0);
    } else if op == OP_HMR {
        let m = next_bit(ref rng);
        if get_q(ref s, inst.t0) == 1 && m == 1 {
            s.phase = 1 - s.phase;
        }
        s.bits.insert(felt_key(inst.t1), m);
        s.qubits.insert(felt_key(inst.t0), 0);
    } else if op == OP_BIT_INVERT {
        let v = get_b(ref s, inst.t0);
        s.bits.insert(felt_key(inst.t0), 1 - v);
    } else if op == OP_BIT_STORE0 {
        s.bits.insert(felt_key(inst.t0), 0);
    } else if op == OP_BIT_STORE1 {
        s.bits.insert(felt_key(inst.t0), 1);
    } else {
        panic!("unknown opcode {}", op);
    }
}

/// Run a whole instruction stream.
pub fn run(ref s: State, ref rng: Rng, program: @Array<Inst>) {
    let mut i: u32 = 0;
    while i < program.len() {
        step(ref s, ref rng, *program.at(i));
        i = i + 1;
    }
}

/// Load `value` into the qubits listed in `members`, 2's-complement LE
/// (member 0 = least significant).
pub fn load_register(ref s: State, members: @Array<u32>, value: u256) {
    let mut v = value;
    let mut j: u32 = 0;
    while j < members.len() {
        let bit: u8 = (v % 2).try_into().unwrap();
        s.qubits.insert(felt_key(*members.at(j)), bit);
        v = v / 2;
        j = j + 1;
    }
}

/// Read the integer value held by the qubits listed in `members`, 2's-complement LE.
pub fn read_register(ref s: State, members: @Array<u32>) -> u256 {
    let mut acc: u256 = 0;
    let mut pow: u256 = 1;
    let mut j: u32 = 0;
    while j < members.len() {
        if get_q(ref s, *members.at(j)) == 1 {
            acc = acc + pow;
        }
        pow = pow * 2;
        j = j + 1;
    }
    acc
}

#[cfg(test)]
mod tests {
    use super::{
        Inst, NO_COND, NO_TARGET, OP_CCX, OP_CX, OP_HMR, OP_NEG, OP_R, OP_X, get_q, load_register,
        new_state, next_u64, read_register, rng_new, run,
    };

    fn inst(opcode: u32, t0: u32, t1: u32, t2: u32, cond: u32) -> Inst {
        Inst { opcode, t0, t1, t2, cond }
    }

    // -- SplitMix64 cross-vector against the Rust kickmix::SplitMix64 --------

    #[test]
    fn splitmix64_matches_rust_seed0() {
        let mut rng = rng_new(0);
        assert!(next_u64(ref rng) == 0xe220a8397b1dcdaf_u64, "seed 0 first output");
    }

    #[test]
    fn splitmix64_matches_rust_seed42() {
        let mut rng = rng_new(42);
        assert!(next_u64(ref rng) == 0xbdd732262feb6e95_u64, "seed 42 first output");
    }

    // -- register I/O round-trip --------------------------------------------

    #[test]
    fn register_round_trip() {
        let mut members: Array<u32> = ArrayTrait::new();
        members.append(0);
        members.append(1);
        members.append(2);
        let mut s = new_state();
        load_register(ref s, @members, 5_u256); // 0b101
        assert!(read_register(ref s, @members) == 5_u256, "round trip");
    }

    // -- inc3: CCX / CX / X semantics match the adder behaviour --------------

    fn inc3_program() -> Array<Inst> {
        // CCX q0 q1 q2 ; CX q0 q1 ; X q0
        let mut p: Array<Inst> = ArrayTrait::new();
        p.append(inst(OP_CCX, 0, 1, 2, NO_COND));
        p.append(inst(OP_CX, 0, 1, NO_TARGET, NO_COND));
        p.append(inst(OP_X, 0, NO_TARGET, NO_TARGET, NO_COND));
        p
    }

    #[test]
    fn inc3_increments_mod_8() {
        let mut members: Array<u32> = ArrayTrait::new();
        members.append(0);
        members.append(1);
        members.append(2);
        let program = inc3_program();
        let mut v: u32 = 0;
        while v != 8 {
            let mut s = new_state();
            load_register(ref s, @members, v.into());
            let mut rng = rng_new(0); // no HMR -> rng unused
            run(ref s, ref rng, @program);
            let got = read_register(ref s, @members);
            let expected: u256 = ((v + 1) % 8).into();
            assert!(got == expected, "inc3 step");
            v = v + 1;
        }
    }

    // -- HMR phase-kickback + correction (the format spec's example) ---------

    #[test]
    fn hmr_kickback_corrected_by_neg() {
        // R q0 ; X q0 ; HMR q0 b0 ; NEG if b0  -> phase always corrected to 0.
        // Seed 0 yields first measurement bit = 1 (matches Rust), exercising the
        // kickback-then-correction path.
        let mut p: Array<Inst> = ArrayTrait::new();
        p.append(inst(OP_R, 0, NO_TARGET, NO_TARGET, NO_COND));
        p.append(inst(OP_X, 0, NO_TARGET, NO_TARGET, NO_COND));
        p.append(inst(OP_HMR, 0, 0, NO_TARGET, NO_COND)); // qubit q0 -> bit b0
        p.append(inst(OP_NEG, NO_TARGET, NO_TARGET, NO_TARGET, 0)); // NEG if b0
        let mut s = new_state();
        let mut rng = rng_new(0);
        run(ref s, ref rng, @p);
        assert!(s.phase == 0, "kickback corrected by NEG");
        assert!(get_q(ref s, 0) == 0, "q0 cleared");
    }

    #[test]
    fn hmr_kickback_uncorrected_inverts_phase() {
        // Same circuit WITHOUT the NEG correction: with measurement bit = 1 the
        // phase is left inverted (1) — the failure fuzz testing detects.
        let mut p: Array<Inst> = ArrayTrait::new();
        p.append(inst(OP_R, 0, NO_TARGET, NO_TARGET, NO_COND));
        p.append(inst(OP_X, 0, NO_TARGET, NO_TARGET, NO_COND));
        p.append(inst(OP_HMR, 0, 0, NO_TARGET, NO_COND));
        let mut s = new_state();
        let mut rng = rng_new(0); // first bit = 1
        run(ref s, ref rng, @p);
        assert!(s.phase == 1, "uncorrected kickback inverts phase");
    }
}
