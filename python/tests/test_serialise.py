"""Tests for `grover_tax.serialise`."""

from __future__ import annotations

import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from grover_tax.serialise import (
    GATE_BYTES,
    HEADER_BYTES,
    MAGIC,
    UNUSED_CTRL,
    Gate,
    Opcode,
    deserialise,
    serialise,
)


def _gate_strategy() -> st.SearchStrategy[Gate]:
    return st.builds(
        Gate,
        opcode=st.sampled_from([int(op) for op in Opcode]),
        target=st.integers(min_value=0, max_value=0xFFFF),
        ctrl_a=st.integers(min_value=0, max_value=0xFFFF),
        ctrl_b=st.integers(min_value=0, max_value=0xFFFF),
    )


def test_constants_match_spec() -> None:
    assert MAGIC == b"GTV1"
    assert HEADER_BYTES == 8
    assert GATE_BYTES == 8
    assert UNUSED_CTRL == 0xFFFF


def test_opcodes_are_dense_small_integers() -> None:
    assert int(Opcode.NOP) == 0
    assert int(Opcode.NOT) == 1
    assert int(Opcode.CNOT) == 2
    assert int(Opcode.TOFFOLI) == 3


def test_empty_gate_list_serialises_to_header_only() -> None:
    encoded = serialise([])
    assert encoded == MAGIC + b"\x00\x00\x00\x00"
    assert len(encoded) == HEADER_BYTES
    assert deserialise(encoded) == []


def test_regression_vector_four_gates() -> None:
    """Hand-computed 4-gate vector. If this changes the format has drifted."""
    gates = [
        Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.CNOT, target=1, ctrl_a=0, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.TOFFOLI, target=2, ctrl_a=0, ctrl_b=1),
        Gate(opcode=Opcode.NOP, target=UNUSED_CTRL, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL),
    ]
    encoded = serialise(gates)
    expected = (
        b"GTV1"  # magic
        + b"\x04\x00\x00\x00"  # n_gates = 4 (LE)
        + b"\x01\x00\x00\x00\xff\xff\xff\xff"  # NOT t=0, a=ff ff, b=ff ff
        + b"\x02\x00\x01\x00\x00\x00\xff\xff"  # CNOT t=1, a=0, b=ff ff
        + b"\x03\x00\x02\x00\x00\x00\x01\x00"  # TOFFOLI t=2, a=0, b=1
        + b"\x00\x00\xff\xff\xff\xff\xff\xff"  # NOP t=ff ff, a=ff ff, b=ff ff
    )
    assert encoded == expected
    assert deserialise(encoded) == gates


@given(st.lists(_gate_strategy(), max_size=64))
def test_round_trip_property(gates: list[Gate]) -> None:
    """The acceptance bullet: random gate lists round-trip identically."""
    encoded = serialise(gates)
    decoded = deserialise(encoded)
    assert decoded == gates
    # Re-serialising the decoded list must produce the same bytes (byte stability).
    assert serialise(decoded) == encoded


@given(_gate_strategy())
def test_single_gate_record_is_eight_bytes(g: Gate) -> None:
    encoded = serialise([g])
    assert len(encoded) == HEADER_BYTES + GATE_BYTES


def test_unknown_opcode_rejected_at_serialise() -> None:
    bad = Gate(opcode=42, target=0, ctrl_a=0, ctrl_b=0)
    with pytest.raises(ValueError, match="unknown opcode 42"):
        serialise([bad])


def test_out_of_range_wire_rejected_at_serialise() -> None:
    bad = Gate(opcode=Opcode.NOT, target=0x10000, ctrl_a=0, ctrl_b=0)
    with pytest.raises(ValueError, match="out of u16 range"):
        serialise([bad])


def test_out_of_range_opcode_rejected_at_serialise() -> None:
    """Opcodes that are valid IntEnum values would round-trip, but values out
    of the u8 range never can. We guard against both kinds of garbage."""
    bad = Gate(opcode=300, target=0, ctrl_a=0, ctrl_b=0)
    # The unknown-opcode check fires first; assert the *category* not the
    # exact substring.
    with pytest.raises(ValueError):
        serialise([bad])


def test_negative_wire_rejected() -> None:
    bad = Gate(opcode=Opcode.NOT, target=-1, ctrl_a=0, ctrl_b=0)
    with pytest.raises(ValueError, match="out of u16 range"):
        serialise([bad])


def test_too_many_gates_rejected() -> None:
    """Edge case: u32 overflow at the n_gates field. We can't materialise
    that many gates in a test, so we monkey-patch len()."""

    class _Faux:
        def __len__(self) -> int:
            return 1 << 32

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(())

    with pytest.raises(ValueError, match="too many gates"):
        serialise(_Faux())  # type: ignore[arg-type]


def test_bad_magic_rejected() -> None:
    bad = b"XXXX" + (0).to_bytes(4, "little")
    with pytest.raises(ValueError, match="bad magic"):
        deserialise(bad)


def test_input_too_short_rejected() -> None:
    with pytest.raises(ValueError, match="too short"):
        deserialise(b"GTV")


def test_length_mismatch_rejected() -> None:
    """Declared n_gates says 2 but only 1 gate follows."""
    header = MAGIC + (2).to_bytes(4, "little")
    one_gate = struct.pack("<BBHHH", int(Opcode.NOT), 0, 0, UNUSED_CTRL, UNUSED_CTRL)
    with pytest.raises(ValueError, match="expects"):
        deserialise(header + one_gate)


def test_non_zero_pad_rejected() -> None:
    header = MAGIC + (1).to_bytes(4, "little")
    bad = struct.pack("<BBHHH", int(Opcode.NOT), 1, 0, UNUSED_CTRL, UNUSED_CTRL)  # pad=1
    with pytest.raises(ValueError, match="pad byte must be 0"):
        deserialise(header + bad)


def test_unknown_opcode_at_deserialise_rejected() -> None:
    header = MAGIC + (1).to_bytes(4, "little")
    bad = struct.pack("<BBHHH", 99, 0, 0, UNUSED_CTRL, UNUSED_CTRL)
    with pytest.raises(ValueError, match="unknown opcode 99"):
        deserialise(header + bad)
