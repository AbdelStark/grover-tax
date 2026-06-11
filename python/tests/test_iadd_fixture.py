"""Tests for `grover_tax.iadd_fixture` — repeated-addition fixtures (KB-4, #116)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grover_tax.errors import FixtureError
from grover_tax.iadd_fixture import (
    FIXTURE_VERSION,
    SCHEMA_FILENAME,
    build_iadd_fixture,
    main,
)
from grover_tax.validate_schemas import validate_artifact

_MOD64 = 1 << 64


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


def test_forward_looking_resource_fields() -> None:
    """demanded_* bounds reflect the K-repeated circuit (forward-looking, KB-10)."""
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
    # GTV1 hashes are over the actual executed bytes.
    assert fixture["circuit_commitment_sha256_hex"] != fixture["circuit_commitment_blake2s_hex"]


def test_kmx_source_hash_is_over_single_repetition() -> None:
    """The raw-kmx hash is K-invariant (always the single source circuit)."""
    f1 = build_iadd_fixture(repetitions=1, n_samples=2, tier="T0")
    f5 = build_iadd_fixture(repetitions=5, n_samples=2, tier="T3")
    assert f1["kmx_source_sha256"] == f5["kmx_source_sha256"]
    # But the GTV1 commitment differs (5x the gates).
    assert f1["circuit_commitment_sha256_hex"] != f5["circuit_commitment_sha256_hex"]


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


# -- determinism -------------------------------------------------------------


@pytest.mark.parametrize("k", [1, 2, 3])
def test_build_is_deterministic(k: int) -> None:
    a = build_iadd_fixture(repetitions=k, n_samples=8, tier="T0")
    b = build_iadd_fixture(repetitions=k, n_samples=8, tier="T0")
    # generator_commit is the only non-deterministic field (git HEAD).
    a.pop("generator_commit")
    b.pop("generator_commit")
    assert a == b


def test_committed_fixture_round_trips_via_check(tmp_path: Path) -> None:
    out = tmp_path / "v0.3-iadd-T0.json"
    assert main(["--tier", "T0", "--repetitions", "1", "--samples", "8", "--out", str(out)]) == 0
    # A second --check against the just-written file passes.
    assert (
        main(["--tier", "T0", "--repetitions", "1", "--samples", "8", "--out", str(out), "--check"])
        == 0
    )


def test_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "v0.3-iadd-T0.json"
    assert main(["--tier", "T0", "--repetitions", "1", "--samples", "8", "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    doc["test_cases"][0]["r0_in"] += 1  # tamper
    out.write_text(json.dumps(doc, indent=2) + "\n")
    rc = main(
        ["--tier", "T0", "--repetitions", "1", "--samples", "8", "--out", str(out), "--check"]
    )
    assert rc != 0


# -- the committed canonical fixture -----------------------------------------


def test_committed_canonical_fixture_matches_generator() -> None:
    """fixtures/v0.3-iadd-T0.json on disk is reproducible from the generator."""
    repo_root = Path(__file__).resolve().parents[2]
    committed = repo_root / "fixtures" / "v0.3-iadd-T0.json"
    on_disk = json.loads(committed.read_text())
    regenerated = build_iadd_fixture(
        repetitions=on_disk["repetitions"],
        n_samples=on_disk["n_samples"],
        tier=on_disk["tier"],
    )
    on_disk.pop("generator_commit")
    regenerated.pop("generator_commit")
    assert regenerated == on_disk


# -- input validation --------------------------------------------------------


def test_rejects_bad_repetitions() -> None:
    with pytest.raises(ValueError):
        build_iadd_fixture(repetitions=0, n_samples=4, tier="T0")


def test_rejects_non_classical_circuit() -> None:
    """A circuit outside the classical subset is rejected by the transpiler."""
    with pytest.raises(FixtureError):
        build_iadd_fixture(
            repetitions=1, n_samples=4, tier="T0", circuit_source="iadd8_with_ancillae.kmx"
        )
