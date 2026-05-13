"""Unit tests for `grover_tax.paths`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from grover_tax import paths


def _clear_repo_root_cache() -> None:
    paths.repo_root.cache_clear()


def test_repo_root_finds_pyproject() -> None:
    _clear_repo_root_cache()
    try:
        root = paths.repo_root()
    finally:
        _clear_repo_root_cache()
    assert (root / "pyproject.toml").is_file()


def test_repo_root_is_cached() -> None:
    _clear_repo_root_cache()
    try:
        first = paths.repo_root()
        second = paths.repo_root()
    finally:
        _clear_repo_root_cache()
    assert first is second


def test_repo_root_raises_when_marker_missing(tmp_path: Path) -> None:
    _clear_repo_root_cache()
    try:
        with patch("grover_tax.paths.__file__", str(tmp_path / "grover_tax" / "paths.py")):
            with pytest.raises(FileNotFoundError) as excinfo:
                paths.repo_root()
    finally:
        _clear_repo_root_cache()
    assert "pyproject.toml" in str(excinfo.value)


def test_workload_md_path() -> None:
    _clear_repo_root_cache()
    try:
        p = paths.workload_md_path()
    finally:
        _clear_repo_root_cache()
    assert p.name == "WORKLOAD.md"
    assert p.is_file()


def test_path_accessors_return_repo_relative_subpaths() -> None:
    """Every accessor lives under repo_root() and has the expected leaf name."""
    _clear_repo_root_cache()
    try:
        root = paths.repo_root()
        assert paths.fixtures_dir() == root / "fixtures"
        assert paths.fixture_path("v0.1") == root / "fixtures" / "v0.1.json"
        assert paths.fixture_path() == root / "fixtures" / "v0.1.json"
        assert paths.results_dir() == root / "results"
        assert paths.plots_dir() == root / "results" / "plots"
        assert paths.discards_log_path() == root / "results" / "discards.log"
        assert paths.schemas_dir() == root / "docs" / "spec" / "schemas"
        assert paths.versions_lock_path() == root / "versions.lock"
    finally:
        _clear_repo_root_cache()


def test_fixture_path_accepts_arbitrary_version_label() -> None:
    _clear_repo_root_cache()
    try:
        p = paths.fixture_path("v9.9")
    finally:
        _clear_repo_root_cache()
    assert p.name == "v9.9.json"
