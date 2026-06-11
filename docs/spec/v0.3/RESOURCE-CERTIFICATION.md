# Resource certification

**Status:** normative for the Tier-2 Khattar-benchmark statement (KB-10, #122).
**Companion:** `KHATTAR-BENCHMARK-ALIGNMENT.md` §2 (G2),
`third_party/sp1/verifier/verifier.rs`, `getting_started.md`.

## What and why

The reference verifier asserts more than "the circuit passed its fuzz tests": it
certifies the circuit's **resource usage** stays within demanded bounds, so a
prover cannot pass a trivially-small or pathological circuit. The prover commits
the circuit's counts as public outputs; the verifier checks them against the
bounds the fixture demands.

## Public-output layout

The prover commits, in order:

```
circuit_hash, num_samples, max_qubit_count, max_non_clifford_count,
max_circuit_instructions, 42
```

The trailing `42` is the upstream sentinel. The five integer outputs are
produced by `public_outputs()` in each stack; `circuit_hash` is the SHA-256 over
the raw `.kmx` bytes (`COMMITMENT-POLICY.md`).

## Verifier assertions

`certify()` (identical comparisons on all three stacks):

| Field | Rule |
|---|---|
| `num_samples` | committed **≥** demanded (at least N cases were run) |
| `max_qubit_count` | committed **≤** demanded |
| `max_non_clifford_count` | committed **≤** demanded |
| `max_circuit_instructions` | committed **≤** demanded |
| sentinel | committed **==** `42` |

A circuit exceeding any cap, or running too few samples, is rejected.

## Counting

For `iadd64` the certified counts are **128 qubits, 125 non-Clifford, 757
instructions** — the upstream figures.

- **qubit count** = one past the largest `qN` index.
- **non-Clifford count** = number of `CCX`/`CCZ` gates (the T-count proxy).
- **instruction count** = the **kickmix** instruction count, which **includes**
  the `REGISTER`/`APPEND_TO_REGISTER` metadata lines: `502 CX + 125 CCX +
  128 APPEND + 2 REGISTER = 757`.

### Note: 627 vs 757

The GTV1 gate list (KB-1) has only `{NOP, NOT, CNOT, TOFFOLI}` — no metadata
opcodes — so its gate count is **627** (`502 + 125`). The kickmix instruction
count is **757** (it counts the register-metadata lines, as upstream does).
Resource certification uses the **kickmix** count (757) to match the reference
verifier. Accordingly, the Tier-2 fixture's `demanded_max_circuit_instructions`
should be set to **757**, not the GTV1 gate count 627 that the Tier-1
`v0.3-iadd` fixture (KB-4/#116) currently records. Reconcile when the KB-4 and
KB-10 branches merge.

## Implementations

| Stack | Implementation |
|---|---|
| SP1 (Rust) | `kickmix::resource` — `count_resources`, `public_outputs`, `certify` |
| Stwo (Cairo) | `stwo-side/cairo/src/kickmix.cairo` — `ResourceCounts`/`DemandedBounds`/`certify` |
| Harness (Python) | `grover_tax.resource_cert` + `bin/apples-verify` (`uv run apples-verify`) |

All three reject a circuit exceeding any demanded bound and accept a conforming
one, verified by their respective test suites.
