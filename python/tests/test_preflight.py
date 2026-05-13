"""Tests for `scripts/preflight.sh` + `scripts/cleanup.sh` (#36)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from grover_tax.paths import repo_root

PREFLIGHT = repo_root() / "scripts" / "preflight.sh"
CLEANUP = repo_root() / "scripts" / "cleanup.sh"


def _env_clean(state_path: Path, **extra: str) -> dict[str, str]:
    """Build an environment where every check is either set up to pass or
    skipped — the clean baseline."""
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "",
        "RAYON_NUM_THREADS": "1",
        "TOKIO_WORKER_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "PREFLIGHT_STATE_PATH": str(state_path),
        "SKIP_VERSIONS_DRIFT": "1",
        "SKIP_LOWPOWER": "1",
        "SKIP_AC_POWER": "1",
        "SKIP_GPU_RESIDENCY": "1",
        "SKIP_SWAP": "1",
        "SKIP_GOVERNOR": "1",
    }
    env.update(extra)
    return env


def _run(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# -- preflight ---------------------------------------------------------------


def test_preflight_clean_baseline_exits_zero(tmp_path: Path) -> None:
    state = tmp_path / "preflight.json"
    result = _run(PREFLIGHT, _env_clean(state))
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout
    assert state.is_file()
    recorded = json.loads(state.read_text(encoding="utf-8"))
    assert "platform" in recorded
    assert recorded["platform"] in {"darwin", "linux"}


@pytest.mark.parametrize(
    "missing_var",
    ["CUDA_VISIBLE_DEVICES", "RAYON_NUM_THREADS", "TOKIO_WORKER_THREADS", "OMP_NUM_THREADS"],
)
def test_preflight_env_var_violation_exits_five(missing_var: str, tmp_path: Path) -> None:
    state = tmp_path / "preflight.json"
    env = _env_clean(state)
    env.pop(missing_var, None)
    result = _run(PREFLIGHT, env)
    assert result.returncode == 5
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr
    assert missing_var in result.stderr


def test_preflight_wrong_env_var_value_exits_five(tmp_path: Path) -> None:
    state = tmp_path / "preflight.json"
    env = _env_clean(state)
    env["RAYON_NUM_THREADS"] = "8"
    result = _run(PREFLIGHT, env)
    assert result.returncode == 5
    assert "RAYON_NUM_THREADS" in result.stderr


def test_preflight_records_prior_state(tmp_path: Path) -> None:
    state = tmp_path / "preflight.json"
    _run(PREFLIGHT, _env_clean(state))
    recorded = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(recorded, dict)
    assert recorded.get("platform") in {"darwin", "linux"}


# -- cleanup -----------------------------------------------------------------


def test_cleanup_removes_state_file(tmp_path: Path) -> None:
    state = tmp_path / "preflight.json"
    # Preflight writes the state…
    _run(PREFLIGHT, _env_clean(state))
    assert state.is_file()
    # …cleanup removes it.
    result = _run(CLEANUP, {**os.environ, "PREFLIGHT_STATE_PATH": str(state)})
    assert result.returncode == 0
    assert not state.exists()
    assert "state file removed" in result.stdout


def test_cleanup_is_noop_when_no_state_file(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_state.json"
    result = _run(CLEANUP, {**os.environ, "PREFLIGHT_STATE_PATH": str(missing)})
    assert result.returncode == 0
    assert "nothing to restore" in result.stdout


# -- static structure --------------------------------------------------------


def test_preflight_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in PREFLIGHT.read_text(encoding="utf-8")


def test_cleanup_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in CLEANUP.read_text(encoding="utf-8")


def test_preflight_sources_locale_env() -> None:
    """RFC-0013 §"Locale neutrality" — preflight applies the LANG/LC_ALL/TZ
    exports before any subprocess. Static check: the source line is present."""
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "scripts/locale_env.sh" in text
