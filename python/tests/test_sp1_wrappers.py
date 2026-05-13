"""Smoke tests for `bin/run_sp1.sh` and `bin/verify_sp1.sh` preconditions.

Covers the precondition matrix specified in RFC-0007: argv shape, env vars,
affinity, missing files. The full wrapper-symmetry test (W-T1 / I-1) is in
#30 (`test_wrapper_symmetry.py`); the post-prover happy-path test (W-T5
grammar) needs a real SP1 binary and is also out of scope here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from grover_tax.paths import repo_root

RUN_SP1 = repo_root() / "bin" / "run_sp1.sh"
VERIFY_SP1 = repo_root() / "bin" / "verify_sp1.sh"


def _env_with_required_caps() -> dict[str, str]:
    """The four env caps every prover invocation requires (RFC-0007 §C2)."""
    return {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "",
        "RAYON_NUM_THREADS": "1",
        "TOKIO_WORKER_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(RUN_SP1), *args],
        env=env if env is not None else _env_with_required_caps(),
        capture_output=True,
        text=True,
        check=False,
    )


def _verify(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(VERIFY_SP1), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_sp1_exists_and_is_executable() -> None:
    assert RUN_SP1.is_file()
    assert os.access(RUN_SP1, os.X_OK)


def test_verify_sp1_exists_and_is_executable() -> None:
    assert VERIFY_SP1.is_file()
    assert os.access(VERIFY_SP1, os.X_OK)


def test_run_sp1_uses_set_euo_pipefail() -> None:
    """Required by RFC-0007 §"Wrapper internals" — `set -euo pipefail` at top."""
    text = RUN_SP1.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_verify_sp1_uses_set_euo_pipefail() -> None:
    text = VERIFY_SP1.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


# -- bin/run_sp1.sh preconditions ----------------------------------------------


def test_run_sp1_zero_args_exits_2() -> None:
    result = _run([])
    assert result.returncode == 2
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr


def test_run_sp1_one_arg_exits_2() -> None:
    result = _run(["/tmp/x"])
    assert result.returncode == 2


def test_run_sp1_three_args_exits_2() -> None:
    result = _run(["/tmp/x", "/tmp/y", "/tmp/z"])
    assert result.returncode == 2


def test_run_sp1_missing_fixture_exits_2(tmp_path: Path) -> None:
    result = _run([str(tmp_path / "nope.json"), str(tmp_path / "proof.bin")])
    assert result.returncode == 2
    assert "fixtures file not readable" in result.stderr


@pytest.mark.parametrize(
    "missing_var", ["CUDA_VISIBLE_DEVICES", "RAYON_NUM_THREADS", "TOKIO_WORKER_THREADS", "OMP_NUM_THREADS"]
)
def test_run_sp1_missing_env_var_exits_2(missing_var: str, tmp_path: Path) -> None:
    """Every one of the four caps is checked individually."""
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_with_required_caps()
    env.pop(missing_var, None)
    result = _run([str(fixture), str(tmp_path / "proof.bin")], env=env)
    assert result.returncode == 2
    assert missing_var in result.stderr
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr


def test_run_sp1_wrong_env_var_value_exits_2(tmp_path: Path) -> None:
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_with_required_caps()
    env["RAYON_NUM_THREADS"] = "4"  # not 1
    result = _run([str(fixture), str(tmp_path / "proof.bin")], env=env)
    assert result.returncode == 2
    assert "RAYON_NUM_THREADS" in result.stderr


def test_run_sp1_no_binary_exits_3(tmp_path: Path) -> None:
    """When the SP1 prover binary doesn't exist, exit 3 (`BUILD.SP1_PATCH_FAIL`)."""
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_with_required_caps()
    env["SP1_BINARY"] = str(tmp_path / "no-such-binary")
    result = _run([str(fixture), str(tmp_path / "proof.bin")], env=env)
    assert result.returncode == 3
    assert "BUILD.SP1_PATCH_FAIL" in result.stderr


# -- bin/verify_sp1.sh preconditions -------------------------------------------


def test_verify_sp1_zero_args_exits_2() -> None:
    result = _verify([])
    assert result.returncode == 2


def test_verify_sp1_two_args_exits_2() -> None:
    result = _verify(["/tmp/a", "/tmp/b"])
    assert result.returncode == 2


def test_verify_sp1_missing_proof_exits_2(tmp_path: Path) -> None:
    result = _verify([str(tmp_path / "nope.bin")])
    assert result.returncode == 2
    assert "proof not readable" in result.stderr


def test_verify_sp1_missing_fixture_exits_2(tmp_path: Path) -> None:
    """If `$(pwd)/fixtures/v0.1.json` doesn't exist, exit 2."""
    proof = tmp_path / "proof.bin"
    proof.write_bytes(b"\x00" * 16)
    result = _verify([str(proof)], cwd=str(tmp_path))
    assert result.returncode == 2
    assert "fixtures/v0.1.json" in result.stderr


# -- Wrapper contract --------------------------------------------------------


def test_run_sp1_writes_proof_atomically_via_mv(tmp_path: Path) -> None:
    """Static check: the source uses `mv -- "${TMP_PROOF}" ...` for atomicity.

    (The runtime behaviour requires a real SP1 binary; this static check is
    cheap and catches a refactor that drops the temp-then-rename pattern.)
    """
    text = RUN_SP1.read_text(encoding="utf-8")
    assert ".partial" in text
    assert 'mv -- "${TMP_PROOF}"' in text


def test_run_sp1_writes_constraints_and_trace_rows_check(tmp_path: Path) -> None:
    """Static check: the wrapper enforces the M7 grammar (via the sourced lib)."""
    wrapper_text = RUN_SP1.read_text(encoding="utf-8")
    lib_text = (repo_root() / "scripts" / "wrapper_lib.sh").read_text(encoding="utf-8")
    combined = wrapper_text + "\n" + lib_text
    assert "enforce_proverlog_grammar" in wrapper_text
    assert "CONSTRAINTS:" in combined
    assert "TRACE_ROWS:" in combined
    assert "PROVER.STDOUT_GRAMMAR_VIOLATION" in combined
