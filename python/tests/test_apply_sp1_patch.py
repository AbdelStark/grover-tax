"""Tests for `scripts/apply_sp1_patch.sh` (#26)."""

from __future__ import annotations

import os
import subprocess

from grover_tax.paths import repo_root

APPLY = repo_root() / "scripts" / "apply_sp1_patch.sh"


def _run() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(APPLY)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_apply_script_exists() -> None:
    assert APPLY.is_file()
    assert os.access(APPLY, os.X_OK)


def test_apply_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in APPLY.read_text(encoding="utf-8")


def test_apply_reports_subcode_on_drift() -> None:
    """Today's patch is a sketch and intentionally fails to apply against
    the pinned upstream — the test asserts the script surfaces this as
    `BUILD.SP1_PATCH_FAIL` (exit 3), not as a silent success or arbitrary
    failure. When the patch is refreshed to apply cleanly, this test
    naturally inverts (exit 0 + "all patches applied")."""
    result = _run()
    # Either exit 3 with the right subcode, *or* exit 0 with the
    # success message (once the patch is refreshed to apply cleanly).
    if result.returncode == 0:
        assert "applied" in result.stdout
    else:
        assert result.returncode == 3
        assert "BUILD.SP1_PATCH_FAIL" in result.stderr


def test_apply_reports_helpful_remediation_on_failure() -> None:
    """The error message names the common causes (drift, uncommitted
    changes, re-pin) so the operator knows where to look."""
    result = _run()
    if result.returncode == 3:
        assert "WORKLOAD.md.upstream_commit" in result.stderr
        assert "Re-pinning" in result.stderr
