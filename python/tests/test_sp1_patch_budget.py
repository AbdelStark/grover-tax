"""Tests for `scripts/check_sp1_patch_budget.sh` (#27)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from grover_tax.paths import repo_root

SCRIPT = repo_root() / "scripts" / "check_sp1_patch_budget.sh"


def _run(env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ}
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_script_exists_and_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_script_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in SCRIPT.read_text(encoding="utf-8")


def test_passes_against_current_patch() -> None:
    """Acceptance: current patch in tree fits the 50/5 budget."""
    result = _run()
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}; stderr:\n{result.stderr}"
    )
    assert "all patches within budget" in result.stdout


def test_default_budgets_match_rfc_0006() -> None:
    """RFC-0006 §"Line budget" caps: 50 for *.rs, 5 for Cargo.toml."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "BUDGET_RS:-50}" in text
    assert "BUDGET_CARGO_TOML:-5}" in text


def test_budget_override_makes_check_fail() -> None:
    """Tightening the budget to 1 line surfaces the (compliant-by-default)
    patch as a violation — confirms the gate is wired and counts correctly."""
    result = _run({"BUDGET_RS": "1"})
    assert result.returncode == 3
    assert "BUILD.SP1_PATCH_FAIL" in result.stderr


def test_handles_empty_patch_dir(tmp_path: Path) -> None:
    """If no patches exist, exit 0 with a `no patches` note."""
    fake_root = tmp_path / "repo"
    (fake_root / "sp1-side-patches").mkdir(parents=True)
    (fake_root / "scripts").mkdir(parents=True)
    # Copy the script into the fake root so its REPO_ROOT resolves correctly.
    target = fake_root / "scripts" / "check_sp1_patch_budget.sh"
    target.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o755)
    result = subprocess.run(
        ["bash", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "no patches" in result.stdout
