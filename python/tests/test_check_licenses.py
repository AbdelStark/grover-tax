"""Tests for `scripts/check_licenses.sh`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from grover_tax.paths import repo_root

SCRIPT = repo_root() / "scripts" / "check_licenses.sh"


def _run(env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env if env is not None else {**os.environ},
        capture_output=True,
        text=True,
        check=False,
    )


def _run_isolated(repo_root_override: Path, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the script after copying it into a synthetic repo root.

    The script resolves `REPO_ROOT` from its own location, so we copy it
    into `<override>/scripts/check_licenses.sh` and `git init` if needed.
    """
    target = repo_root_override / "scripts" / "check_licenses.sh"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(target)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_passes_against_current_repo() -> None:
    """Acceptance: clean repo state validates."""
    result = _run()
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}; stderr:\n{result.stderr}"
    )


def test_gpl_submodule_makes_check_fail(tmp_path: Path) -> None:
    """Acceptance: a synthetic GPL submodule trips the check."""
    # Stage a synthetic repo containing one submodule whose LICENSE is GPL.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".gitmodules").write_text(
        "[submodule \"gpl-fake\"]\n\tpath = vendor/gpl-fake\n\turl = https://example.invalid/gpl-fake\n",
        encoding="utf-8",
    )
    sub = tmp_path / "vendor" / "gpl-fake"
    sub.mkdir(parents=True)
    (sub / "LICENSE").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n", encoding="utf-8"
    )
    result = _run_isolated(tmp_path)
    assert result.returncode == 3
    assert "BUILD.LICENSE_CHECK_FAIL" in result.stderr
    assert "gpl-fake" in result.stderr


def test_mit_submodule_passes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".gitmodules").write_text(
        "[submodule \"mit-fake\"]\n\tpath = vendor/mit-fake\n\turl = https://example.invalid/mit-fake\n",
        encoding="utf-8",
    )
    sub = tmp_path / "vendor" / "mit-fake"
    sub.mkdir(parents=True)
    (sub / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n",
        encoding="utf-8",
    )
    result = _run_isolated(tmp_path)
    assert result.returncode == 0, result.stderr


def test_submodule_with_no_license_file_fails(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".gitmodules").write_text(
        "[submodule \"missing\"]\n\tpath = vendor/missing\n\turl = https://example.invalid/missing\n",
        encoding="utf-8",
    )
    sub = tmp_path / "vendor" / "missing"
    sub.mkdir(parents=True)
    result = _run_isolated(tmp_path)
    assert result.returncode == 3
    assert "no LICENSE file found" in result.stderr


def test_apache_submodule_passes(tmp_path: Path) -> None:
    """Apache-2.0 is MIT-compatible per RFC-0014 §"Licensing"."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".gitmodules").write_text(
        "[submodule \"apache-fake\"]\n\tpath = vendor/apache-fake\n\turl = https://example.invalid/apache-fake\n",
        encoding="utf-8",
    )
    sub = tmp_path / "vendor" / "apache-fake"
    sub.mkdir(parents=True)
    (sub / "LICENSE").write_text(
        "Apache License, Version 2.0\n", encoding="utf-8"
    )
    result = _run_isolated(tmp_path)
    assert result.returncode == 0, result.stderr


def test_lockfile_gpl_dependency_fails(tmp_path: Path) -> None:
    """A `license = "GPL-3.0"` entry in `uv.lock` fails the gate."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "gpl-pkg"\nversion = "1.0.0"\nlicense = "GPL-3.0"\n',
        encoding="utf-8",
    )
    (tmp_path / ".gitmodules").write_text("", encoding="utf-8")
    result = _run_isolated(tmp_path)
    assert result.returncode == 3
    assert "gpl-pkg" in result.stderr


def test_lockfile_dual_license_with_compatible_disjunct_passes(tmp_path: Path) -> None:
    """`MIT OR Apache-2.0` is acceptable (compatible disjunct exists)."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "dual"\nversion = "1.0.0"\nlicense = "MIT OR Apache-2.0"\n',
        encoding="utf-8",
    )
    (tmp_path / ".gitmodules").write_text("", encoding="utf-8")
    result = _run_isolated(tmp_path)
    assert result.returncode == 0, result.stderr


def test_allow_license_regex_override(tmp_path: Path) -> None:
    """Permitting AGPL via the env override widens the accepted set."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "agpl-pkg"\nversion = "1.0.0"\nlicense = "AGPL-3.0"\n',
        encoding="utf-8",
    )
    (tmp_path / ".gitmodules").write_text("", encoding="utf-8")
    result = _run_isolated(tmp_path, env_extra={"ALLOW_LICENSE_REGEX": "^agpl-3\\.0$"})
    assert result.returncode == 0, result.stderr


def test_no_gitmodules_no_lockfile_passes(tmp_path: Path) -> None:
    """If neither file exists, the gate has nothing to check → exit 0."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    result = _run_isolated(tmp_path)
    assert result.returncode == 0, result.stderr
