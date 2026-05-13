// grover-tax v0.1 — Cairo gate-execution circuit (Stwo side).
//
// Entry-point signature per RFC-0004 §"Proposed Design":
//
//   fn main(
//       public_test_cases: Array<TestCase>,
//       public_h_c: [u8; 32],
//       secret_c: Array<Gate>,
//   ) {
//       // a. Range-check all gate fields (#21).
//       // b. For each test case, simulate (#20..#22).
//       // c. Blake2s commitment check against public_h_c (#23).
//   }
//
// The Cairo body is filled in incrementally by:
//   #20 — M31 9-limb 256-bit arithmetic + get_bit/set_bit.
//   #21 — Gate dispatcher with constant-cost step().
//   #22 — Canonical byte serialisation + NOP padding.
//   #23 — In-circuit Blake2s commitment check.
//   #24 — Cairo unit-test suite C-T1..C-T8.
//
// This skeleton compiles and exposes the signature so the rest of the
// project can reference module shapes that exist on disk.

pub mod limbs;

#[derive(Drop, Copy)]
pub struct Gate {
    pub opcode: u32,
    pub target: u32,
    pub ctrl_a: u32,
    pub ctrl_b: u32,
}

#[derive(Drop, Copy)]
pub struct TestCase {
    // x_hex is encoded as two 32-byte chunks (see fixture schema).
    pub x_lo: u256,
    pub x_hi: u256,
    pub y: u256,
}

pub const NO_CTRL: u32 = 0xFFFF;

// NOP opcode — the only one the skeleton needs to reference today;
// the full enum lands with #21.
pub const OP_NOP: u32 = 0;
pub const OP_NOT: u32 = 1;
pub const OP_CNOT: u32 = 2;
pub const OP_TOFFOLI: u32 = 3;

// Skeleton entry point. The real circuit body lands incrementally
// across #20..#23. Today this function exists so `scarb build` succeeds
// against the project layout.
fn main(
    public_test_cases: Array<TestCase>,
    public_h_c: u256,
    secret_c: Array<Gate>,
) {
    // Touch every parameter so the compiler doesn't drop them in the stub.
    let _ = public_test_cases.len();
    let _ = public_h_c;
    let _ = secret_c.len();
}
