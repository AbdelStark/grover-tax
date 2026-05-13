"""Tests for `scripts/wrapper_lib.sh` — the shared wrapper helpers.

Covers the exactly-once grammar contract from issue #31 plus the cross-
prover semantics of `require_env` and `resolve_affinity`. The wider
symmetry suite lives in `test_wrapper_symmetry.py`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from grover_tax.paths import repo_root

WRAPPER_LIB = repo_root() / "scripts" / "wrapper_lib.sh"


def _bash(snippet: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run an inline bash snippet that sources `wrapper_lib.sh`.

    `set -euo pipefail` is on so the lib's `exit N` calls propagate.
    """
    full = f"set -euo pipefail\nsource {WRAPPER_LIB}\n{snippet}\n"
    return subprocess.run(
        ["bash", "-c", full],
        env=env if env is not None else {**os.environ},
        capture_output=True,
        text=True,
        check=False,
    )


# -- enforce_proverlog_grammar -------------------------------------------------


def _write_log(tmp_path: Path, contents: str) -> Path:
    p = tmp_path / "proverlog.txt"
    p.write_text(contents, encoding="utf-8")
    return p


def test_grammar_one_of_each_passes(tmp_path: Path) -> None:
    log = _write_log(
        tmp_path,
        "noise\nCONSTRAINTS: 12345\nmore noise\nTRACE_ROWS:    98765\nstill noise\n",
    )
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 0, result.stderr


def test_grammar_zero_constraints_fails(tmp_path: Path) -> None:
    log = _write_log(tmp_path, "TRACE_ROWS:  42\nnothing else here\n")
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 1
    assert "PROVER.STDOUT_GRAMMAR_VIOLATION" in result.stderr
    assert "CONSTRAINTS" in result.stderr
    assert "found 0" in result.stderr


def test_grammar_zero_trace_rows_fails(tmp_path: Path) -> None:
    log = _write_log(tmp_path, "CONSTRAINTS: 42\n")
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 1
    assert "TRACE_ROWS" in result.stderr


def test_grammar_two_constraints_fails(tmp_path: Path) -> None:
    """RFC-0010 / L-INV-1: exactly one occurrence per invocation."""
    log = _write_log(
        tmp_path,
        "CONSTRAINTS: 1\nTRACE_ROWS: 2\nCONSTRAINTS: 3\n",
    )
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 1
    assert "found 2" in result.stderr


def test_grammar_two_trace_rows_fails(tmp_path: Path) -> None:
    log = _write_log(
        tmp_path,
        "CONSTRAINTS: 1\nTRACE_ROWS:    2\nTRACE_ROWS:  4\n",
    )
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 1
    assert "found 2" in result.stderr
    assert "TRACE_ROWS" in result.stderr


def test_grammar_negative_integer_fails(tmp_path: Path) -> None:
    """L-INV-2: non-negative decimal integers."""
    log = _write_log(tmp_path, "CONSTRAINTS: -1\nTRACE_ROWS: 2\n")
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 1
    # The line doesn't match `^CONSTRAINTS: [0-9]+$`, so the count is 0.
    assert "found 0" in result.stderr


def test_grammar_non_decimal_fails(tmp_path: Path) -> None:
    log = _write_log(tmp_path, "CONSTRAINTS: 0xFF\nTRACE_ROWS:  2\n")
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 1


def test_grammar_constraints_must_be_at_line_start(tmp_path: Path) -> None:
    """Line-anchored regex — embedded matches don't count."""
    log = _write_log(
        tmp_path,
        "logged: CONSTRAINTS: 1234 (embedded)\nTRACE_ROWS:  5\nCONSTRAINTS: 9\n",
    )
    result = _bash(f"enforce_proverlog_grammar {log}")
    assert result.returncode == 0  # only the line-anchored ones count


# -- require_env ---------------------------------------------------------------


def test_require_env_unset_var_fails() -> None:
    env = {k: v for k, v in os.environ.items() if k != "RAYON_NUM_THREADS"}
    result = _bash("require_env RAYON_NUM_THREADS 1", env=env)
    assert result.returncode == 2
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr
    assert "RAYON_NUM_THREADS" in result.stderr
    assert "__UNSET__" in result.stderr


def test_require_env_wrong_value_fails() -> None:
    env = {**os.environ, "RAYON_NUM_THREADS": "4"}
    result = _bash("require_env RAYON_NUM_THREADS 1", env=env)
    assert result.returncode == 2


def test_require_env_correct_value_passes() -> None:
    env = {**os.environ, "RAYON_NUM_THREADS": "1"}
    result = _bash("require_env RAYON_NUM_THREADS 1", env=env)
    assert result.returncode == 0


def test_require_env_empty_string_accepted_when_required() -> None:
    """CUDA_VISIBLE_DEVICES='' (literal empty) must satisfy require_env. The
    `${VAR-...}` form distinguishes 'unset' from 'empty'."""
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    result = _bash("require_env CUDA_VISIBLE_DEVICES ''", env=env)
    assert result.returncode == 0


# -- resolve_affinity ----------------------------------------------------------


def test_resolve_affinity_returns_tokens_on_current_platform() -> None:
    """On macOS or Linux, the function returns the right prefix."""
    result = _bash("resolve_affinity")
    assert result.returncode == 0, result.stderr
    text = result.stdout.strip()
    if subprocess.run(["uname"], capture_output=True, text=True, check=True).stdout.strip() == "Darwin":
        assert text == "taskpolicy -c utility"
    else:
        assert text == "taskset -c 0"
