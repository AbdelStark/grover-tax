"""Wrapper symmetry CI test (I-1 in `07-testing-strategy.md`).

RFC-0007 §"Symmetry CI check" treats SP1↔Stwo wrapper symmetry as a
soundness requirement: if the two scripts diverge in argument shape,
env-var checks, affinity discipline, atomicity, or grammar enforcement,
the measurement script is forced to special-case one prover and the
comparison becomes "SP1 under regime A vs Stwo under regime B" — a
different benchmark.

This test asserts the two pairs of wrappers (#28 and #29) share the
load-bearing structure. Tests are stub-only — they read the script
sources and exercise the precondition matrix; they do not invoke the
real provers (those need binaries that may not be built on every
contributor's machine).

The acceptance criteria for #30:

* All structural and behavioural symmetry checks pass.
* The exit-code matrix from RFC-0007 §"Exit codes" is exercised for
  every documented violation.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from grover_tax.paths import repo_root

BIN = repo_root() / "bin"
RUN_SP1 = BIN / "run_sp1.sh"
RUN_STWO = BIN / "run_stwo.sh"
VERIFY_SP1 = BIN / "verify_sp1.sh"
VERIFY_STWO = BIN / "verify_stwo.sh"
WRAPPER_LIB = repo_root() / "scripts" / "wrapper_lib.sh"

RUN_WRAPPERS = (RUN_SP1, RUN_STWO)
VERIFY_WRAPPERS = (VERIFY_SP1, VERIFY_STWO)
ALL_WRAPPERS = RUN_WRAPPERS + VERIFY_WRAPPERS


def _wrapper_text_with_lib(wrapper: Path) -> str:
    """Concatenate wrapper text with the sourced helper library — that's the
    real surface a precondition / grammar check is implemented on, since the
    library is `source`d into the wrapper at run time."""
    return wrapper.read_text(encoding="utf-8") + "\n" + WRAPPER_LIB.read_text(encoding="utf-8")


def _env_caps() -> dict[str, str]:
    return {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "",
        "RAYON_NUM_THREADS": "1",
        "TOKIO_WORKER_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }


# -- Structural symmetry checks (I-1) ------------------------------------------


@pytest.mark.parametrize("wrapper", ALL_WRAPPERS)
def test_set_euo_pipefail_at_top(wrapper: Path) -> None:
    """RFC-0007 §"Wrapper internals" — every wrapper sets the strict-shell flags."""
    text = wrapper.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text, f"{wrapper.name} missing `set -euo pipefail`"


@pytest.mark.parametrize("var", ["CUDA_VISIBLE_DEVICES", "RAYON_NUM_THREADS", "TOKIO_WORKER_THREADS", "OMP_NUM_THREADS"])
@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_run_wrapper_checks_env_var(wrapper: Path, var: str) -> None:
    """Both `run` wrappers must check each of the four required env caps."""
    text = wrapper.read_text(encoding="utf-8")
    assert var in text, f"{wrapper.name} does not reference {var}"


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_run_wrapper_checks_affinity(wrapper: Path) -> None:
    """Both `run` wrappers (via the sourced lib) handle both `taskpolicy` and `taskset`."""
    text = _wrapper_text_with_lib(wrapper)
    assert "taskpolicy" in text
    assert "taskset" in text


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_run_wrapper_writes_proof_atomically(wrapper: Path) -> None:
    """Match the temp-then-rename pattern: `.partial.$$` + `mv -- "${TMP_PROOF}"`."""
    text = wrapper.read_text(encoding="utf-8")
    assert re.search(r"\.partial\.\$\$", text), f"{wrapper.name} missing temp-suffix pattern"
    assert re.search(r'mv -- "\$\{TMP_PROOF\}"', text), \
        f"{wrapper.name} missing atomic mv"


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_run_wrapper_enforces_grammar(wrapper: Path) -> None:
    """Both `run` wrappers (via the sourced lib) check `CONSTRAINTS:` and `TRACE_ROWS:`."""
    text = _wrapper_text_with_lib(wrapper)
    assert "CONSTRAINTS:" in text
    assert "TRACE_ROWS:" in text
    assert "PROVER.STDOUT_GRAMMAR_VIOLATION" in text


@pytest.mark.parametrize("wrapper", VERIFY_WRAPPERS)
def test_verify_wrapper_sources_fixture_from_cwd(wrapper: Path) -> None:
    """Both `verify` wrappers read `fixtures/v0.1.json` from the cwd."""
    text = wrapper.read_text(encoding="utf-8")
    assert "fixtures/v0.1.json" in text


# -- Behavioural symmetry: invoking with no args exits 2 (I-1 step 1) ----------


@pytest.mark.parametrize("wrapper", ALL_WRAPPERS)
def test_wrapper_with_no_args_exits_2(wrapper: Path) -> None:
    """Per RFC-0007 §"Preconditions" step 1, wrong argv shape exits 2."""
    result = subprocess.run(
        ["bash", str(wrapper)],
        env=_env_caps(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, f"{wrapper.name} returned {result.returncode}"
    assert "MEASUREMENT.ENV_VAR_MISS" in result.stderr


# -- Exit-code matrix (W-T2..W-T5) ---------------------------------------------


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
@pytest.mark.parametrize("missing_var", ["CUDA_VISIBLE_DEVICES", "RAYON_NUM_THREADS", "TOKIO_WORKER_THREADS", "OMP_NUM_THREADS"])
def test_exit_2_on_missing_env(wrapper: Path, missing_var: str, tmp_path: Path) -> None:
    """W-T2: each of the four env caps, when missing, fails with exit 2."""
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_caps()
    env.pop(missing_var, None)
    result = subprocess.run(
        ["bash", str(wrapper), str(fixture), str(tmp_path / "proof.bin")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert missing_var in result.stderr


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_exit_3_on_missing_prover_binary(wrapper: Path, tmp_path: Path) -> None:
    """W-T2: missing prover binary → exit 3 (BUILD.* subcode)."""
    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_caps()
    # Both override env vars must point to a missing binary.
    env["SP1_BINARY"] = str(tmp_path / "no-such-sp1")
    env["STWO_BINARY"] = str(tmp_path / "no-such-stwo")
    result = subprocess.run(
        ["bash", str(wrapper), str(fixture), str(tmp_path / "proof.bin")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert "BUILD." in result.stderr


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_grammar_violation_exits_1(wrapper: Path, tmp_path: Path) -> None:
    """W-T5: a stub prover that emits no CONSTRAINTS / TRACE_ROWS lines
    triggers `PROVER.STDOUT_GRAMMAR_VIOLATION` (exit 1)."""
    # Build a stub binary that emits no grammar lines, succeeds, and writes
    # a non-empty proof file.
    stub = tmp_path / "stub_prover.sh"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
# Parse --fixtures and --output (wrapper invokes us with these).
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixtures) shift 2 ;;
    --output)   OUT="$2"; shift 2 ;;
    *)          shift ;;
  esac
done
echo "stub prover: no grammar lines emitted"
printf 'stub-proof-bytes' >"${OUT}"
exit 0
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_caps()
    env["SP1_BINARY"] = str(stub)
    env["STWO_BINARY"] = str(stub)
    result = subprocess.run(
        ["bash", str(wrapper), str(fixture), str(tmp_path / "proof.bin")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "PROVER.STDOUT_GRAMMAR_VIOLATION" in result.stderr
    # No partial proof file should be left behind (atomicity).
    assert not (tmp_path / "proof.bin").exists()


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_happy_path_with_compliant_stub(wrapper: Path, tmp_path: Path) -> None:
    """W-T5 + W-T3 happy path: a stub that emits the grammar lines and writes
    a proof produces exit 0 and the final proof file lands at `<output>`."""
    stub = tmp_path / "stub_prover.sh"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixtures) shift 2 ;;
    --output)   OUT="$2"; shift 2 ;;
    *)          shift ;;
  esac
done
echo "CONSTRAINTS: 1234"
printf 'TRACE_ROWS: 5678\\n'
printf 'stub-proof-bytes' >"${OUT}"
exit 0
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    proof_path = tmp_path / "proof.bin"
    env = _env_caps()
    env["SP1_BINARY"] = str(stub)
    env["STWO_BINARY"] = str(stub)
    result = subprocess.run(
        ["bash", str(wrapper), str(fixture), str(proof_path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert proof_path.read_bytes() == b"stub-proof-bytes"
    # No `.partial` temp file left behind.
    leftovers = [p.name for p in tmp_path.iterdir() if ".partial." in p.name]
    assert leftovers == []


@pytest.mark.parametrize("wrapper", RUN_WRAPPERS)
def test_prover_failure_exits_1(wrapper: Path, tmp_path: Path) -> None:
    """A stub that emits the grammar lines but exits non-zero → exit 1."""
    stub = tmp_path / "stub_prover.sh"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fixtures) shift 2 ;;
    --output)   OUT="$2"; shift 2 ;;
    *)          shift ;;
  esac
done
echo "CONSTRAINTS: 1234"
echo "TRACE_ROWS:  5678"
# Write a non-empty proof so the empty-proof check doesn't shadow our exit.
printf 'stub' >"${OUT}"
exit 7
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    fixture = tmp_path / "fix.json"
    fixture.write_text("{}", encoding="utf-8")
    env = _env_caps()
    env["SP1_BINARY"] = str(stub)
    env["STWO_BINARY"] = str(stub)
    result = subprocess.run(
        ["bash", str(wrapper), str(fixture), str(tmp_path / "proof.bin")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "PROVER.WITNESS_REJECTED" in result.stderr


# -- Verifier exit-code matrix (W-T4) ------------------------------------------


@pytest.mark.parametrize("wrapper", VERIFY_WRAPPERS)
def test_verify_stdout_empty_on_success(wrapper: Path, tmp_path: Path) -> None:
    """W-T4: verifier success path produces empty stdout."""
    stub = tmp_path / "stub_verifier.sh"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
# Successful verification — wrapper redirects our stdout to /dev/null already
# but we must still exit 0.
exit 0
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    # Set up the cwd structure the verifier requires.
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "v0.1.json").write_text("{}", encoding="utf-8")
    proof = tmp_path / "proof.bin"
    proof.write_bytes(b"\x00" * 16)

    env = _env_caps()
    env["SP1_VERIFIER"] = str(stub)
    env["STWO_VERIFIER"] = str(stub)
    result = subprocess.run(
        ["bash", str(wrapper), str(proof)],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("wrapper", VERIFY_WRAPPERS)
def test_verify_stderr_nonempty_on_failure(wrapper: Path, tmp_path: Path) -> None:
    """W-T4: verifier failure path produces a stderr diagnostic."""
    stub = tmp_path / "stub_verifier.sh"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "verifier internal diagnostic: invalid proof" >&2
exit 1
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "v0.1.json").write_text("{}", encoding="utf-8")
    proof = tmp_path / "proof.bin"
    proof.write_bytes(b"\x00" * 16)

    env = _env_caps()
    env["SP1_VERIFIER"] = str(stub)
    env["STWO_VERIFIER"] = str(stub)
    result = subprocess.run(
        ["bash", str(wrapper), str(proof)],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "PROVER.VERIFIER_REJECTED" in result.stderr


# -- Cross-wrapper equality of the env-var assertions --------------------------


def _required_env_lines(wrapper: Path) -> set[str]:
    """Extract lines that look like `require_env <VAR> <VALUE>` from a wrapper."""
    out: set[str] = set()
    for line in wrapper.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("require_env "):
            out.add(stripped)
    return out


def test_run_wrappers_have_identical_require_env_lines() -> None:
    """SP1 and Stwo `run` wrappers issue the same `require_env` calls — this is
    the load-bearing symmetry guarantee for the measurement script."""
    sp1_lines = _required_env_lines(RUN_SP1)
    stwo_lines = _required_env_lines(RUN_STWO)
    assert sp1_lines == stwo_lines, (
        f"run_sp1 require_env: {sp1_lines}; run_stwo require_env: {stwo_lines}"
    )
