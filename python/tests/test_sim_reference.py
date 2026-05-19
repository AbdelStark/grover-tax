"""Tests for `grover_tax.sim_reference`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from grover_tax.errors import FIXTURE_EXIT_CODE
from grover_tax.serialise import UNUSED_CTRL, Gate, Opcode, serialise
from grover_tax.sim_reference import BitVector, main, run, step

# -- BitVector -----------------------------------------------------------------


def test_bitvector_length_is_bits_not_bytes() -> None:
    assert len(BitVector(b"\x00")) == 8
    assert len(BitVector(b"\x00\x00")) == 16
    assert len(BitVector(b"\x00" * 32)) == 256


def test_bitvector_get_lsb_first() -> None:
    """`b"\\x01"` is bit 0 set, bits 1-7 clear (LSB-first within byte)."""
    bv = BitVector(b"\x01")
    assert bv.get(0) == 1
    for i in range(1, 8):
        assert bv.get(i) == 0


def test_bitvector_set_round_trips() -> None:
    bv = BitVector(b"\x00\x00\x00\x00")
    for i in range(0, 32, 3):
        bv.set(i, 1)
    for i in range(32):
        assert bv.get(i) == (1 if i % 3 == 0 else 0)


def test_bitvector_set_zero_clears_bit() -> None:
    bv = BitVector(b"\xff")
    bv.set(3, 0)
    assert bv.get(3) == 0
    assert bv.get(0) == 1
    assert bv.get(7) == 1


def test_bitvector_to_bytes_round_trips() -> None:
    data = b"\xde\xad\xbe\xef"
    assert BitVector(data).to_bytes() == data


def test_bitvector_get_out_of_range_raises() -> None:
    bv = BitVector(b"\x00")
    with pytest.raises(IndexError):
        bv.get(-1)
    with pytest.raises(IndexError):
        bv.get(8)


def test_bitvector_set_out_of_range_index_raises() -> None:
    bv = BitVector(b"\x00")
    with pytest.raises(IndexError):
        bv.set(8, 1)


def test_bitvector_set_bad_value_raises() -> None:
    bv = BitVector(b"\x00")
    with pytest.raises(ValueError, match="must be 0 or 1"):
        bv.set(0, 2)


# -- Per-opcode unit tests (R-T1) ----------------------------------------------


@pytest.mark.parametrize("initial", range(2))
def test_step_nop_is_identity(initial: int) -> None:
    bv = BitVector(b"\x00")
    bv.set(0, initial)
    step(bv, Gate(opcode=Opcode.NOP, target=UNUSED_CTRL, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL))
    assert bv.get(0) == initial


@pytest.mark.parametrize("initial", range(2))
def test_step_not_flips_target(initial: int) -> None:
    bv = BitVector(b"\x00")
    bv.set(0, initial)
    step(bv, Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL))
    assert bv.get(0) == 1 - initial


@pytest.mark.parametrize(
    ("ctrl", "tgt", "expected"),
    [(0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0)],
)
def test_step_cnot_truth_table(ctrl: int, tgt: int, expected: int) -> None:
    bv = BitVector(b"\x00\x00")
    bv.set(0, ctrl)
    bv.set(8, tgt)
    step(bv, Gate(opcode=Opcode.CNOT, target=8, ctrl_a=0, ctrl_b=UNUSED_CTRL))
    assert bv.get(8) == expected
    assert bv.get(0) == ctrl  # control is untouched


@pytest.mark.parametrize("a", range(2))
@pytest.mark.parametrize("b", range(2))
@pytest.mark.parametrize("t", range(2))
def test_step_toffoli_truth_table(a: int, b: int, t: int) -> None:
    expected = t ^ (a & b)
    bv = BitVector(b"\x00\x00\x00")
    bv.set(0, a)
    bv.set(8, b)
    bv.set(16, t)
    step(bv, Gate(opcode=Opcode.TOFFOLI, target=16, ctrl_a=0, ctrl_b=8))
    assert bv.get(16) == expected
    assert bv.get(0) == a
    assert bv.get(8) == b


def test_step_unknown_opcode_raises() -> None:
    bv = BitVector(b"\x00")
    with pytest.raises(ValueError, match="unknown opcode"):
        step(bv, Gate(opcode=7, target=0, ctrl_a=0, ctrl_b=0))


# -- run() ---------------------------------------------------------------------


def test_run_empty_circuit_is_identity() -> None:
    x = b"\xde\xad\xbe\xef"
    assert run([], x) == x


def test_run_eight_bit_increment_sequence() -> None:
    """R-T2: a hand-constructed C that increments an 8-bit integer.

    The classic ripple increment over wires 0..7: for each bit b, flip b
    if all lower bits are 1 (cumulative product). Tested over all 256
    starting values.

    We synthesise the cumulative-AND via a chain of TOFFOLIs into
    helper wires 8..14:
        h_0 = w_0
        h_k = h_{k-1} AND w_k          for k = 1..6
    Then for each output wire k = 1..7, flip w_k if h_{k-1} = 1.
    Wire 0 always flips (it's the lowest bit).

    Total bit-vector width: 15 (8 data + 7 helpers).
    """
    gates: list[Gate] = []
    # Initialise helpers h_0 = w_0 (CNOT w_0 -> h_0, h_0 starts at 0).
    gates.append(Gate(opcode=Opcode.CNOT, target=8, ctrl_a=0, ctrl_b=UNUSED_CTRL))
    # h_k = h_{k-1} AND w_k via TOFFOLI(target=h_k, ctrl_a=h_{k-1}, ctrl_b=w_k).
    for k in range(1, 7):
        gates.append(Gate(opcode=Opcode.TOFFOLI, target=8 + k, ctrl_a=7 + k, ctrl_b=k))
    # Output bits: flip w_k if h_{k-1}; flip w_0 unconditionally (low bit always toggles).
    gates.append(Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL))
    for k in range(1, 8):
        gates.append(Gate(opcode=Opcode.CNOT, target=k, ctrl_a=7 + k, ctrl_b=UNUSED_CTRL))

    for v in range(256):
        # Pack v into 15 bits with the upper 7 helper bits zero.
        data = bytes([v, 0, 0])
        out = run(gates, data)
        expected_v = (v + 1) & 0xFF
        assert out[0] == expected_v, f"increment({v}) = {out[0]}, want {expected_v}"


# -- Property tests (R-T5, R-T6) -----------------------------------------------


@given(
    st.binary(min_size=4, max_size=8),
    st.integers(min_value=0, max_value=7),
    st.integers(min_value=0, max_value=7),
    st.integers(min_value=0, max_value=7),
)
def test_nop_invariance(x: bytes, target: int, ctrl_a: int, ctrl_b: int) -> None:
    """R-T5: appending a NOP changes nothing."""
    gates = [
        Gate(opcode=Opcode.NOT, target=target, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.CNOT, target=target, ctrl_a=ctrl_a, ctrl_b=UNUSED_CTRL),
    ]
    nop = Gate(opcode=Opcode.NOP, target=UNUSED_CTRL, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL)
    assert run([*gates, nop], x) == run(gates, x)
    assert run([nop, *gates], x) == run(gates, x)


@given(st.binary(min_size=4, max_size=8))
def test_run_is_deterministic(x: bytes) -> None:
    """R-T6: repeated invocations on the same (C, x) produce equal bytes."""
    gates = [
        Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.CNOT, target=1, ctrl_a=0, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.TOFFOLI, target=2, ctrl_a=0, ctrl_b=1),
    ]
    a = run(gates, x)
    b = run(gates, x)
    assert a == b


def test_run_does_not_mutate_input_bytes() -> None:
    """`run(C, x)` is pure: `x` is not aliased into the returned bytes."""
    x = b"\xff\xff"
    out = run([Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL)], x)
    assert x == b"\xff\xff"  # input untouched
    assert out != x


# -- main() entry point --------------------------------------------------------


def _write_fake_fixture(path: Path, gates: list[Gate], cases: list[tuple[str, str]]) -> None:
    """Write a v0.2 fixture-shaped JSON with arbitrary gate list + test cases.

    Uses `version: "v0.2"` so `sim_reference._verify_fixture` takes the
    F-INV-4-active path (full `run(C, x[:32]) == y` cross-check). The v0.1
    path intentionally skips F-INV-4 (legacy point-add proxy) and would
    accept a tampered fixture; we want the test to exercise the active
    verification path.
    """
    fixture = {
        "version": "v0.2",
        "generator_commit": "0" * 40,
        "workload_pin_commit": "1" * 40,
        "seed_hex": "2" * 64,
        "n_samples": len(cases),
        "bit_stripe_width": 64,
        "circuit_serialisation_format_version": 1,
        "circuit_byte_serialisation_hex": serialise(gates).hex(),
        "circuit_commitment_sha256_hex": "3" * 64,
        "circuit_commitment_blake2s_hex": "4" * 64,
        "test_cases": [{"x_hex": x, "y_hex": y} for x, y in cases],
    }
    path.write_text(json.dumps(fixture), encoding="utf-8")


def test_main_exits_zero_on_valid_fixture(tmp_path: Path) -> None:
    # Identity circuit: empty gate list. x_hex == y_hex (bit-identical).
    x = "00" * 4
    p = tmp_path / "fix.json"
    _write_fake_fixture(p, gates=[], cases=[(x, x)])
    assert main(["--fixture", str(p)]) == 0


def test_main_exits_non_zero_on_tampered_fixture(tmp_path: Path) -> None:
    """Acceptance bullet: tampered fixture should exit non-zero."""
    x = "00" * 4
    p = tmp_path / "fix.json"
    # Identity circuit but y_hex flipped: should not match run(C, x).
    _write_fake_fixture(p, gates=[], cases=[(x, "ff" * 4)])
    assert main(["--fixture", str(p)]) == FIXTURE_EXIT_CODE


def test_main_exits_non_zero_on_missing_fixture(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    assert main(["--fixture", str(missing)]) == FIXTURE_EXIT_CODE


def test_main_with_not_gate_circuit(tmp_path: Path) -> None:
    """End-to-end with a non-trivial circuit: NOT-on-bit-0 flips the LSB."""
    not_bit0 = Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL)
    p = tmp_path / "fix.json"
    _write_fake_fixture(p, gates=[not_bit0], cases=[("00" * 4, "01" + "00" * 3)])
    assert main(["--fixture", str(p)]) == 0
