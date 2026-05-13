"""Tests for `grover_tax.validate_schemas`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grover_tax.errors import FIXTURE_EXIT_CODE, REPORT_EXIT_CODE
from grover_tax.paths import repo_root
from grover_tax.validate_schemas import (
    AUTO_DETECT_NAMES,
    SCHEMA_NAMES,
    main,
    validate_artifact,
    validate_file,
)

GOOD_FIXTURE = repo_root() / "python" / "tests" / "fixtures" / "good" / "fixture_canonical.json"
BAD_FIXTURE_DIR = repo_root() / "python" / "tests" / "fixtures" / "bad"


def test_schema_names_cover_three_artifacts() -> None:
    """All three persisted-artifact schemas have at least one short label."""
    schemas = set(SCHEMA_NAMES.values())
    assert "fixture-v0.1.schema.json" in schemas
    assert "setup-v1.schema.json" in schemas
    assert "discards-v1.schema.json" in schemas


def test_auto_detect_table_has_discards_setup_fixture() -> None:
    schemas = {schema for _, schema in AUTO_DETECT_NAMES}
    assert "discards-v1.schema.json" in schemas
    assert "setup-v1.schema.json" in schemas
    assert "fixture-v0.1.schema.json" in schemas


def test_validate_canonical_fixture_returns_no_errors() -> None:
    errors = validate_file(GOOD_FIXTURE, schema_filename="fixture-v0.1.schema.json")
    assert errors == []


def test_validate_artifact_in_memory() -> None:
    record = {
        "schema_version": 1,
        "run_id": "r",
        "wall_clock_s": 1.0,
        "user_cpu_s": 1.0,
        "sys_cpu_s": 0.5,
        "peak_rss_mib": 256.0,
        "proving_key_bytes": 1,
        "verifying_key_bytes": 1,
        "groth16_ceremony_origin": "ok",
    }
    assert validate_artifact(document=record, schema_filename="setup-v1.schema.json") == []


def test_validate_discards_log_per_line(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    record1 = {
        "ts": "2026-05-13T14:35:12Z",
        "run_id": "r-1",
        "prover": "sp1",
        "reason": "thermal",
        "detail": "d",
        "measurement_artifact": "results/r-1.json",
    }
    record2 = {
        "ts": "2026-05-13T14:35:13Z",
        "run_id": "r-2",
        "prover": "stwo",
        "reason": "swap_active",
        "detail": "d",
        "measurement_artifact": "results/r-2.json",
    }
    log.write_text(json.dumps(record1) + "\n\n" + json.dumps(record2) + "\n", encoding="utf-8")
    assert validate_file(log, schema_filename="discards-v1.schema.json") == []


def test_validate_discards_log_reports_line_number(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    bad = {
        "ts": "2026-05-13T14:35:12Z",
        "run_id": "r-1",
        "prover": "groth16",  # invalid enum
        "reason": "thermal",
        "detail": "d",
        "measurement_artifact": "r.json",
    }
    log.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    errors = validate_file(log, schema_filename="discards-v1.schema.json")
    assert len(errors) == 1
    assert "line 1" in errors[0].message


# -- main() ---------------------------------------------------------------------


def test_main_good_fixture_exits_zero() -> None:
    assert main([str(GOOD_FIXTURE)]) == 0


def test_main_bad_fixture_exits_4(capsys: pytest.CaptureFixture[str]) -> None:
    """Acceptance bullet: tampered fixture exits non-zero with field-level reason."""
    bad = BAD_FIXTURE_DIR / "12_wrong_format_version.json"
    rc = main([str(bad)])
    captured = capsys.readouterr()
    assert rc == FIXTURE_EXIT_CODE
    assert "FIXTURE.SCHEMA_INVALID" in captured.err
    assert "circuit_serialisation_format_version" in captured.err


def test_main_explicit_schema_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Force a fixture file to be validated against the setup schema → fails."""
    rc = main([str(GOOD_FIXTURE), "--schema", "setup"])
    captured = capsys.readouterr()
    assert rc == REPORT_EXIT_CODE
    assert "REPORT.SCHEMA_INVALID" in captured.err


def test_main_unknown_schema_label_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse rejects unknown choices before our code sees them — exit 2."""
    with pytest.raises(SystemExit) as excinfo:
        main([str(GOOD_FIXTURE), "--schema", "nonsense"])
    assert excinfo.value.code == 2


def test_main_unknown_filename_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cannot infer schema from an unrecognised filename → exit 2."""
    p = tmp_path / "mystery.json"
    p.write_text("{}", encoding="utf-8")
    rc = main([str(p)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "cannot auto-detect" in captured.err


def test_main_missing_file_exits_with_schema_code(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([str(GOOD_FIXTURE.parent / "does_not_exist_v0.1.json")])
    captured = capsys.readouterr()
    assert rc == FIXTURE_EXIT_CODE
    assert "FIXTURE.SCHEMA_INVALID" in captured.err
    assert "file not found" in captured.err


def test_main_non_json_file_exits_with_schema_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / "v0.1.json"
    p.write_text("not json at all", encoding="utf-8")
    rc = main([str(p)])
    captured = capsys.readouterr()
    assert rc == FIXTURE_EXIT_CODE
    assert "FIXTURE.SCHEMA_INVALID" in captured.err
    assert "not valid JSON" in captured.err


def test_main_setup_file_routes_to_report_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Filename `*setup*.json` auto-detects the setup schema; failure is exit 6."""
    p = tmp_path / "sp1_setup.json"
    p.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    rc = main([str(p)])
    captured = capsys.readouterr()
    assert rc == REPORT_EXIT_CODE
    assert "REPORT.SCHEMA_INVALID" in captured.err


def test_main_all_twenty_bad_fixtures_fail() -> None:
    """Regression guard: every checked-in bad fixture is rejected by the CLI."""
    for path in sorted(BAD_FIXTURE_DIR.glob("*.json")):
        assert main([str(path)]) == FIXTURE_EXIT_CODE, f"{path.name} unexpectedly validated"


def test_resolve_schema_rejects_bogus_explicit_label(tmp_path: Path) -> None:
    """Defensive guard inside `_resolve_schema` against library callers
    that bypass argparse and pass an unknown label."""
    from grover_tax.validate_schemas import _resolve_schema
    with pytest.raises(SystemExit, match="unknown --schema"):
        _resolve_schema(explicit="bogus", path=tmp_path / "x")
