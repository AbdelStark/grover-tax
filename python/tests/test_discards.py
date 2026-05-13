"""Tests for `grover_tax.discards`."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from grover_tax.discards import DiscardReason, append_discard
from grover_tax.paths import repo_root

SCHEMA_PATH = repo_root() / "docs" / "spec" / "schemas" / "discards-v1.schema.json"
DISCARD_SH = repo_root() / "scripts" / "discard.sh"


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def test_enum_values_match_spec() -> None:
    assert {r.value for r in DiscardReason} == {
        "thermal",
        "gpu_residency",
        "swap_active",
        "cold_cache",
        "env_var_miss",
        "other",
    }


def test_append_single_record(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    append_discard(
        run_id="1715610912-abcd123",
        prover="sp1",
        reason=DiscardReason.THERMAL,
        detail="P-core T 97C above 95C threshold",
        measurement_artifact="results/sp1_v0.1_1715610912-abcd123.timing.json",
        log_path=log,
    )
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["prover"] == "sp1"
    assert record["reason"] == "thermal"
    assert record["run_id"] == "1715610912-abcd123"
    # Trailing newline mandatory per the spec.
    raw = log.read_bytes()
    assert raw.endswith(b"\n")


def test_record_validates_against_schema(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    append_discard(
        run_id="r",
        prover="stwo",
        reason="cold_cache",
        detail="first run discarded per D-INV-3",
        measurement_artifact="results/stwo_v0.1_r.timing.json",
        log_path=log,
    )
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    _schema_validator().validate(record)


def test_string_reason_accepted(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    append_discard(
        run_id="r",
        prover="sp1",
        reason="other",
        detail="d",
        measurement_artifact="r.json",
        log_path=log,
    )
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert record["reason"] == "other"


def test_invalid_reason_raises(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    with pytest.raises(ValueError, match="reason 'tired' not in"):
        append_discard(
            run_id="r",
            prover="sp1",
            reason="tired",
            detail="d",
            measurement_artifact="r.json",
            log_path=log,
        )
    # Hard guarantee: the file was not created.
    assert not log.exists()


def test_invalid_prover_raises(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    with pytest.raises(ValueError, match="prover must be"):
        append_discard(
            run_id="r",
            prover="groth16",
            reason="other",
            detail="d",
            measurement_artifact="r.json",
            log_path=log,
        )


def test_concurrent_thread_writes(tmp_path: Path) -> None:
    """Acceptance bullet: 100 records from 10 threads, all valid, no corruption."""
    log = tmp_path / "discards.log"

    def worker(start: int) -> None:
        for i in range(10):
            append_discard(
                run_id=f"r-{start * 10 + i}",
                prover="sp1",
                reason="thermal",
                detail=f"concurrent write {start * 10 + i}",
                measurement_artifact=f"r-{start * 10 + i}.json",
                log_path=log,
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 100
    validator = _schema_validator()
    ids = []
    for line in lines:
        record = json.loads(line)  # raises if any line is corrupted JSON
        validator.validate(record)
        ids.append(record["run_id"])
    assert len(set(ids)) == 100


def test_creates_parent_directory_when_missing(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "deeper" / "discards.log"
    append_discard(
        run_id="r",
        prover="sp1",
        reason="other",
        detail="d",
        measurement_artifact="r.json",
        log_path=log,
    )
    assert log.is_file()


def test_default_log_path_used_when_none_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover the `log_path is None` branch by redirecting both helpers."""
    fake_log = tmp_path / "results" / "discards.log"
    fake_results = tmp_path / "results"
    monkeypatch.setattr("grover_tax.discards.discards_log_path", lambda: fake_log)
    monkeypatch.setattr("grover_tax.discards.results_dir", lambda: fake_results)
    append_discard(
        run_id="r",
        prover="sp1",
        reason="other",
        detail="d",
        measurement_artifact="r.json",
    )
    assert fake_log.is_file()
    record = json.loads(fake_log.read_text(encoding="utf-8").splitlines()[0])
    assert record["run_id"] == "r"


# -- shell helper --------------------------------------------------------------


def _run_discard_sh(*args: str, log_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            str(DISCARD_SH),
            "--run-id", "r-1",
            "--prover", "sp1",
            "--detail", "shell-emitted record",
            "--measurement-artifact", "results/foo.timing.json",
            "--log-path", str(log_path),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_shell_helper_appends_valid_record(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    result = _run_discard_sh("--reason", "thermal", log_path=log)
    assert result.returncode == 0, result.stderr
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    _schema_validator().validate(record)
    assert record["reason"] == "thermal"
    assert record["run_id"] == "r-1"


def test_shell_helper_rejects_invalid_reason(tmp_path: Path) -> None:
    log = tmp_path / "discards.log"
    result = _run_discard_sh("--reason", "tired", log_path=log)
    assert result.returncode == 2
    assert "not in enum" in result.stderr
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


def test_shell_and_python_interleave_safely(tmp_path: Path) -> None:
    """Both writers under the same lock — cross-tool exclusion holds."""
    log = tmp_path / "discards.log"

    # Python burst from one thread.
    def py_worker() -> None:
        for i in range(20):
            append_discard(
                run_id=f"py-{i}",
                prover="sp1",
                reason="thermal",
                detail=f"py {i}",
                measurement_artifact=f"py-{i}.json",
                log_path=log,
            )

    # Shell burst from another thread.
    def sh_worker() -> None:
        for i in range(20):
            _run_discard_sh(
                "--reason", "thermal",
                "--run-id", f"sh-{i}",
                "--detail", f"sh {i}",
                log_path=log,
            )

    t1 = threading.Thread(target=py_worker)
    t2 = threading.Thread(target=sh_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 40
    validator = _schema_validator()
    for line in lines:
        validator.validate(json.loads(line))


def test_jsonschema_dependency_is_importable() -> None:
    """Smoke check — without jsonschema the validation tests above would
    silently no-op; assert the import succeeded."""
    assert hasattr(jsonschema, "Draft202012Validator")
