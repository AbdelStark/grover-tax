"""Tests for `scripts/run_all.sh` (#37)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from grover_tax.paths import repo_root

RUN_ALL = repo_root() / "scripts" / "run_all.sh"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(RUN_ALL), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_all_exists_and_executable() -> None:
    assert RUN_ALL.is_file()
    assert os.access(RUN_ALL, os.X_OK)


def test_run_all_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in RUN_ALL.read_text(encoding="utf-8")


def test_run_all_sources_locale_env() -> None:
    assert "scripts/locale_env.sh" in RUN_ALL.read_text(encoding="utf-8")


def test_run_all_help_exits_zero() -> None:
    result = _run(["--help"])
    assert result.returncode == 0
    assert "Usage:" in result.stderr


def test_run_all_unknown_flag_exits_two() -> None:
    result = _run(["--bogus"])
    assert result.returncode == 2


def test_run_all_invalid_day_exits_two() -> None:
    result = _run(["--day", "3"])
    assert result.returncode == 2
    assert "--day must be 1 or 2" in result.stderr


def test_run_all_traps_cleanup() -> None:
    """Trap installs cleanup.sh on every exit path."""
    text = RUN_ALL.read_text(encoding="utf-8")
    assert 'trap ' in text
    assert "scripts/cleanup.sh" in text


def test_run_all_pins_thermal_cooldown() -> None:
    """RFC-0010 §"Thermal protocol" — 5 min default cool-down."""
    text = RUN_ALL.read_text(encoding="utf-8")
    assert "COOLDOWN_SECONDS=300" in text


def test_run_all_orchestrates_both_days() -> None:
    """`--day 2` reverses the order per RFC-0010 stability protocol."""
    text = RUN_ALL.read_text(encoding="utf-8")
    assert "order=(sp1 stwo)" in text
    assert "order=(stwo sp1)" in text


def test_run_all_calls_init_submodules_first() -> None:
    """Step ordering: submodules → uv sync → versions → licenses → build → fixture → preflight → measure → analyze."""
    text = RUN_ALL.read_text(encoding="utf-8")
    init = text.find("scripts/init_submodules.sh")
    uv_sync = text.find("uv sync --frozen")
    versions = text.find("scripts/lock_versions.sh")
    licenses = text.find("scripts/check_licenses.sh")
    preflight = text.find("scripts/preflight.sh")
    measure = text.find("scripts/measure.sh")
    assert 0 < init < uv_sync < versions < licenses < preflight < measure
