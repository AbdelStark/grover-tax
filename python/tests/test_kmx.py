"""Unit tests for `grover_tax.kmx` — the `.kmx → GTV1` transpiler (KB-1, #113)."""

from __future__ import annotations

from pathlib import Path

import pytest

from grover_tax.errors import FIXTURE_EXIT_CODE, FixtureError, FixtureSubcode
from grover_tax.kmx import (
    KmxCircuit,
    kmx_source_sha256,
    opcode_histogram,
    parse_kmx,
    transpile_file,
)
from grover_tax.serialise import Opcode, deserialise, serialise
from grover_tax.sim_reference import BitVector, run

# The vendored upstream example circuits live under the SP1 reference copy.
_EXAMPLE_DATA = (
    Path(__file__).resolve().parents[2] / "third_party" / "sp1" / "docs" / "example_data"
)


def _example(name: str) -> Path:
    return _EXAMPLE_DATA / name


# -- happy path: the requested adders transpile ------------------------------


def test_inc3_transpiles_to_expected_gates() -> None:
    """The doc's 3-qubit incrementer: CCX q0 q1 q2 / CX q0 q1 / X q0."""
    circuit = transpile_file(_example("inc3.kmx"))
    assert opcode_histogram(circuit.gates) == {
        "NOP": 0,
        "NOT": 1,
        "CNOT": 1,
        "TOFFOLI": 1,
    }
    # Order is preserved and operand mapping is control(s)-then-target.
    toffoli, cnot, not_gate = circuit.gates
    assert (toffoli.opcode, toffoli.ctrl_a, toffoli.ctrl_b, toffoli.target) == (
        Opcode.TOFFOLI,
        0,
        1,
        2,
    )
    assert (cnot.opcode, cnot.ctrl_a, cnot.target) == (Opcode.CNOT, 0, 1)
    assert (not_gate.opcode, not_gate.target) == (Opcode.NOT, 0)
    assert circuit.registers == {0: (0, 1, 2)}
    assert circuit.num_qubits == 3


def test_iadd64_golden_histogram() -> None:
    """KB-1 acceptance: iadd64 transpiles to 502 CNOT + 125 TOFFOLI (upstream)."""
    circuit = transpile_file(_example("iadd64.kmx"))
    hist = opcode_histogram(circuit.gates)
    assert hist["CNOT"] == 502
    assert hist["TOFFOLI"] == 125
    assert hist["NOT"] == 0
    assert hist["NOP"] == 0
    assert len(circuit.gates) == 627


def test_iadd64_register_layout() -> None:
    """iadd64 declares r0 = q0..q63 and r1 = q64..q127, LSB-first."""
    circuit = transpile_file(_example("iadd64.kmx"))
    assert circuit.registers[0] == tuple(range(0, 64))
    assert circuit.registers[1] == tuple(range(64, 128))
    assert circuit.num_qubits == 128
    assert circuit.register_layout["r0"][0] == 0  # least-significant first
    assert circuit.register_layout["r1"][-1] == 127


def test_iadd8_golden_histogram() -> None:
    circuit = transpile_file(_example("iadd8.kmx"))
    hist = opcode_histogram(circuit.gates)
    assert hist["CNOT"] == 54
    assert hist["TOFFOLI"] == 13
    assert circuit.registers[0] == tuple(range(0, 8))
    assert circuit.registers[1] == tuple(range(8, 16))
    assert circuit.num_qubits == 16


# -- round-trip --------------------------------------------------------------


@pytest.mark.parametrize("name", ["iadd64.kmx", "iadd8.kmx", "inc3.kmx"])
def test_serialise_round_trip(name: str) -> None:
    """Transpiled gates survive GTV1 serialise → deserialise unchanged."""
    circuit = transpile_file(_example(name))
    assert deserialise(serialise(circuit.gates)) == list(circuit.gates)


def test_parse_is_pure_function_of_text() -> None:
    text = _example("iadd64.kmx").read_text(encoding="utf-8")
    a = parse_kmx(text)
    b = parse_kmx(text)
    assert a.gates == b.gates
    assert a.registers == b.registers


def test_transpiled_inc3_increments_under_reference_sim() -> None:
    """Sanity: the transpiled inc3 actually increments r0 mod 8 (LSB q0)."""
    circuit = transpile_file(_example("inc3.kmx"))
    for value in range(8):
        state = BitVector(b"\x00")  # 8 bits, q0..q2 used
        for bit in range(3):
            state.set(bit, (value >> bit) & 1)
        out = run(list(circuit.gates), state.to_bytes())
        out_vec = BitVector(out)
        got = sum(out_vec.get(b) << b for b in range(3))
        assert got == (value + 1) % 8


# -- rejection: Tier-2 instructions ------------------------------------------


def test_iadd8_with_ancillae_is_rejected() -> None:
    """KB-1 acceptance: the HMR/phase variant is cleanly rejected."""
    with pytest.raises(FixtureError) as exc:
        transpile_file(_example("iadd8_with_ancillae.kmx"))
    assert exc.value.subcode == FixtureSubcode.UNSUPPORTED_INSTRUCTION.value
    assert exc.value.exit_code == FIXTURE_EXIT_CODE


@pytest.mark.parametrize(
    "src",
    [
        "Z q0",
        "CZ q0 q1",
        "CCZ q0 q1 q2",
        "NEG",
        "SWAP q0 q1",
        "R q0",
        "HMR q0 b0",
        "BIT_INVERT b0",
        "BIT_STORE0 b0",
        "BIT_STORE1 b0",
        "PUSH_CONDITION if b0",
        "POP_CONDITION",
        "DEBUG_PRINT q0",
    ],
)
def test_unsupported_instructions_rejected(src: str) -> None:
    with pytest.raises(FixtureError) as exc:
        parse_kmx(src + "\n")
    assert exc.value.subcode == FixtureSubcode.UNSUPPORTED_INSTRUCTION.value


def test_if_condition_on_classical_gate_rejected() -> None:
    with pytest.raises(FixtureError) as exc:
        parse_kmx("CX q0 q1 if b3\n")
    assert exc.value.subcode == FixtureSubcode.UNSUPPORTED_INSTRUCTION.value


def test_bit_register_member_rejected() -> None:
    with pytest.raises(FixtureError) as exc:
        parse_kmx("APPEND_TO_REGISTER b0 r0\n")
    assert exc.value.subcode == FixtureSubcode.UNSUPPORTED_INSTRUCTION.value


# -- rejection: parse errors -------------------------------------------------


@pytest.mark.parametrize(
    "src",
    [
        "X",  # wrong arity (0 qubits)
        "X q0 q1",  # wrong arity (2 qubits)
        "CX q0",  # wrong arity (1 qubit)
        "CCX q0 q1",  # wrong arity (2 qubits)
        "X b0",  # non-qubit operand
        "CX q0 r1",  # register operand
        "X qq",  # malformed target
        "X q0 if",  # malformed condition (no bit)
    ],
)
def test_parse_errors(src: str) -> None:
    with pytest.raises(FixtureError) as exc:
        parse_kmx(src + "\n")
    assert exc.value.subcode == FixtureSubcode.KMX_PARSE_ERROR.value


def test_lowercase_name_is_parse_error() -> None:
    with pytest.raises(FixtureError) as exc:
        parse_kmx("cx q0 q1\n")
    assert exc.value.subcode == FixtureSubcode.KMX_PARSE_ERROR.value


def test_qubit_id_over_u16_rejected() -> None:
    with pytest.raises(FixtureError) as exc:
        parse_kmx("X q70000\n")
    assert exc.value.subcode == FixtureSubcode.KMX_PARSE_ERROR.value


# -- comments, indentation, blanks are decorative ----------------------------


def test_comments_indentation_blanks_ignored() -> None:
    src = "# a comment\n\n   \t  CCX q0 q1 q2   # inline comment with ünïcödé\n  CX q0 q1\nX q0\n\n"
    circuit = parse_kmx(src)
    assert opcode_histogram(circuit.gates) == {"NOP": 0, "NOT": 1, "CNOT": 1, "TOFFOLI": 1}


def test_empty_register_declared_by_REGISTER() -> None:
    circuit = parse_kmx("REGISTER r2\n")
    assert circuit.registers == {2: ()}


# -- commitment & metadata ---------------------------------------------------


def test_source_bytes_and_sha_match_raw_file() -> None:
    path = _example("iadd64.kmx")
    circuit = transpile_file(path)
    raw = path.read_bytes()
    assert circuit.source_bytes == raw
    assert kmx_source_sha256(circuit.source_bytes) == kmx_source_sha256(raw)
    # Distinct from the GTV1 commitment — the bytes genuinely differ.
    import hashlib

    gtv1_sha = hashlib.sha256(serialise(circuit.gates)).hexdigest()
    assert kmx_source_sha256(raw) != gtv1_sha


def test_register_layout_is_json_friendly() -> None:
    circuit = transpile_file(_example("iadd8.kmx"))
    layout = circuit.register_layout
    assert set(layout) == {"r0", "r1"}
    assert all(isinstance(v, list) for v in layout.values())
    assert isinstance(circuit, KmxCircuit)
