"""Unit tests for `grover_tax.workload`."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from grover_tax.errors import FixtureError
from grover_tax.workload import Workload, WorkloadField, load_workload_md

VALID_SHA = "0123456789abcdef0123456789abcdef01234567"


def _valid_workload(*, commit: str = VALID_SHA) -> str:
    """Build a fully-populated, valid `WORKLOAD.md` body for testing."""
    return dedent(
        f"""\
        ---
        upstream_repo: https://github.com/tanujkhattar/zkp_ecc
        upstream_commit: {commit}
        pinned_at: 2026-05-13
        pinned_by: tester
        fixture_target_version: v0.1
        ---

        # Workload pin

        | Field | Source location (upstream) | Value | Notes |
        |---|---|---|---|
        | `N` (number of test cases) | `prover/prove.rs:67` | 9024 | upstream README example |
        | Gate count of `C` for one secp256k1 point-add | `program/src/main.rs` | 17000000 | total ops upper bound |
        | `W` (bit-stripe width) | `program/src/main.rs:121` | 64 | `const BATCH_SIZE` |
        | Modular-arithmetic gate count | derived | 2100000 | Toffoli upper bound |
        | Circuit-commitment scheme (SP1 side) | `program/src/main.rs:21-25` | SHA-256 over kmx bytes | verbatim |
        | Entropy source for test-case generation | `program/src/main.rs:83-85` | SHAKE-256 seeded with kmx bytes | Fiat-Shamir |
        """
    )


def test_valid_workload_parses(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload(), encoding="utf-8")
    wl = load_workload_md(p)
    assert isinstance(wl, Workload)
    assert wl.upstream_commit == VALID_SHA
    assert wl.upstream_repo == "https://github.com/tanujkhattar/zkp_ecc"
    assert wl.pinned_at == "2026-05-13"
    assert wl.pinned_by == "tester"
    assert wl.fixture_target_version == "v0.1"
    assert len(wl.fields) == 6
    assert all(isinstance(f, WorkloadField) for f in wl.fields)


def test_workload_by_name_indexes_rows(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload(), encoding="utf-8")
    wl = load_workload_md(p)
    row = wl.by_name["`W` (bit-stripe width)"]
    assert row.value == "64"
    assert "BATCH_SIZE" in row.notes


def test_accepts_str_path(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload(), encoding="utf-8")
    wl = load_workload_md(str(p))  # str path, not Path
    assert wl.upstream_commit == VALID_SHA


def test_tbd_value_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload().replace("9024", "TBD"), encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert excinfo.value.subcode == "FIXTURE.WORKLOAD_NOT_PINNED"
    assert "TBD" in str(excinfo.value)


def test_tbd_in_frontmatter_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload().replace("v0.1", "TBD"), encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert excinfo.value.subcode == "FIXTURE.WORKLOAD_NOT_PINNED"


def test_malformed_sha_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload(commit="not-a-sha"), encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert excinfo.value.subcode == "FIXTURE.WORKLOAD_NOT_PINNED"
    assert "upstream_commit malformed" in str(excinfo.value)


def test_uppercase_sha_rejected(tmp_path: Path) -> None:
    """The hex SHA must be lowercase; uppercase is rejected (RFC-0001 §CI gate)."""
    p = tmp_path / "WORKLOAD.md"
    p.write_text(_valid_workload(commit="ABCDEF" + VALID_SHA[6:]), encoding="utf-8")
    with pytest.raises(FixtureError):
        load_workload_md(p)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_workload_md(tmp_path / "does-not-exist.md")


def test_missing_frontmatter_open_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text("# Workload pin\nno frontmatter here\n", encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "no leading `---`" in str(excinfo.value)


def test_missing_frontmatter_close_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(
        "---\n"
        "upstream_repo: https://x\n"
        f"upstream_commit: {VALID_SHA}\n"
        "pinned_at: 2026-05-13\n"
        "pinned_by: x\n"
        "fixture_target_version: v0.1\n",
        encoding="utf-8",
    )
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "no closing `---`" in str(excinfo.value)


def test_frontmatter_missing_colon_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(
        "---\n"
        "upstream_repo somerepo-without-colon\n"
        f"upstream_commit: {VALID_SHA}\n"
        "pinned_at: 2026-05-13\n"
        "pinned_by: x\n"
        "fixture_target_version: v0.1\n"
        "---\n"
        + _table_body(),
        encoding="utf-8",
    )
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "missing `:`" in str(excinfo.value)


def test_frontmatter_missing_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    # Drop the `pinned_by` line.
    body = _valid_workload().replace("pinned_by: tester\n", "")
    p.write_text(body, encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "pinned_by" in str(excinfo.value)


def test_table_not_found_raises(tmp_path: Path) -> None:
    p = tmp_path / "WORKLOAD.md"
    p.write_text(
        "---\n"
        "upstream_repo: https://x\n"
        f"upstream_commit: {VALID_SHA}\n"
        "pinned_at: 2026-05-13\n"
        "pinned_by: x\n"
        "fixture_target_version: v0.1\n"
        "---\n"
        "# no table here\n"
        "just prose\n",
        encoding="utf-8",
    )
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "workload table not found" in str(excinfo.value)


def test_table_wrong_column_count_raises(tmp_path: Path) -> None:
    body = _valid_workload().replace(
        "| `N` (number of test cases) | `prover/prove.rs:67` | 9024 | upstream README example |",
        "| `N` | only-three-cells | row |",
    )
    p = tmp_path / "WORKLOAD.md"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "cells, want 4" in str(excinfo.value)


def test_table_wrong_row_count_raises(tmp_path: Path) -> None:
    """Five rows instead of six."""
    body = _valid_workload().replace(
        "| Entropy source for test-case generation | `program/src/main.rs:83-85` | "
        "SHAKE-256 seeded with kmx bytes | Fiat-Shamir |\n",
        "",
    )
    p = tmp_path / "WORKLOAD.md"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(FixtureError) as excinfo:
        load_workload_md(p)
    assert "rows, want 6" in str(excinfo.value)


def test_frontmatter_blank_lines_are_ignored(tmp_path: Path) -> None:
    """Empty lines inside the frontmatter block are tolerated."""
    body = (
        "---\n"
        "upstream_repo: https://x\n"
        "\n"
        f"upstream_commit: {VALID_SHA}\n"
        "pinned_at: 2026-05-13\n"
        "pinned_by: x\n"
        "fixture_target_version: v0.1\n"
        "---\n"
        + _table_body()
    )
    p = tmp_path / "WORKLOAD.md"
    p.write_text(body, encoding="utf-8")
    wl = load_workload_md(p)
    assert wl.upstream_commit == VALID_SHA


def test_table_terminates_at_non_table_line(tmp_path: Path) -> None:
    """Lines following the table that are not pipe-delimited end the table parse."""
    body = _valid_workload() + "\nSome trailing prose that is not a table row.\n"
    p = tmp_path / "WORKLOAD.md"
    p.write_text(body, encoding="utf-8")
    wl = load_workload_md(p)
    assert len(wl.fields) == 6


def _table_body() -> str:
    """Just the six-row table portion of a valid `WORKLOAD.md`."""
    return dedent(
        """\

        # Workload pin

        | Field | Source location (upstream) | Value | Notes |
        |---|---|---|---|
        | `N` (number of test cases) | `prover/prove.rs:67` | 9024 | upstream README example |
        | Gate count of `C` for one secp256k1 point-add | `program/src/main.rs` | 17000000 | total ops upper bound |
        | `W` (bit-stripe width) | `program/src/main.rs:121` | 64 | `const BATCH_SIZE` |
        | Modular-arithmetic gate count | derived | 2100000 | Toffoli upper bound |
        | Circuit-commitment scheme (SP1 side) | `program/src/main.rs:21-25` | SHA-256 over kmx bytes | verbatim |
        | Entropy source for test-case generation | `program/src/main.rs:83-85` | SHAKE-256 seeded with kmx bytes | Fiat-Shamir |
        """
    )
