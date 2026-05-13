"""Canonical byte serialiser for the gate list `C`.

The format is binding (`docs/spec/03-data-model.md` §"Canonical byte
serialisation of `C`"). Any change here invalidates every prior fixture
file. Three independent implementations (Python here, Rust on the SP1
side, Cairo on the Stwo side) must produce byte-identical output for
the same input — the integration test (#18) asserts that.

Wire format (`GateListV1`)::

    +------+-------+-----------+
    | b"GTV1" (4)  | n_gates (u32, LE)
    +------+-------+-----------+
    | gate[0] (8 bytes)        |
    | gate[1] (8 bytes)        |
    | ...                      |
    +--------------------------+

Each `Gate` is 8 bytes::

    +----+----+-------+-------+-------+
    | opcode | _pad | target | ctrl_a | ctrl_b |
    | (u8)   | (u8) | (u16)  | (u16)  | (u16)  |
    +--------+------+--------+--------+--------+

All multi-byte fields are little-endian. `_pad` is always `0`.
`ctrl_b == 0xFFFF` is the sentinel for "control wire unused" (for
single-control gates like CNOT). `0xFFFF` is *also* valid in `ctrl_a`
for the NOT opcode (no controls). The simulator interprets the
sentinel; the serialiser does not.

Opcodes are dense small integers and are part of the contract:

    0 — NOP        (padding to a power of two; no semantic effect)
    1 — NOT        (target only)
    2 — CNOT       (target + ctrl_a)
    3 — TOFFOLI    (target + ctrl_a + ctrl_b)
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "GATE_BYTES",
    "HEADER_BYTES",
    "MAGIC",
    "UNUSED_CTRL",
    "Gate",
    "Opcode",
    "deserialise",
    "serialise",
]

MAGIC = b"GTV1"
HEADER_BYTES = 8  # 4-byte magic + 4-byte n_gates
GATE_BYTES = 8
UNUSED_CTRL = 0xFFFF  # u16 sentinel for "this control slot is not used"

# Field widths from the spec.
_U16_MAX = 0xFFFF
_U32_MAX = 0xFFFFFFFF

_GATE_STRUCT = struct.Struct("<BBHHH")  # opcode, pad, target, ctrl_a, ctrl_b
_HEADER_STRUCT = struct.Struct("<4sI")  # magic, n_gates


class Opcode(IntEnum):
    """Stable wire-format opcodes (`docs/spec/03-data-model.md`)."""

    NOP = 0
    NOT = 1
    CNOT = 2
    TOFFOLI = 3


_VALID_OPCODES = frozenset(int(op) for op in Opcode)


@dataclass(frozen=True)
class Gate:
    """One row of the gate list.

    Attributes:
        opcode: One of `Opcode.NOP`, `Opcode.NOT`, `Opcode.CNOT`,
            `Opcode.TOFFOLI`. Stored as `int` to keep the dataclass cheap to
            construct from raw integers (e.g. during deserialisation).
        target: `u16` target wire id, or `UNUSED_CTRL` for NOP padding.
        ctrl_a: `u16` first control wire, or `UNUSED_CTRL` if unused.
        ctrl_b: `u16` second control wire, or `UNUSED_CTRL` if unused.
    """

    opcode: int
    target: int
    ctrl_a: int
    ctrl_b: int


def serialise(gates: Sequence[Gate]) -> bytes:
    """Encode `gates` as `GateListV1` bytes.

    Raises:
        ValueError: If `len(gates)` exceeds the `u32` capacity, any opcode is
            not in `Opcode`, or any wire id exceeds `0xFFFF`.
    """
    n_gates = len(gates)
    if n_gates > _U32_MAX:
        raise ValueError(f"serialise: too many gates ({n_gates}); u32 max is {_U32_MAX}")

    buf = bytearray(_HEADER_STRUCT.pack(MAGIC, n_gates))
    for i, g in enumerate(gates):
        _validate_gate(g, i)
        buf += _GATE_STRUCT.pack(g.opcode, 0, g.target, g.ctrl_a, g.ctrl_b)
    return bytes(buf)


def deserialise(data: bytes) -> list[Gate]:
    """Decode `GateListV1` bytes into a list of `Gate`.

    Raises:
        ValueError: On malformed magic, declared/actual length mismatch,
            non-zero pad byte, unknown opcode, or wire-id over `0xFFFF`.
    """
    if len(data) < HEADER_BYTES:
        raise ValueError(
            f"deserialise: input too short — {len(data)} bytes, header is {HEADER_BYTES}"
        )
    magic, n_gates = _HEADER_STRUCT.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"deserialise: bad magic {magic!r}, want {MAGIC!r}")

    expected_total = HEADER_BYTES + n_gates * GATE_BYTES
    if len(data) != expected_total:
        raise ValueError(
            f"deserialise: declared n_gates={n_gates} expects {expected_total} bytes, "
            f"got {len(data)}"
        )

    gates: list[Gate] = []
    for i in range(n_gates):
        off = HEADER_BYTES + i * GATE_BYTES
        opcode, pad, target, ctrl_a, ctrl_b = _GATE_STRUCT.unpack_from(data, off)
        if pad != 0:
            raise ValueError(f"deserialise: gate {i}: pad byte must be 0, got {pad}")
        if opcode not in _VALID_OPCODES:
            raise ValueError(
                f"deserialise: gate {i}: unknown opcode {opcode}; valid: {_VALID_OPCODES}"
            )
        gates.append(Gate(opcode=opcode, target=target, ctrl_a=ctrl_a, ctrl_b=ctrl_b))
    return gates


def _validate_gate(g: Gate, index: int) -> None:
    # The opcode check also covers u8 range — `_VALID_OPCODES` is a subset of
    # `[0, 255]`, so any opcode that *would* overflow u8 is already rejected
    # here.
    if g.opcode not in _VALID_OPCODES:
        raise ValueError(
            f"serialise: gate {index}: unknown opcode {g.opcode}; valid: {_VALID_OPCODES}"
        )
    for name, value in (
        ("target", g.target),
        ("ctrl_a", g.ctrl_a),
        ("ctrl_b", g.ctrl_b),
    ):
        if not 0 <= value <= _U16_MAX:
            raise ValueError(
                f"serialise: gate {index}: {name}={value} out of u16 range [0, {_U16_MAX}]"
            )
