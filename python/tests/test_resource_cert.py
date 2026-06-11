"""Tests for `grover_tax.resource_cert` — resource certification (KB-10, #122)."""

from __future__ import annotations

from pathlib import Path

import pytest

from grover_tax.errors import PROVER_EXIT_CODE
from grover_tax.resource_cert import (
    SENTINEL,
    DemandedBounds,
    ResourceCounts,
    certify,
    count_kmx,
    main,
    public_outputs,
)

_IADD64 = (
    Path(__file__).resolve().parents[2]
    / "third_party"
    / "sp1"
    / "docs"
    / "example_data"
    / "iadd64.kmx"
)


def _counts(samples: int) -> ResourceCounts:
    return count_kmx(_IADD64.read_text(encoding="utf-8"), samples)


def _demanded() -> DemandedBounds:
    return DemandedBounds(
        num_samples=128,
        max_qubit_count=128,
        max_non_clifford_count=125,
        max_circuit_instructions=757,
    )


def test_count_kmx_matches_upstream_iadd64() -> None:
    """Kickmix instruction count incl. metadata = 757 (matches Rust + upstream)."""
    counts = _counts(128)
    assert counts.max_qubit_count == 128
    assert counts.max_non_clifford_count == 125
    assert counts.max_circuit_instructions == 757


def test_public_outputs_layout() -> None:
    assert public_outputs(_counts(128)) == (128, 128, 125, 757, SENTINEL)


def test_conforming_circuit_certifies() -> None:
    assert certify(_counts(128), SENTINEL, _demanded()) == []


def test_more_samples_than_demanded_certifies() -> None:
    assert certify(_counts(1000), SENTINEL, _demanded()) == []


def test_too_few_samples_rejected() -> None:
    violations = certify(_counts(64), SENTINEL, _demanded())
    assert any("too few samples" in v for v in violations)


@pytest.mark.parametrize(
    ("field", "bad", "needle"),
    [
        ("max_qubit_count", 64, "qubit cap"),
        ("max_non_clifford_count", 100, "non-Clifford cap"),
        ("max_circuit_instructions", 700, "instruction cap"),
    ],
)
def test_caps_exceeded_rejected(field: str, bad: int, needle: str) -> None:
    base = _demanded()
    demanded = DemandedBounds(**{**base.__dict__, field: bad})
    violations = certify(_counts(128), SENTINEL, demanded)
    assert any(needle in v for v in violations)


def test_bad_sentinel_rejected() -> None:
    violations = certify(_counts(128), 41, _demanded())
    assert any("bad sentinel" in v for v in violations)


# -- CLI ---------------------------------------------------------------------


def _cli_args(samples: int, q: int, nc: int, instr: int) -> list[str]:
    return [
        "--kmx",
        str(_IADD64),
        "--num-samples",
        str(samples),
        "--demand-samples",
        "128",
        "--demand-qubits",
        str(q),
        "--demand-non-clifford",
        str(nc),
        "--demand-instructions",
        str(instr),
    ]


def test_cli_accepts_conforming() -> None:
    assert main(_cli_args(128, 128, 125, 757)) == 0


def test_cli_rejects_over_cap() -> None:
    # qubit cap 64 < actual 128 -> rejected with PROVER.VERIFIER_REJECTED.
    assert main(_cli_args(128, 64, 125, 757)) == PROVER_EXIT_CODE


def test_cli_usage_error_without_bounds() -> None:
    assert main(["--kmx", str(_IADD64), "--num-samples", "128"]) == 2
