"""Tests for `scripts/measure.sh` (#32)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from grover_tax.paths import repo_root

MEASURE = repo_root() / "scripts" / "measure.sh"


def _run(args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(MEASURE), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_measure_exists_and_executable() -> None:
    assert MEASURE.is_file()
    assert os.access(MEASURE, os.X_OK)


def test_measure_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in MEASURE.read_text(encoding="utf-8")


def test_measure_sources_locale_env() -> None:
    """RFC-0013 §"Locale neutrality"."""
    text = MEASURE.read_text(encoding="utf-8")
    assert "scripts/locale_env.sh" in text


def test_measure_zero_args_exits_2() -> None:
    result = _run([])
    assert result.returncode == 2
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr


def test_measure_one_arg_exits_2() -> None:
    result = _run(["sp1"])
    assert result.returncode == 2


def test_measure_three_args_exits_2() -> None:
    result = _run(["sp1", "r1", "extra"])
    assert result.returncode == 2


def test_measure_invalid_prover_exits_2() -> None:
    result = _run(["groth16", "r1"])
    assert result.returncode == 2
    assert "must be" in result.stderr


def test_measure_pins_hyperfine_sample_counts() -> None:
    """RFC-0008 hard-pinned counts: warmup 1 / runs 10 for prove, warmup 3 / runs 50 for verify."""
    text = MEASURE.read_text(encoding="utf-8")
    assert "HYPERFINE_PROVE_WARMUP" in text
    assert "HYPERFINE_PROVE_RUNS" in text
    assert "HYPERFINE_VERIFY_WARMUP" in text
    assert "HYPERFINE_VERIFY_RUNS" in text
    # Defaults match RFC-0008.
    assert ":-1}" in text and ":-10}" in text
    assert ":-3}" in text and ":-50}" in text


def test_measure_exits_5_when_hyperfine_missing(tmp_path: Path) -> None:
    """With a PATH that has no hyperfine, the tool-presence check fails."""
    if shutil.which("hyperfine"):
        # On this rig hyperfine is missing already, but in case CI ever
        # installs it, simulate absence via a stripped PATH.
        env_extra = {"PATH": "/usr/bin:/bin"}
    else:
        env_extra = None
    result = _run(["sp1", "test"], env_extra=env_extra)
    # On a host without hyperfine, exit 5 with `MEASUREMENT.ENV_VAR_MISS`.
    assert result.returncode == 5
    assert "hyperfine" in result.stderr
