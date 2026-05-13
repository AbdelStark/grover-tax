"""Tests for `scripts/check_gpu_residency.sh`."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import pytest

from grover_tax.paths import repo_root

SCRIPT = repo_root() / "scripts" / "check_gpu_residency.sh"


def _stub(tmp_path: Path, name: str, body: str) -> Path:
    """Write an executable bash stub to `tmp_path/<name>` and return its path."""
    p = tmp_path / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    p.chmod(0o755)
    return p


def _run(
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
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


# -- macOS path ----------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only stub path")
def test_macos_under_threshold(tmp_path: Path) -> None:
    """Powermetrics emits 0.1 mW (under 500 mW threshold) → exit 0."""
    stub = _stub(
        tmp_path,
        "powermetrics_stub.sh",
        'echo "GPU Power: 0.1 mW"\n',
    )
    result = _run({"MACOS_POWERMETRICS_CMD": str(stub)})
    assert result.returncode == 0, result.stderr
    assert "gpu_residency platform=darwin probe=powermetrics power=0.1mW" in result.stdout


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only stub path")
def test_macos_over_threshold(tmp_path: Path) -> None:
    """1.0 mW > 0.5 mW threshold → exit 1, MEASUREMENT.GPU_RESIDENT."""
    stub = _stub(
        tmp_path,
        "powermetrics_stub.sh",
        'echo "GPU Power: 750.0 mW"\n',
    )
    result = _run({"MACOS_POWERMETRICS_CMD": str(stub)})
    assert result.returncode == 1
    assert "MEASUREMENT.GPU_RESIDENT" in result.stderr
    assert "750" in result.stderr


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only stub path")
def test_macos_handles_watts_unit(tmp_path: Path) -> None:
    """Some hosts emit 'GPU Power: 0.3 W' instead of mW; convert and compare."""
    stub = _stub(
        tmp_path,
        "powermetrics_stub.sh",
        'echo "GPU Active Power: 0.3 W"\n',
    )
    # 0.3 W = 300 mW; threshold is 500 mW → 300 ≤ 500 → exit 0.
    result = _run({"MACOS_POWERMETRICS_CMD": str(stub)})
    assert result.returncode == 0, result.stderr
    assert "power=300mW" in result.stdout


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only stub path")
def test_macos_unparseable_output_exits_2(tmp_path: Path) -> None:
    stub = _stub(tmp_path, "powermetrics_stub.sh", 'echo "totally unrelated text"\n')
    result = _run({"MACOS_POWERMETRICS_CMD": str(stub)})
    assert result.returncode == 2


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only stub path")
def test_macos_probe_failure_exits_2(tmp_path: Path) -> None:
    """If the stub itself exits non-zero, the script reports probe failure."""
    stub = _stub(tmp_path, "powermetrics_stub.sh", "exit 7\n")
    result = _run({"MACOS_POWERMETRICS_CMD": str(stub)})
    assert result.returncode == 2
    assert "powermetrics probe failed" in result.stderr


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only stub path")
def test_macos_custom_threshold(tmp_path: Path) -> None:
    """Drop the threshold to 1 mW; even 5 mW now trips the gate."""
    stub = _stub(tmp_path, "powermetrics_stub.sh", 'echo "GPU Power: 5.0 mW"\n')
    result = _run(
        {
            "MACOS_POWERMETRICS_CMD": str(stub),
            "THRESHOLD_MACOS_MW": "1",
        }
    )
    assert result.returncode == 1


# -- Linux paths (run on any platform by forcing the dispatcher) ---------------


def test_linux_no_gpu_path_exits_0() -> None:
    """If nvidia-smi and rocm-smi are both absent (Linux), exit 0 with the
    "no GPU detected" message. We exercise this by spawning a fresh bash
    with a stripped PATH that contains nothing GPU-related.

    Skip on Darwin — the platform dispatcher would never reach this branch.
    """
    if platform.system() != "Linux":
        pytest.skip("Linux-specific dispatcher path")
    # Strip PATH to bare /usr/bin + /bin so nvidia-smi / rocm-smi can't be
    # resolved. POSIX utilities still available.
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "no GPU detected" in result.stderr


def test_threshold_constants_default_match_rfc_0009() -> None:
    """Static check: defaults inside the script match RFC-0009."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "THRESHOLD_MACOS_MW:-500" in text  # 0.5 W per RFC-0009
    assert "THRESHOLD_LINUX_MW:-1000" in text  # 1 W per RFC-0009


def test_script_emits_structured_line_format(tmp_path: Path) -> None:
    """Static check: script grep-friendly output shape."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "gpu_residency platform=" in text
    assert "probe=" in text
    assert "power=" in text
    assert "threshold=" in text
