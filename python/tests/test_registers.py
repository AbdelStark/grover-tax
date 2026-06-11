"""Unit tests for `grover_tax.registers` — two-register adder I/O (KB-3, #115)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from grover_tax.kmx import transpile_file
from grover_tax.registers import (
    AdderCase,
    decode_registers,
    encode_registers,
    iadd_test_cases,
    min_state_bytes,
    run_adder_case,
)

_EXAMPLE_DATA = (
    Path(__file__).resolve().parents[2] / "third_party" / "sp1" / "docs" / "example_data"
)


def _example(name: str) -> Path:
    return _EXAMPLE_DATA / name


# -- encode / decode round-trip ----------------------------------------------


def test_encode_decode_round_trip_iadd8() -> None:
    circuit = transpile_file(_example("iadd8.kmx"))
    layout = circuit.register_layout
    nbytes = min_state_bytes(circuit)
    for x, y in [(0, 0), (1, 2), (255, 255), (200, 99)]:
        state = encode_registers({"r0": x, "r1": y}, layout, nbytes)
        decoded = decode_registers(state, layout)
        assert decoded["r0"] == x
        assert decoded["r1"] == y


def test_encode_is_little_endian_lsb_first() -> None:
    """Member 0 of a register carries the least-significant bit."""
    circuit = transpile_file(_example("iadd8.kmx"))
    layout = circuit.register_layout
    # r0 = q0..q7, so value 1 lights only q0 (bit 0 of the flat state).
    state = encode_registers({"r0": 1, "r1": 0}, layout, min_state_bytes(circuit))
    assert state[0] & 0b1 == 1
    # value 0x80 (bit 7) lights q7.
    state = encode_registers({"r0": 0x80, "r1": 0}, layout, min_state_bytes(circuit))
    assert (state[0] >> 7) & 0b1 == 1


def test_encode_reduces_modulo_register_width() -> None:
    circuit = transpile_file(_example("iadd8.kmx"))
    layout = circuit.register_layout
    nbytes = min_state_bytes(circuit)
    # 256 ≡ 0 (mod 2^8); 257 ≡ 1.
    assert decode_registers(encode_registers({"r0": 256}, layout, nbytes), layout)["r0"] == 0
    assert decode_registers(encode_registers({"r0": 257}, layout, nbytes), layout)["r0"] == 1


def test_min_state_bytes() -> None:
    assert min_state_bytes(transpile_file(_example("iadd64.kmx"))) == 16  # 128 qubits
    assert min_state_bytes(transpile_file(_example("iadd8.kmx"))) == 2  # 16 qubits
    assert min_state_bytes(transpile_file(_example("inc3.kmx"))) == 1  # 3 qubits


# -- the adder actually adds -------------------------------------------------


def test_iadd64_getting_started_example() -> None:
    """getting_started.md: `iadd64 101 123` → `224 123`."""
    circuit = transpile_file(_example("iadd64.kmx"))
    assert run_adder_case(circuit, 101, 123) == (224, 123)


def test_iadd64_wraps_modulo_2_64() -> None:
    circuit = transpile_file(_example("iadd64.kmx"))
    mod = 1 << 64
    x, y = mod - 1, 5  # (2^64 - 1) + 5 = 4 (mod 2^64)
    assert run_adder_case(circuit, x, y) == ((x + y) % mod, y)


def test_iadd8_exhaustive_small_sample() -> None:
    circuit = transpile_file(_example("iadd8.kmx"))
    mod = 1 << 8
    for x in range(0, 256, 37):
        for y in range(0, 256, 53):
            assert run_adder_case(circuit, x, y) == ((x + y) % mod, y)


def test_iadd64_passes_1000_random_cases() -> None:
    """KB-3 acceptance: iadd64 passes ≥1000 random encoded cases under the sim."""
    circuit = transpile_file(_example("iadd64.kmx"))
    cases = iadd_test_cases(width=64, count=1000, seed=hashlib.sha256(b"kb3-test").digest())
    assert len(cases) == 1000
    for case in cases:
        acc, off = run_adder_case(circuit, case.x, case.y)
        assert acc == case.sum_out
        assert off == case.y


# -- deterministic test-case generator ---------------------------------------


def test_iadd_test_cases_are_deterministic() -> None:
    seed = hashlib.sha256(b"determinism").digest()
    a = iadd_test_cases(width=64, count=16, seed=seed)
    b = iadd_test_cases(width=64, count=16, seed=seed)
    assert a == b


def test_iadd_test_cases_respect_width_and_arithmetic() -> None:
    seed = hashlib.sha256(b"width").digest()
    for case in iadd_test_cases(width=8, count=64, seed=seed):
        assert isinstance(case, AdderCase)
        assert 0 <= case.x < 256
        assert 0 <= case.y < 256
        assert case.sum_out == (case.x + case.y) % 256
        assert case.width == 8


def test_iadd_test_cases_reject_bad_args() -> None:
    seed = b"\x00" * 32
    with pytest.raises(ValueError):
        iadd_test_cases(width=0, count=4, seed=seed)
    with pytest.raises(ValueError):
        iadd_test_cases(width=8, count=0, seed=seed)


def test_decode_unnamed_qubits_ignored() -> None:
    """Ancillae outside any register don't affect register decode."""
    circuit = transpile_file(_example("iadd8.kmx"))
    layout = circuit.register_layout
    state = bytearray(encode_registers({"r0": 5, "r1": 9}, layout, min_state_bytes(circuit)))
    decoded = decode_registers(bytes(state), layout)
    assert decoded == {"r0": 5, "r1": 9}
