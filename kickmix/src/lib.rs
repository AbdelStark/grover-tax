//! Full kickmix (`.kmx`) circuit simulator — the SP1-side reference (KB-8, #120).
//!
//! The Khattar/Google benchmark proves kickmix circuits via *fuzz testing as a
//! proof strategy* (`third_party/sp1/docs/getting_started.md`): a program
//! simulates the circuit over many test cases and certifies it behaves. The
//! grover-tax v0.2 simulator handled only `{NOT, CNOT, TOFFOLI}` on a single
//! register — it cannot represent the phase/measurement instructions used by
//! `iadd8_with_ancillae`, the qubit-efficient adders, or the point-add net.
//!
//! This crate implements the **full** kickmix state machine so those circuits
//! can be proven:
//!
//! - **qubits** — one boolean per qubit index (no superposition is creatable),
//! - **phase** — a tracked sign bit negated by `Z`/`CZ`/`CCZ`/`NEG` and by
//!   `HMR` phase-kickback,
//! - **classical bits** — written by measurements and `BIT_*`,
//! - **condition stack** — `PUSH_CONDITION`/`POP_CONDITION`,
//! - **registers** — `APPEND_TO_REGISTER` groups qubits into 2's-complement
//!   little-endian integers for I/O.
//!
//! `HMR` (the X-basis demolition measurement) is modelled per the format spec
//! `§Fuzz Testing`: a random measurement result is drawn, the phase is negated
//! when the target qubit is ON and the result is ON (the "phase kickback"). A
//! correct measurement-based uncomputation cancels this kickback with
//! `Z`/`CZ`/`CCZ`/`NEG`; an incorrect one leaves the phase inverted on some
//! trajectories, which fuzz testing detects.
//!
//! Determinism / statement-equality: instruction execution is a pure function
//! of `(circuit, initial qubits, measurement-bit stream)`. Measurement bits are
//! drawn from a [`MeasureSource`]; the Cairo mirror (KB-11, #123) must consume
//! bits in the same order to stay bit-for-bit equal.

#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use std::fmt;

/// A typed circuit target: a qubit `qN`, a classical bit `bN`, or a register `rN`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Target {
    Qubit(usize),
    Bit(usize),
    Register(usize),
}

/// One parsed instruction: an upper-case name, its targets, and an optional
/// `if bN` classical condition.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Instruction {
    pub name: String,
    pub targets: Vec<Target>,
    pub condition: Option<usize>,
}

/// A parsed kickmix circuit plus the metadata needed to run and fuzz it.
#[derive(Clone, Debug, Default)]
pub struct Circuit {
    pub instructions: Vec<Instruction>,
    /// register id -> its qubit indices, least-significant first (append order).
    pub registers: BTreeMap<usize, Vec<usize>>,
    pub num_qubits: usize,
    pub num_bits: usize,
}

#[derive(Debug, PartialEq, Eq)]
pub struct ParseError {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for ParseError {}

// --------------------------------------------------------------------------
// Parsing
// --------------------------------------------------------------------------

impl Circuit {
    /// Parse a kickmix circuit from its source text (full instruction set).
    pub fn parse(text: &str) -> Result<Circuit, ParseError> {
        let mut circuit = Circuit::default();
        let mut max_qubit: isize = -1;
        let mut max_bit: isize = -1;

        for (idx, raw) in text.lines().enumerate() {
            let lineno = idx + 1;
            // Strip the comment (everything from the first '#') and indentation.
            let code = raw.split('#').next().unwrap_or("").trim();
            if code.is_empty() {
                continue;
            }

            let mut tokens = code.split_whitespace();
            let name = tokens.next().unwrap().to_string();
            if !is_valid_name(&name) {
                return Err(ParseError {
                    line: lineno,
                    message: format!("malformed instruction name {name:?}"),
                });
            }

            let rest: Vec<&str> = tokens.collect();
            let (target_toks, condition) = split_condition(&rest, lineno)?;

            let mut targets = Vec::with_capacity(target_toks.len());
            for tok in target_toks {
                let t = parse_target(tok, lineno)?;
                match t {
                    Target::Qubit(q) => max_qubit = max_qubit.max(q as isize),
                    Target::Bit(b) => max_bit = max_bit.max(b as isize),
                    Target::Register(_) => {}
                }
                targets.push(t);
            }
            if let Some(b) = condition {
                max_bit = max_bit.max(b as isize);
            }

            // Register metadata is recorded but not executed.
            update_registers(
                &name,
                &targets,
                &mut circuit.registers,
                &mut max_qubit,
                lineno,
            )?;

            circuit.instructions.push(Instruction {
                name,
                targets,
                condition,
            });
        }

        circuit.num_qubits = (max_qubit + 1) as usize;
        circuit.num_bits = (max_bit + 1) as usize;
        Ok(circuit)
    }

    /// The set membership test "is this qubit part of any declared register?".
    pub fn register_qubits(&self) -> Vec<bool> {
        let mut is_member = vec![false; self.num_qubits];
        for members in self.registers.values() {
            for &q in members {
                if q < is_member.len() {
                    is_member[q] = true;
                }
            }
        }
        is_member
    }
}

fn is_valid_name(name: &str) -> bool {
    let mut chars = name.chars();
    match chars.next() {
        Some(c) if c.is_ascii_uppercase() => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == '_')
}

fn split_condition<'a>(
    rest: &[&'a str],
    lineno: usize,
) -> Result<(Vec<&'a str>, Option<usize>), ParseError> {
    if let Some(pos) = rest.iter().position(|&t| t == "if") {
        let cond = &rest[pos + 1..];
        if cond.len() != 1 {
            return Err(ParseError {
                line: lineno,
                message: format!("`if` condition must name exactly one bit, got {cond:?}"),
            });
        }
        match parse_target(cond[0], lineno)? {
            Target::Bit(b) => Ok((rest[..pos].to_vec(), Some(b))),
            other => Err(ParseError {
                line: lineno,
                message: format!("`if` condition must be a bit, got {other:?}"),
            }),
        }
    } else {
        Ok((rest.to_vec(), None))
    }
}

fn parse_target(token: &str, lineno: usize) -> Result<Target, ParseError> {
    let (kind, rest) = token.split_at(1);
    let id: usize = rest.parse().map_err(|_| ParseError {
        line: lineno,
        message: format!("malformed target {token:?} (want q<N>/b<N>/r<N>)"),
    })?;
    match kind {
        "q" => Ok(Target::Qubit(id)),
        "b" => Ok(Target::Bit(id)),
        "r" => Ok(Target::Register(id)),
        _ => Err(ParseError {
            line: lineno,
            message: format!("malformed target {token:?} (want q<N>/b<N>/r<N>)"),
        }),
    }
}

fn update_registers(
    name: &str,
    targets: &[Target],
    registers: &mut BTreeMap<usize, Vec<usize>>,
    max_qubit: &mut isize,
    lineno: usize,
) -> Result<(), ParseError> {
    match name {
        "REGISTER" => {
            if let [Target::Register(r)] = targets {
                registers.entry(*r).or_default();
                Ok(())
            } else {
                Err(ParseError {
                    line: lineno,
                    message: "REGISTER takes exactly one register operand".into(),
                })
            }
        }
        "APPEND_TO_REGISTER" => match targets {
            [Target::Qubit(q), Target::Register(r)] => {
                registers.entry(*r).or_default().push(*q);
                *max_qubit = (*max_qubit).max(*q as isize);
                Ok(())
            }
            // Bit registers are legal in kickmix; we record qubit registers
            // (the adder I/O path) and ignore bit members for value encoding.
            [Target::Bit(_), Target::Register(r)] => {
                registers.entry(*r).or_default();
                Ok(())
            }
            _ => Err(ParseError {
                line: lineno,
                message: "APPEND_TO_REGISTER takes <qubit|bit> <register>".into(),
            }),
        },
        _ => Ok(()),
    }
}

// --------------------------------------------------------------------------
// Measurement source
// --------------------------------------------------------------------------

/// Source of the random measurement results `HMR` (and a misused `R`) consume.
///
/// Fuzz testing samples a trajectory; the measurement bits are part of that
/// trajectory. Cross-implementation equality (Rust ↔ Cairo, KB-11) requires
/// consuming bits in the same order.
pub trait MeasureSource {
    fn next_bit(&mut self) -> bool;
}

/// A small, dependency-free SplitMix64 PRNG used as the default trajectory
/// source. Deterministic given its seed.
#[derive(Clone, Debug)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        SplitMix64 { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

impl MeasureSource for SplitMix64 {
    fn next_bit(&mut self) -> bool {
        self.next_u64() & 1 == 1
    }
}

/// A fixed, replayable bit stream — useful for deterministic tests.
#[derive(Clone, Debug)]
pub struct FixedBits {
    bits: Vec<bool>,
    pos: usize,
}

impl FixedBits {
    pub fn new(bits: Vec<bool>) -> Self {
        FixedBits { bits, pos: 0 }
    }
}

impl MeasureSource for FixedBits {
    fn next_bit(&mut self) -> bool {
        let b = self.bits.get(self.pos).copied().unwrap_or(false);
        self.pos += 1;
        b
    }
}

// --------------------------------------------------------------------------
// Simulation
// --------------------------------------------------------------------------

/// Mutable simulator state: qubits, classical bits, a tracked phase, and the
/// condition stack.
#[derive(Clone, Debug)]
pub struct State {
    pub qubits: Vec<bool>,
    pub bits: Vec<bool>,
    /// `false` = +1, `true` = -1 (the phase is a single sign bit).
    pub phase: bool,
    cond_stack: Vec<bool>,
}

impl State {
    pub fn new(num_qubits: usize, num_bits: usize) -> Self {
        State {
            qubits: vec![false; num_qubits],
            bits: vec![false; num_bits],
            phase: false,
            cond_stack: Vec::new(),
        }
    }

    /// Whether a (non-control-flow, non-metadata) instruction is active: every
    /// pushed condition is true and the optional `if` bit is true.
    fn active(&self, condition: Option<usize>) -> bool {
        self.cond_stack.iter().all(|&c| c)
            && condition.map_or(true, |b| self.bits.get(b).copied().unwrap_or(false))
    }
}

/// Run `circuit` from initial `state`, drawing measurement results from
/// `measure`. Mutates `state` in place.
pub fn run(circuit: &Circuit, state: &mut State, measure: &mut dyn MeasureSource) {
    for inst in &circuit.instructions {
        step(inst, state, measure);
    }
}

fn q(targets: &[Target], i: usize) -> usize {
    match targets[i] {
        Target::Qubit(x) => x,
        other => panic!("expected qubit target, got {other:?}"),
    }
}

fn step(inst: &Instruction, state: &mut State, measure: &mut dyn MeasureSource) {
    let t = &inst.targets;
    match inst.name.as_str() {
        // Control flow and metadata ignore the condition stack.
        "PUSH_CONDITION" => {
            let bit = inst.condition.expect("PUSH_CONDITION requires `if bN`");
            state
                .cond_stack
                .push(state.bits.get(bit).copied().unwrap_or(false));
            return;
        }
        "POP_CONDITION" => {
            state.cond_stack.pop();
            return;
        }
        "REGISTER" | "APPEND_TO_REGISTER" | "DEBUG_PRINT" => return,
        _ => {}
    }

    if !state.active(inst.condition) {
        return;
    }

    match inst.name.as_str() {
        "X" => {
            let a = q(t, 0);
            state.qubits[a] ^= true;
        }
        "CX" => {
            let (c, tg) = (q(t, 0), q(t, 1));
            state.qubits[tg] ^= state.qubits[c];
        }
        "CCX" => {
            let (c1, c2, tg) = (q(t, 0), q(t, 1), q(t, 2));
            state.qubits[tg] ^= state.qubits[c1] && state.qubits[c2];
        }
        "Z" => {
            let a = q(t, 0);
            if state.qubits[a] {
                state.phase ^= true;
            }
        }
        "CZ" => {
            let (a, b) = (q(t, 0), q(t, 1));
            if state.qubits[a] && state.qubits[b] {
                state.phase ^= true;
            }
        }
        "CCZ" => {
            let (a, b, c) = (q(t, 0), q(t, 1), q(t, 2));
            if state.qubits[a] && state.qubits[b] && state.qubits[c] {
                state.phase ^= true;
            }
        }
        "NEG" => {
            state.phase ^= true;
        }
        "SWAP" => {
            let (a, b) = (q(t, 0), q(t, 1));
            state.qubits.swap(a, b);
        }
        "R" => {
            // Reset to |0>. Resetting a |1> randomizes the phase — a misuse the
            // fuzzer is meant to catch — so consume a trajectory bit then.
            let a = q(t, 0);
            if state.qubits[a] && measure.next_bit() {
                state.phase ^= true;
            }
            state.qubits[a] = false;
        }
        "HMR" => {
            // X-basis demolition measurement: random result, phase kickback if
            // the qubit was ON and the result is ON, then reset to |0>.
            let qb = q(t, 0);
            let bit = match t[1] {
                Target::Bit(b) => b,
                other => panic!("HMR output must be a bit, got {other:?}"),
            };
            let m = measure.next_bit();
            if state.qubits[qb] && m {
                state.phase ^= true;
            }
            state.bits[bit] = m;
            state.qubits[qb] = false;
        }
        "BIT_INVERT" => {
            if let Target::Bit(b) = t[0] {
                state.bits[b] ^= true;
            }
        }
        "BIT_STORE0" => {
            if let Target::Bit(b) = t[0] {
                state.bits[b] = false;
            }
        }
        "BIT_STORE1" => {
            if let Target::Bit(b) = t[0] {
                state.bits[b] = true;
            }
        }
        other => panic!("unknown instruction {other:?}"),
    }
}

// --------------------------------------------------------------------------
// Register I/O + fuzzing
// --------------------------------------------------------------------------

/// Write `value` into `register`'s qubits, 2's-complement little-endian.
pub fn load_register(state: &mut State, circuit: &Circuit, register: usize, value: u128) {
    if let Some(members) = circuit.registers.get(&register) {
        for (j, &qidx) in members.iter().enumerate() {
            state.qubits[qidx] = (value >> j) & 1 == 1;
        }
    }
}

/// Read `register`'s value, 2's-complement little-endian (as an unsigned residue).
pub fn read_register(state: &State, circuit: &Circuit, register: usize) -> u128 {
    let mut value: u128 = 0;
    if let Some(members) = circuit.registers.get(&register) {
        for (j, &qidx) in members.iter().enumerate() {
            if state.qubits[qidx] {
                value |= 1u128 << j;
            }
        }
    }
    value
}

/// One fuzz case: input register values and the expected output register values
/// (both in ascending register-id order).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FuzzCase {
    pub inputs: Vec<u128>,
    pub outputs: Vec<u128>,
}

/// Why a fuzz trajectory failed — mirrors upstream `example_fuzz`'s diagnostics.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FuzzFailure {
    /// A register held the wrong value at the end.
    WrongOutput {
        register: usize,
        expected: u128,
        got: u128,
    },
    /// An ancillary qubit (not part of any register) was left non-zero.
    UnclearedAncilla { qubit: usize },
    /// The tracked phase ended inverted (uncorrected HMR kickback).
    InvertedPhase,
}

impl fmt::Display for FuzzFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            FuzzFailure::WrongOutput {
                register,
                expected,
                got,
            } => {
                write!(f, "register r{register}: expected {expected}, got {got}")
            }
            FuzzFailure::UnclearedAncilla { qubit } => {
                write!(f, "ancillary qubit q{qubit} not cleared to 0")
            }
            FuzzFailure::InvertedPhase => write!(f, "inverted phase"),
        }
    }
}

/// Run one trajectory of `case` and return the failure (if any).
pub fn check_case(
    circuit: &Circuit,
    case: &FuzzCase,
    measure: &mut dyn MeasureSource,
) -> Option<FuzzFailure> {
    let mut state = State::new(circuit.num_qubits, circuit.num_bits);
    for (i, &reg) in circuit.registers.keys().enumerate() {
        let value = case.inputs.get(i).copied().unwrap_or(0);
        load_register(&mut state, circuit, reg, value);
    }

    run(circuit, &mut state, measure);

    for (i, &reg) in circuit.registers.keys().enumerate() {
        let expected = case.outputs.get(i).copied().unwrap_or(0);
        let width = circuit.registers[&reg].len();
        let mask = if width >= 128 {
            u128::MAX
        } else {
            (1u128 << width) - 1
        };
        let got = read_register(&state, circuit, reg);
        if got != (expected & mask) {
            return Some(FuzzFailure::WrongOutput {
                register: reg,
                expected: expected & mask,
                got,
            });
        }
    }

    let is_member = circuit.register_qubits();
    for (qubit, &on) in state.qubits.iter().enumerate() {
        if on && !is_member.get(qubit).copied().unwrap_or(false) {
            return Some(FuzzFailure::UnclearedAncilla { qubit });
        }
    }

    if state.phase {
        return Some(FuzzFailure::InvertedPhase);
    }
    None
}

/// Fuzz `circuit` against `cases`, running `shots_per_case` random trajectories
/// each. Returns `Ok(total_shots)` on full success, or `Err((case_index, failure))`
/// at the first failing trajectory. `seed` makes the run reproducible.
pub fn fuzz(
    circuit: &Circuit,
    cases: &[FuzzCase],
    shots_per_case: usize,
    seed: u64,
) -> Result<usize, (usize, FuzzFailure)> {
    let mut rng = SplitMix64::new(seed);
    let mut total = 0;
    for (ci, case) in cases.iter().enumerate() {
        for _ in 0..shots_per_case {
            // A fresh measure source per shot, advanced deterministically from
            // the master rng, so each trajectory is independent yet reproducible.
            let mut measure = SplitMix64::new(rng.next_u64());
            if let Some(failure) = check_case(circuit, case, &mut measure) {
                return Err((ci, failure));
            }
            total += 1;
        }
    }
    Ok(total)
}
