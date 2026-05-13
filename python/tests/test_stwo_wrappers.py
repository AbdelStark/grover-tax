"""Smoke tests for `bin/run_stwo.sh` and `bin/verify_stwo.sh` preconditions.

Symmetric with `test_sp1_wrappers.py` — by intent, since RFC-0007 §"Symmetry
CI check" depends on both wrappers honouring the same contract. The full
symmetry assertion (paths agree, env-check lines match) lives in #30; this
file covers the Stwo-specific preconditions in isolation so a Stwo-side
regression is caught locally too.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from grover_tax.paths import repo_root

RUN_STWO = repo_root() / "bin" / "run_stwo.sh"
VERIFY_STWO = repo_root() / "bin" / "verify_stwo.sh"


def _env_with_required_caps() -> dict[str, str]:
    return {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "",
        "RAYON_NUM_THREADS": "1",
        "TOKIO_WORKER_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(RUN_STWO), *args],
        env=env if env is not None else _env_with_required_caps(),
        capture_output=True,
        text=True,
        check=False,
    )


def _verify(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(VERIFY_STWO), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_stwo_exists_and_is_executable() -> None:
    assert RUN_STWO.is_file()
    assert os.access(RUN_STWO, os.X_OK)


def test_verify_stwo_exists_and_is_executable() -> None:
    assert VERIFY_STWO.is_file()
    assert os.access(VERIFY_STWO, os.X_OK)


def test_run_stwo_uses_set_euo_pipefail() -> None:
    text = RUN_STWO.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_verify_stwo_uses_set_euo_pipefail() -> None:
    text = VERIFY_STWO.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_run_stwo_zero_args_exits_2() -> None:
    result = _run([])
    assert result.returncode == 2
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr


def test_run_stwo_three_args_exits_2() -> None:
    result = _run(["/tmp/x", "/tmp/y", "/tmp/z"])
    assert result.returncode == 2


def test_run_stwo_missing_fixture_exits_2(tmp_path: Path) -> None:
    result = _run([str(tmp_path / "nope.json"), str(tmp_path / "proof.bin")])
    assert result.returncode == 2
    assert "fixtures file not readable" in result.stderr


@pytest.mark.parametrize(
    "missing_var",
    ["CUDA_VISIBLE_DEVICES", "RAYON_NUM_THREADS", "TOKIO_WORKER_THREADS", "OMP_NUM_THREADS"],
)
def test_run_stwo_missing_env_var_exits_2(missing_var: str, tmp_path: Path) -> None:
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_with_required_caps()
    env.pop(missing_var, None)
    result = _run([str(fixture), str(tmp_path / "proof.bin")], env=env)
    assert result.returncode == 2
    assert missing_var in result.stderr


def test_run_stwo_no_binary_exits_3(tmp_path: Path) -> None:
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_with_required_caps()
    env["STWO_BINARY"] = str(tmp_path / "no-such-binary")
    result = _run([str(fixture), str(tmp_path / "proof.bin")], env=env)
    assert result.returncode == 3
    assert "BUILD.STWO_SHA_DRIFT" in result.stderr


def test_verify_stwo_zero_args_exits_2() -> None:
    result = _verify([])
    assert result.returncode == 2


def test_verify_stwo_missing_proof_exits_2(tmp_path: Path) -> None:
    result = _verify([str(tmp_path / "nope.bin")])
    assert result.returncode == 2
    assert "proof not readable" in result.stderr


def test_verify_stwo_missing_fixture_exits_2(tmp_path: Path) -> None:
    proof = tmp_path / "proof.bin"
    proof.write_bytes(b"\x00" * 16)
    result = _verify([str(proof)], cwd=str(tmp_path))
    assert result.returncode == 2
    assert "fixtures/v0.1.json" in result.stderr


def test_run_stwo_writes_proof_atomically_via_mv() -> None:
    text = RUN_STWO.read_text(encoding="utf-8")
    assert ".partial" in text
    assert 'mv -- "${TMP_PROOF}"' in text


def test_run_stwo_writes_constraints_and_trace_rows_check() -> None:
    # Grammar enforcement moved into scripts/wrapper_lib.sh (#31). The
    # wrapper sources the lib at runtime, so the strings live across both
    # files now; check the combined text.
    wrapper_text = RUN_STWO.read_text(encoding="utf-8")
    lib_text = (repo_root() / "scripts" / "wrapper_lib.sh").read_text(encoding="utf-8")
    combined = wrapper_text + "\n" + lib_text
    assert "enforce_proverlog_grammar" in wrapper_text
    assert "CONSTRAINTS:" in combined
    assert "TRACE_ROWS:" in combined
    assert "PROVER.STDOUT_GRAMMAR_VIOLATION" in combined
