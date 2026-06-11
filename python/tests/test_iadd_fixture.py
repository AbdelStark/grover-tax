"""Tests for `grover_tax.iadd_fixture` (KB-4 #116, KB-15 #127).

Covers the v0.3-iadd fixture builder: single-copy circuit storage with K-loop
`repetitions` semantics, register-aware test-case I/O, integer-math vs
reference-simulator agreement, the forward-looking resource bounds, schema
validity, determinism, reproducibility of the committed canonical fixtures,
and the `gen-iadd-fixtures` CLI round trip (write then `--check`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from grover_tax.errors import FIXTURE_EXIT_CODE, FixtureError
from grover_tax.iadd_fixture import (
    FIXTURE_VERSION,
    SCHEMA_FILENAME,
    UPSTREAM_PIN_COMMIT,
    build_iadd_fixture,
    main,
)
from grover_tax.registers import decode_registers
from grover_tax.serialise import deserialise
from grover_tax.sim_reference import run
from grover_tax.validate_schemas import validate_artifact

_MOD64 = 1 << 64

# iadd8 keeps simulator replay cheap (67 gates/repetition).
_SMALL = {"repetitions": 3, "n_samples": 4, "tier": "T0", "circuit_source": "iadd8.kmx"}


# -- shape & schema ----------------------------------------------------------


def test_fixture_validates_against_schema() -> None:
    fixture = build_iadd_fixture(repetitions=1, n_samples=8, tier="T0")
    assert validate_artifact(document=fixture, schema_filename=SCHEMA_FILENAME) == []
    assert fixture["version"] == FIXTURE_VERSION
    assert fixture["circuit_source"] == "iadd64.kmx"
    assert fixture["num_qubits"] == 128
    assert fixture["register_width"] == 64
    assert fixture["n_samples"] == 8
    assert len(fixture["test_cases"]) == 8
    assert fixture["workload_pin_commit"] == UPSTREAM_PIN_COMMIT


def test_small_fixture_shape_and_schema() -> None:
    fixture = build_iadd_fixture(**_SMALL)
    assert fixture["repetitions"] == 3
    assert len(fixture["test_cases"]) == 4
    assert validate_artifact(document=fixture, schema_filename=SCHEMA_FILENAME) == []


# -- single-copy storage (the KB-15 design point) -----------------------------


def test_stored_circuit_is_single_repetition() -> None:
    """The GTV1 bytes hold ONE adder copy regardless of K; K lives in
    `repetitions`. Embedded concatenation would be ~163 MB at the reference
    scale (iadd256, K~8000)."""
    k1 = build_iadd_fixture(**{**_SMALL, "repetitions": 1})
    k3 = build_iadd_fixture(**_SMALL)
    assert k1["circuit_byte_serialisation_hex"] == k3["circuit_byte_serialisation_hex"]
    assert k1["circuit_commitment_sha256_hex"] == k3["circuit_commitment_sha256_hex"]
    assert k1["kmx_source_sha256"] == k3["kmx_source_sha256"]


def test_forward_looking_resource_fields_scale_with_k() -> None:
    """demanded_* bounds cover all K repetitions, as upstream scales them
    (run_proofs.sh: SCALED_TOFFOLI = TOFFOLI * nrep)."""
    f1 = build_iadd_fixture(repetitions=1, n_samples=4, tier="T0")
    assert f1["demanded_max_qubit_count"] == 128
    assert f1["demanded_max_non_clifford_count"] == 125  # 125 TOFFOLI
    assert f1["demanded_max_circuit_instructions"] == 627  # 502 CNOT + 125 TOFFOLI
    f3 = build_iadd_fixture(repetitions=3, n_samples=4, tier="T2")
    assert f3["demanded_max_qubit_count"] == 128  # qubits don't grow with K
    assert f3["demanded_max_non_clifford_count"] == 375
    assert f3["demanded_max_circuit_instructions"] == 1881


def test_commitment_policy_carries_both_hashes() -> None:
    fixture = build_iadd_fixture(repetitions=1, n_samples=4, tier="T0")
    # Raw .kmx hash is cross-comparable with upstream sha256(iadd64.kmx).
    assert fixture["kmx_source_sha256"] != fixture["circuit_commitment_sha256_hex"]
    assert len(fixture["kmx_source_sha256"]) == 64
    assert fixture["circuit_commitment_sha256_hex"] != fixture["circuit_commitment_blake2s_hex"]


def test_commitments_match_stored_bytes() -> None:
    fixture = build_iadd_fixture(**_SMALL)
    circuit_bytes = bytes.fromhex(fixture["circuit_byte_serialisation_hex"])
    assert fixture["circuit_commitment_sha256_hex"] == hashlib.sha256(circuit_bytes).hexdigest()
    assert fixture["circuit_commitment_blake2s_hex"] == hashlib.blake2s(circuit_bytes).hexdigest()


# -- repeated-addition semantics ---------------------------------------------


@pytest.mark.parametrize("k", [1, 2, 3])
def test_repeated_addition_law(k: int) -> None:
    """K-fold iadd applied to (x, y) computes (x + K*y mod 2^64, y)."""
    fixture = build_iadd_fixture(repetitions=k, n_samples=12, tier=f"T{k}")
    assert fixture["repetitions"] == k
    for case in fixture["test_cases"]:
        x, y = case["r0_in"], case["r1_in"]
        yb = bytes.fromhex(case["y_hex"])
        out_r0 = int.from_bytes(yb[0:8], "little")
        out_r1 = int.from_bytes(yb[8:16], "little")
        assert out_r0 == (x + k * y) % _MOD64
        assert out_r1 == y


def test_repeated_addition_semantics_via_simulator() -> None:
    """Looping the stored gate list K times realises (x + K*y, y) on every case."""
    fixture = build_iadd_fixture(**_SMALL)
    gates = deserialise(bytes.fromhex(fixture["circuit_byte_serialisation_hex"]))
    width = fixture["register_width"]
    layout = fixture["register_layout"]
    for case in fixture["test_cases"]:
        state = bytes.fromhex(case["x_hex"])
        for _ in range(fixture["repetitions"]):
            state = run(gates, state)
        assert state == bytes.fromhex(case["y_hex"])
        decoded = decode_registers(state, layout)
        assert decoded["r0"] == (case["r0_in"] + fixture["repetitions"] * case["r1_in"]) % (
            1 << width
        )
        assert decoded["r1"] == case["r1_in"]


def test_iadd256_fixture_smoke() -> None:
    """iadd256 (512 qubits, 2547 gates) builds, validates, and simulates."""
    fixture = build_iadd_fixture(
        repetitions=2, n_samples=2, tier="T0", circuit_source="iadd256.kmx"
    )
    assert fixture["num_qubits"] == 512
    assert fixture["register_width"] == 256
    assert fixture["demanded_max_circuit_instructions"] == 2 * 2547
    assert validate_artifact(document=fixture, schema_filename=SCHEMA_FILENAME) == []
    case = fixture["test_cases"][0]
    assert len(case["x_hex"]) == 2 * 64  # 64-byte full state
    gates = deserialise(bytes.fromhex(fixture["circuit_byte_serialisation_hex"]))
    state = bytes.fromhex(case["x_hex"])
    for _ in range(2):
        state = run(gates, state)
    assert state == bytes.fromhex(case["y_hex"])


# -- seed binding & determinism ------------------------------------------------


def test_seed_binds_circuit_and_benchmark_point() -> None:
    """Different (circuit, K, N) points draw different test-case streams."""
    a = build_iadd_fixture(**_SMALL)
    b = build_iadd_fixture(**{**_SMALL, "repetitions": 4})
    c = build_iadd_fixture(**{**_SMALL, "circuit_source": "iadd64.kmx"})
    assert a["seed_hex"] != b["seed_hex"]
    assert a["seed_hex"] != c["seed_hex"]
    assert a["test_cases"][0]["r0_in"] != b["test_cases"][0]["r0_in"]


@pytest.mark.parametrize("k", [1, 3])
def test_build_is_deterministic(k: int) -> None:
    a = build_iadd_fixture(repetitions=k, n_samples=8, tier="T0")
    b = build_iadd_fixture(repetitions=k, n_samples=8, tier="T0")
    assert a == b


# -- the committed canonical fixtures -----------------------------------------


def test_committed_canonical_fixtures_match_generator() -> None:
    """Every fixtures/v0.3-*.json on disk is reproducible from the generator."""
    repo_root = Path(__file__).resolve().parents[2]
    committed = sorted((repo_root / "fixtures").glob("v0.3-*.json"))
    assert committed, "no committed v0.3 fixtures found"
    for path in committed:
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        regenerated = build_iadd_fixture(
            repetitions=on_disk["repetitions"],
            n_samples=on_disk["n_samples"],
            tier=on_disk["tier"],
            circuit_source=on_disk["circuit_source"],
            pin_commit=on_disk["workload_pin_commit"],
        )
        on_disk.pop("generator_commit")
        regenerated.pop("generator_commit")
        assert regenerated == on_disk, f"{path.name} drifted from the generator"


# -- input validation ----------------------------------------------------------


def test_rejects_non_adder_circuit() -> None:
    with pytest.raises(FixtureError):
        build_iadd_fixture(repetitions=1, n_samples=1, tier="T0", circuit_source="inc3.kmx")


def test_rejects_non_classical_circuit() -> None:
    """A circuit outside the classical subset is rejected by the transpiler."""
    with pytest.raises(FixtureError):
        build_iadd_fixture(
            repetitions=1, n_samples=4, tier="T0", circuit_source="iadd8_with_ancillae.kmx"
        )


def test_rejects_bad_arguments() -> None:
    with pytest.raises(ValueError):
        build_iadd_fixture(**{**_SMALL, "repetitions": 0})
    with pytest.raises(ValueError):
        build_iadd_fixture(**{**_SMALL, "n_samples": 0})


# -- CLI round trip --------------------------------------------------------------


def test_cli_write_then_check_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "v0.3-iadd8-k3-n4.json"
    args = [
        "--repetitions", "3",
        "--samples", "4",
        "--circuit", "iadd8.kmx",
        "--out", str(out),
    ]
    assert main(args) == 0
    assert out.is_file()
    assert main([*args, "--check"]) == 0

    # Tampering with a case must be caught as drift.
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["test_cases"][0]["r0_in"] = (doc["test_cases"][0]["r0_in"] + 1) % 256
    out.write_text(json.dumps(doc), encoding="utf-8")
    assert main([*args, "--check"]) == FIXTURE_EXIT_CODE
