# RFC-0003: Reference simulator (Python reimplementation of `sim.rs`)

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

`python/grover_tax/sim_reference.py` is a Python reimplementation of `tanujkhattar/zkp_ecc/lib/src/sim.rs`'s gate-by-gate simulator. It serves as the cross-validation oracle for `gen_fixtures.py`: every fixture test case `(x_i, y_i)` must satisfy `sim_reference.run(C, x_i) == y_i` *and* equal `coincurve.add(*x_i)`. The reference simulator is also used as the test oracle for both prover-side implementations (Cairo and Rust) when debugging witness construction.

## Motivation

If the Stwo and SP1 sides each have their own gate-execution implementation, an undetected divergence between them can produce a proof on one side that the other side cannot match. The cheap, fast, third-party-verifiable Python implementation is the tie-breaker.

It also documents the gate semantics in a high-level language so a reviewer does not need to read `sim.rs` to understand what `C` computes.

## Goals

- Bit-exact gate semantics matching `sim.rs` at the pinned upstream commit.
- Pure-functional API: `(C, x) → y` with no global state, no I/O, no time-dependence.
- 100% line coverage in unit tests.
- Performance acceptable for `N ≤ 1024` test cases (the maximum we plan to ship for `v0.1`).
- Type-checked under `mypy --strict`.

## Non-Goals

- Performance parity with Rust. The reference is correctness-load-bearing, not speed-load-bearing.
- Multiple gate-encoding schemes. We support exactly the canonical serialisation of `RFC-0004`.
- A general-purpose ZK simulator. This is scoped to NOT/CNOT/Toffoli on bit-vectors.

## Proposed Design

### API

```python
# python/grover_tax/sim_reference.py

from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True)
class Gate:
    opcode: int   # 0=NOP, 1=NOT, 2=CNOT, 3=TOFFOLI
    target: int   # bit index
    ctrl_a: int   # bit index, or 0xFFFF if unused
    ctrl_b: int   # bit index, or 0xFFFF if unused

class BitVector:
    """A 256-bit (or W*9-bit if so configured) bit-vector with bit-level access."""
    def __init__(self, bits: bytes): ...
    def get(self, i: int) -> int: ...
    def set(self, i: int, v: int) -> None: ...
    def to_bytes(self) -> bytes: ...

def step(state: BitVector, gate: Gate) -> None:
    """Apply one gate, mutating state."""
    if gate.opcode == 0:        # NOP
        return
    if gate.opcode == 1:        # NOT
        state.set(gate.target, state.get(gate.target) ^ 1)
        return
    if gate.opcode == 2:        # CNOT
        c = state.get(gate.ctrl_a)
        state.set(gate.target, state.get(gate.target) ^ c)
        return
    if gate.opcode == 3:        # TOFFOLI
        c = state.get(gate.ctrl_a) & state.get(gate.ctrl_b)
        state.set(gate.target, state.get(gate.target) ^ c)
        return
    raise ValueError(f"unknown opcode {gate.opcode}")

def run(C: Sequence[Gate], x: bytes) -> bytes:
    """Execute C on initial state x, return final state."""
    state = BitVector(x)
    for gate in C:
        step(state, gate)
    return state.to_bytes()
```

### Semantics binding

The gate semantics above are normative. They match `sim.rs` at the pinned upstream commit (`upstream_commit` in `WORKLOAD.md`). If `sim.rs` semantics differ at a future upstream commit, the difference is a *re-pin*, not a fix to `sim_reference.py`; the workload version bumps and the prior `results/` are archived.

### Bit ordering and state layout

256-bit state. Bit `i` lives at byte `i // 8`, bit-position `i % 8` (little-endian within byte). This must match:

- the Python serialiser of `x_hex` in the fixture (`gen_fixtures.py`),
- the Cairo program's bit-vector layout in `stwo-side/circuit.cairo` (RFC-0004),
- the Rust witness construction on the SP1 side.

A single test, `T-bit-layout`, asserts all three layouts agree on a known input vector.

### Performance envelope

- `N * |C| * |gate_cost|` for one full fixture cross-validation.
- For `N ≤ 1024` and `|C| ≤ 10^7` (the expected order of magnitude per PRD §3), Python execution is in the seconds-to-low-minutes range.
- The reference simulator runs at `gen-fixtures` time and at test time, *not* during measured runs. Its performance is bounded only by CI patience.

### Tooling

- `mypy --strict` clean.
- `ruff` clean with `select = ["E", "F", "I", "B", "UP", "PL", "RUF"]`.
- 100% line coverage; CI fails on a coverage gap.

## Alternatives Considered

### A1. Use the upstream `sim.rs` directly via PyO3 bindings

Build `sim.rs` as a Python extension. Rejected:

- Adds a build-time C/Rust dependency to the Python side, breaking the lightweight `uv sync --frozen` story.
- Couples the Python pipeline to the upstream's Rust API, which may change.
- Defeats the purpose of having a *third* independent implementation.

### A2. Skip the Python implementation; trust `sim.rs`

Rejected: a fixture's correctness depends on the gate semantics. If the only check is "run it through `sim.rs`", a `sim.rs` bug propagates undetected. The Python implementation is the fault-isolation mechanism.

### A3. Implement in NumPy with vectorised bit operations

Faster but obscures the gate-by-gate semantics. Since the simulator is not on the hot path, clarity wins.

### A4. Implement in C with ctypes

Faster. Rejected for the same reason as A1 (build-complexity, opacity).

## Drawbacks

- Maintenance burden if upstream `sim.rs` semantics evolve. Mitigated by: pinned upstream commit, re-pin discipline.
- Performance: Python is slow. For `N * |C| ≥ 10^9` ops, the fixture-generation step could take minutes. Acceptable; not on the measured path.

## Migration / Rollout

First implementation. No migration. The reference simulator is a prerequisite for `gen-fixtures`.

## Testing Strategy

- **R-T1**: Unit tests for each opcode (NOP, NOT, CNOT, Toffoli) over all 2/4/8-bit inputs.
- **R-T2**: Sequence test: a hand-constructed `C` that performs a known transformation (e.g., 8-bit increment), assert correctness over all 256 inputs.
- **R-T3**: Cross-validate against `coincurve` for `secp256k1` point-addition: build `C` for one point-add, run on 100 random test cases, assert result equals `coincurve` reference.
- **R-T4**: Bit-layout interop test (`T-bit-layout`) — same `x` bytes produce same bit-by-bit layout in Python, Rust serialiser, and Cairo.
- **R-T5**: Property test (Hypothesis): random `C` over random initial state, assert that `run(C + [NOP], x) == run(C, x)` (NOP invariance).
- **R-T6**: Property test: `run(C, x)` is deterministic — repeated invocations on the same `(C, x)` produce equal bytes.
- **R-T7**: Coverage gate: CI fails if line coverage drops below 100%.

## Open Questions

None for `v0.1`. Performance optimisation is deferred to post-`v0.1` if it ever blocks.

## References

- `python/grover_tax/sim_reference.py` (this file's product)
- Upstream: `tanujkhattar/zkp_ecc/lib/src/sim.rs` at `WORKLOAD.md.upstream_commit`
- `RFC-0002` (fixture generator consumer)
- `RFC-0004` (Cairo bit layout that must match)
- `docs/spec/07-testing-strategy.md` (Layer 1, 2 tests)
