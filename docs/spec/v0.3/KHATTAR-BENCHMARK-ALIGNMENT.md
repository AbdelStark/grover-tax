# grover-tax — Alignment with the Khattar/Google requested benchmark

**Status:** analysis input to a v0.3 scope refinement (proposed). Not yet normative.
**Date:** 2026-06-01.
**Author basis:** Tanuj Khattar email 2026-05-27; exhaustive read of the upstream
reference at `tanujkhattar/zkp_ecc` (`docs/example_data`, `docs/getting_started.md`,
`docs/kickmix_file_format.md`, `docs/kickmix_instruction_set.md`, `README.md`,
`program/`, `prover/prove.rs`, `verifier/verifier.rs`); cross-checked against our
v0.2 implementation (`third_party/sp1/program/src/main.rs`, `stwo-side/cairo/src/`,
`fixtures/v0.2.json`, `bin/apples-prove`) and the v0.3 spec corpus
(`SPEC-v0.3.md`, `SCOPE.md`, `ROADMAP.md`).

---

## 1. What Google asked for

Tanuj Khattar (Google Quantum AI), 2026-05-27:

> The benchmarks I'd be interested in would be proofs for doing a **(repeated)
> addition circuit** as explained in
> `https://github.com/tanujkhattar/zkp_ecc/tree/main/docs/example_data`.
> I'm working on updating my ZKP cairo codebase so I can directly share the
> cairo code that generates these proofs and a comparison with SP1 as a
> benchmark with you.

This is a **narrowing and concretisation** of the earlier "point-add gate net"
target. The requested workload is now:

- The **integer-addition circuit** from `docs/example_data` — concretely
  `iadd64.kmx` (a 64-bit Cuccaro adder, `r0 += r1 mod 2^64`), and its smaller
  sibling `iadd8.kmx`. "(repeated)" signals running the adder **many times** as
  the scaling knob.
- Proven with the **fuzz-testing-as-proof** strategy that the reference repo
  documents: an SP1 zkVM program executes a *kickmix simulator* over many
  test cases and certifies resource bounds.
- He will provide a **Cairo (Stwo) implementation** of the same proof so that we
  have a *direct* SP1-vs-Cairo comparison — which is exactly grover-tax's thesis.

## 2. What the reference benchmark actually is (✓ VERIFIED against the repo)

The proof statement in `tanujkhattar/zkp_ecc` is *not* "simulate(C, x_i) = y_i".
It is, precisely (`getting_started.md`, `program/`, `verifier/verifier.rs`):

> "I know a secret kickmix circuit `C` whose SHA-256 is `h`, that uses ≤ Q
> qubits, executes ≤ T non-Clifford (CCX/CCZ) gates, contains ≤ I instructions,
> and that **passes N fuzz-test cases whose inputs are derived from `h` by the
> Fiat–Shamir heuristic** (SHAKE/CSPRNG seeded by the circuit hash)."

Load-bearing properties of the reference design:

| Property | Reference (`zkp_ecc`) | Evidence |
|---|---|---|
| Circuit format | **kickmix `.kmx`** — text assembly: `X CX CCX Z CZ CCZ NEG SWAP R HMR BIT_* PUSH/POP_CONDITION REGISTER APPEND_TO_REGISTER` | `kickmix_instruction_set.md` |
| State tracked | qubits (bits) **+ a phase bit** + classical bits + condition stack | `kickmix_file_format.md` §State Space |
| Registers | `APPEND_TO_REGISTER` groups qubits into 2's-complement little-endian integers | `kickmix_file_format.md` |
| Test cases | **derived in-proof** from `H(C)` via Fiat–Shamir; prover cannot choose them | `getting_started.md` §"Using Fuzz Testing as a Proof Strategy" |
| Public outputs | `circuit_hash`, `num_samples`, `max_qubit_count`, `max_non_clifford_count`, `max_circuit_instructions`, sentinel `42` | `verifier/verifier.rs` (inlined in `getting_started.md`) |
| Verifier asserts | committed resource counts satisfy the demanded bounds | same |
| Example scale | `iadd64`: 757 ops, 128 qubits, 125 non-Clifford, **128 samples**; headline ECC: 17M ops, 1175–1425 qubits, 9024 samples | `getting_started.md`, `README.md` |
| Addition semantics | `(x, y) -> ((x+y) mod 2^64, y)`, 2's-complement little-endian | `getting_started.md` step 1; `print_iadd_cases.py` |

**Opcode usage of the requested circuits** (✓ VERIFIED by histogram):

| Circuit | Opcodes used | Needs phase/HMR? |
|---|---|---|
| `iadd64.kmx` | `CX`×502, `CCX`×125, `APPEND_TO_REGISTER`×128, `REGISTER`×2 | **No** — pure reversible classical |
| `iadd8.kmx` | `CX`×54, `CCX`×13, register metadata | **No** |
| `iadd8_with_ancillae.kmx` | `CX`, `CCX`, **`HMR`×6, `CZ`×6, `R`×6** | **Yes** — measurement-based uncomputation |

The headline point-add circuits and the qubit-efficient adder variants **do** use
`HMR`/phase. So `iadd64`/`iadd8` are reachable without phase logic; full fidelity
to the broader reference (and to "repeated addition" at qubit-efficient scale)
needs the phase-tracking simulator.

## 3. What grover-tax currently does (✓ VERIFIED against the code)

| Property | grover-tax v0.2 (shipped, measured 2.52× on 2026-05-20) |
|---|---|
| Circuit format | **GTV1** — custom binary, 4 opcodes only: `NOP NOT CNOT TOFFOLI` |
| State tracked | a single 256-bit register; **no phase, no classical bits, no conditions, no registers** |
| Workload | a **random 1024-gate XOF-derived circuit** — *not* an adder, *not* point-add (GAP-ANALYSIS §1.1) |
| Proof statement | `simulate(C, x_i)[:32] == y_i[:32]` for `n_tc` cases; commit `SHA-256(C)` (SP1) / `BLAKE2s(C)` (Stwo) |
| Test cases | **supplied in the fixture** (`x_hex`,`y_hex`); **not** Fiat–Shamir-derived in-proof |
| Public outputs | `(commitment, n_cases)` only — **no resource certification** |
| Test count | `n_samples = 4` |
| SP1 program | **freshly-authored ~130-line** GTV1 simulator, *not* the upstream kickmix fuzzer (GAP-ANALYSIS §1.4) |
| Cairo program | GTV1 gate dispatcher + Blake2s commit; bootloader-mediated prove path |

A grep for `kickmix|\.kmx|iadd|HMR|fiat.?shamir|APPEND_TO_REGISTER|num_samples|non_clifford|qubit_count`
across `python/grover_tax`, `stwo-side/cairo/src`, `bin`, and
`third_party/sp1/program/src` returns **nothing**: none of the reference's
load-bearing concepts are implemented on our side today.

## 4. Verdict — are we on the right track?

**Directionally yes; on the specific deliverable, not yet.**

On track:

- The thesis is exactly right: a single-core, no-GPU, apples-to-apples
  **SP1-vs-Stwo wall-clock ratio**. Tanuj's "comparison with SP1 as a benchmark"
  is the same axis.
- The reference SP1 repo is already **vendored** at `third_party/sp1/`.
- A working measurement harness, a Cairo gate-execution prover, a scaling-curve
  methodology (`RFC-0024`), and a rigorous spec/RFC corpus already exist.
- The v0.3 plan already commits to "the upstream Khattar/Google gate net" — the
  right *direction*, just the wrong *specific circuit*.

Not yet aligned (the gaps):

- **G1 — wrong circuit.** We measure a random 1024-gate circuit; the request is
  the `iadd` adder. v0.3's `SCOPE.md` B1 targets the *point-add* net, not the
  adder. The adder is simpler, is the explicit ask, and "repeated addition" is a
  cleaner scaling primitive than the monolithic point-add net.
- **G2 — wrong (weaker) proof statement.** Ours omits in-proof Fiat–Shamir test
  derivation and resource certification. Tanuj's verifier asserts qubit count,
  non-Clifford count, instruction count, and sample count. A number measured
  against our statement is **not directly comparable** to his.
- **G3 — no kickmix support.** No `.kmx` parser, no kickmix simulator (phase,
  `HMR`, conditions, registers) on either side. GTV1 cannot represent
  `iadd8_with_ancillae`, the qubit-efficient adders, or the point-add net.
- **G4 — divergent SP1 program.** Our SP1 side is a custom GTV1 program, not the
  upstream kickmix fuzzer. For a credible head-to-head we should run **his** SP1
  program (or a byte-faithful equivalent) so only the *prover backend* differs.
- **G5 — register I/O semantics.** Adders are two-register `(x,y) ->
  ((x+y) mod 2^n, y)` in 2's-complement little-endian; our sim is single 256-bit
  `x -> y`. Test-case encoding/decoding must follow the register layout.

None of these contradict the existing corpus; they **re-scope the v0.3 workload**
from "point-add net" to "(repeated) kickmix addition circuit", and **strengthen
the proof statement** to match the reference.

## 5. Recommended plan — two tiers

### Tier 1 — Fast first number on the *real* adder (low risk, days)

Goal: a defensible SP1-vs-Stwo ratio on `iadd64` quickly, accepting documented
divergences from the full reference statement.

- A `.kmx → GTV1` transpiler restricted to `{X→NOT, CX→CNOT, CCX→TOFFOLI}` plus
  `REGISTER`/`APPEND_TO_REGISTER` metadata (drives register I/O). Rejects any
  circuit using `Z/CZ/CCZ/HMR/NEG/SWAP/R/BIT_*/PUSH_CONDITION` (so `iadd64`,
  `iadd8` pass; `iadd8_with_ancillae` is explicitly out of Tier 1).
- Two-register test-case encoding `(x,y)->((x+y) mod 2^64, y)`, generated by a
  port of `print_iadd_cases.py`.
- **Repeated addition** = concatenate K copies of `iadd64` → `n_g ≈ 627·K` →
  the v0.3 scale ladder, on a circuit that is genuinely the requested one.
- Reuses the existing GTV1 SP1 + Cairo provers and the whole harness.
- Disclosed divergences (loud, in `RESULTS.md`): no in-proof Fiat–Shamir, no
  resource certification, classical-only subset, single-register-pair width.

### Tier 2 — Full fidelity to the reference statement (the real ask)

Goal: prove the *same statement* as `tanujkhattar/zkp_ecc`, so his Cairo code and
our number are line-comparable.

- Native `.kmx` parser + **full kickmix simulator** (qubits + phase + classical
  bits + condition stack + `HMR` phase-kickback) on **both** sides — Rust for
  SP1, Cairo for Stwo.
- **In-proof Fiat–Shamir** test-case derivation seeded by `H(C)` (SHAKE-256),
  matching `program/`.
- **Resource-certification public outputs**: `circuit_hash`, `num_samples`,
  `max_qubit_count`, `max_non_clifford_count`, `max_circuit_instructions` — and a
  verifier that asserts them (mirror `verifier/verifier.rs`).
- SP1 side runs the **upstream kickmix fuzzer** (vendored) so the only delta is
  the proving backend.
- Stwo/Cairo side: align with Tanuj's forthcoming Cairo codebase rather than
  re-deriving — coordinate so the two Cairo programs prove the identical
  statement.
- Re-pin `WORKLOAD.md` to the `iadd` circuits at the reference commit; bump the
  fixture schema to carry kmx bytes + demanded resource bounds.

## 6. Gap → issue map

Tracked under the GitHub milestone **"Khattar/Google addition-circuit
benchmark"**; epic is **#112**.

| Gap | Tier | Issue |
|---|---|---|
| G1 workload = adder + repeated-addition scaling | 1+2 | #114 (KB-2), #119 (KB-7) |
| G2 Fiat–Shamir in-proof | 2 | #121 (KB-9) |
| G2 resource-certification public outputs + verifier | 2 | #122 (KB-10) |
| G3 `.kmx` parser (classical subset) | 1 | #113 (KB-1) |
| G3 full kickmix simulator (phase/HMR/conditions) — Rust | 2 | #120 (KB-8) |
| G3 full kickmix simulator — Cairo | 2 | #123 (KB-11) |
| G4 run upstream SP1 fuzzer as the SP1 side | 2 | #124 (KB-12) |
| G5 register-aware two-register test-case I/O | 1 | #115 (KB-3) |
| repeated-addition fixture + schema bump | 1 | #116 (KB-4) |
| WORKLOAD.md re-pin to iadd@commit | 1 | #117 (KB-5) |
| Tier-1 measurement series + RESULTS with divergence disclosure | 1 | #118 (KB-6) |
| coordinate with Tanuj's Cairo program for statement-equality | 2 | #125 (KB-13) |
| methodology note / cross-check vs his SP1 numbers; share write-up | 2 | #126 (KB-14) |

## 7. Open coordination questions for Tanuj

1. Confirm the **exact circuit(s)**: `iadd64` only, or the qubit-efficient
   `iadd8_with_ancillae`-style adders (which require the phase/HMR simulator)?
2. Confirm **scale**: target `num_samples` and repetition count for the headline.
3. Confirm whether he wants us to **reuse his SP1 program verbatim** (recommended)
   or accept our equivalent.
4. Timeline for sharing the **Cairo codebase** so the two statements are aligned
   before we freeze ours.
</content>
</invoke>
