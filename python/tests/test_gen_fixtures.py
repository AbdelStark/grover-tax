"""Tests for `grover_tax.gen_fixtures` (#16)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from grover_tax.errors import FIXTURE_EXIT_CODE
from grover_tax.gen_fixtures import (
    CIRCUIT_SERIALISATION_FORMAT_VERSION,
    FIXTURE_VERSION,
    SEED,
    _build_fixture,
    _normalise,
    main,
)
from grover_tax.paths import repo_root, workload_md_path
from grover_tax.workload import load_workload_md

# -- _build_fixture -----------------------------------------------------------


def test_build_fixture_against_real_workload() -> None:
    """The on-disk WORKLOAD.md (filled by #4) drives a schema-valid fixture."""
    workload = load_workload_md(workload_md_path())
    fixture = _build_fixture(workload)

    assert fixture["version"] == FIXTURE_VERSION
    assert fixture["workload_pin_commit"] == workload.upstream_commit
    assert (
        fixture["circuit_serialisation_format_version"]
        == CIRCUIT_SERIALISATION_FORMAT_VERSION
    )
    assert isinstance(fixture["n_samples"], int)
    assert fixture["n_samples"] >= 1
    assert len(fixture["test_cases"]) == fixture["n_samples"]
    # Hash-shape: 64 lowercase hex chars.
    assert len(fixture["seed_hex"]) == 64
    assert len(fixture["circuit_commitment_sha256_hex"]) == 64
    assert len(fixture["circuit_commitment_blake2s_hex"]) == 64


def test_build_fixture_is_deterministic_modulo_generator_commit() -> None:
    """Two builds on the same workload + SEED produce equal dicts (excl.
    `generator_commit`)."""
    workload = load_workload_md(workload_md_path())
    a = _build_fixture(workload)
    b = _build_fixture(workload)
    assert _normalise(a) == _normalise(b)


def test_build_fixture_satisfies_invariant_2() -> None:
    """F-INV-2: `sha256(circuit_bytes) == circuit_commitment_sha256_hex`."""
    workload = load_workload_md(workload_md_path())
    fixture = _build_fixture(workload)
    circuit_bytes = bytes.fromhex(fixture["circuit_byte_serialisation_hex"])
    assert hashlib.sha256(circuit_bytes).hexdigest() == fixture["circuit_commitment_sha256_hex"]


def test_build_fixture_satisfies_invariant_3() -> None:
    """F-INV-3: `blake2s(circuit_bytes) == circuit_commitment_blake2s_hex`."""
    workload = load_workload_md(workload_md_path())
    fixture = _build_fixture(workload)
    circuit_bytes = bytes.fromhex(fixture["circuit_byte_serialisation_hex"])
    assert (
        hashlib.blake2s(circuit_bytes).hexdigest()
        == fixture["circuit_commitment_blake2s_hex"]
    )


def test_build_fixture_satisfies_invariant_1() -> None:
    """F-INV-1: `len(test_cases) == n_samples`."""
    workload = load_workload_md(workload_md_path())
    fixture = _build_fixture(workload)
    assert len(fixture["test_cases"]) == fixture["n_samples"]


def test_build_fixture_test_case_shapes_match_schema() -> None:
    """`x_hex` is 128 chars, `y_hex` is 66 chars per the fixture schema."""
    workload = load_workload_md(workload_md_path())
    fixture = _build_fixture(workload)
    for case in fixture["test_cases"]:
        assert len(case["x_hex"]) == 128
        assert len(case["y_hex"]) == 66


def test_seed_hex_matches_sha256_of_constant_seed() -> None:
    workload = load_workload_md(workload_md_path())
    fixture = _build_fixture(workload)
    assert fixture["seed_hex"] == hashlib.sha256(SEED).hexdigest()


# -- main() CLI ---------------------------------------------------------------


def test_main_writes_a_schema_valid_fixture(tmp_path: Path) -> None:
    out = tmp_path / "v0.1.json"
    rc = main(["--out", str(out)])
    assert rc == 0
    assert out.is_file()
    # Re-validate via the schema CLI.
    result = subprocess.run(
        ["uv", "run", "python", "-m", "grover_tax.validate_schemas", str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root()),
    )
    assert result.returncode == 0, result.stderr


def test_main_check_passes_after_fresh_generation(tmp_path: Path) -> None:
    out = tmp_path / "v0.1.json"
    main(["--out", str(out)])
    assert main(["--check", "--out", str(out)]) == 0


def test_main_check_fails_on_tampered_fixture(tmp_path: Path) -> None:
    out = tmp_path / "v0.1.json"
    main(["--out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    data["test_cases"][0]["y_hex"] = "02" + "aa" * 32
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert main(["--check", "--out", str(out)]) == FIXTURE_EXIT_CODE


def test_main_check_fails_when_fixture_missing(tmp_path: Path) -> None:
    assert main(["--check", "--out", str(tmp_path / "missing.json")]) == FIXTURE_EXIT_CODE


def test_main_two_runs_produce_byte_identical_output_modulo_commit(
    tmp_path: Path,
) -> None:
    """Acceptance: deterministic generator (RFC-0002 §"Determinism guarantees")."""
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    main(["--out", str(out_a)])
    main(["--out", str(out_b)])
    a = json.loads(out_a.read_text(encoding="utf-8"))
    b = json.loads(out_b.read_text(encoding="utf-8"))
    a.pop("generator_commit", None)
    b.pop("generator_commit", None)
    assert a == b


def test_main_writes_via_temp_then_replace(tmp_path: Path) -> None:
    """No `.partial` artifact left behind on success."""
    out = tmp_path / "v0.1.json"
    main(["--out", str(out)])
    leftovers = [p.name for p in tmp_path.iterdir() if ".partial." in p.name]
    assert leftovers == []


def test_main_fails_with_fixture_subcode_on_bad_workload(tmp_path: Path) -> None:
    """Pointing at an unfilled workload file surfaces FIXTURE.WORKLOAD_NOT_PINNED."""
    bad = tmp_path / "WORKLOAD.md"
    bad.write_text(
        "---\nupstream_repo: x\nupstream_commit: TBD\npinned_at: TBD\n"
        "pinned_by: TBD\nfixture_target_version: TBD\n---\n# tbd\n",
        encoding="utf-8",
    )
    rc = main(["--out", str(tmp_path / "x.json"), "--workload", str(bad)])
    assert rc == FIXTURE_EXIT_CODE
