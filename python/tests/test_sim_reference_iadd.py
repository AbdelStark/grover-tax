"""Cross-validation of the adopted canonical iadd workload (KB-2, #114).

These tests exercise `grover_tax.sim_reference`'s v0.3-iadd dispatch — the
F-INV-4 oracle for the adder — and assert the v0.2 random-circuit path is
retained for regression (T0 continuity).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grover_tax.errors import FixtureError, FixtureSubcode
from grover_tax.iadd_fixture import build_iadd_fixture
from grover_tax.sim_reference import _verify_fixture, main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED = _REPO_ROOT / "fixtures" / "v0.3-iadd-T0.json"


def _write(fixture: dict, path: Path) -> None:
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")


def test_committed_iadd_fixture_cross_validates() -> None:
    """The canonical fixtures/v0.3-iadd-T0.json passes the reference oracle."""
    _verify_fixture(_COMMITTED)  # raises on any mismatch


def test_sim_check_cli_accepts_iadd_fixture() -> None:
    assert main(["--fixture", str(_COMMITTED)]) == 0


@pytest.mark.parametrize("k", [1, 2, 4])
def test_repeated_iadd_cross_validates(tmp_path: Path, k: int) -> None:
    fixture = build_iadd_fixture(repetitions=k, n_samples=8, tier=f"T{k}")
    p = tmp_path / f"v0.3-iadd-T{k}.json"
    _write(fixture, p)
    _verify_fixture(p)  # K-repeated circuit reproduces every y_state


def test_tampered_output_is_rejected(tmp_path: Path) -> None:
    fixture = build_iadd_fixture(repetitions=1, n_samples=4, tier="T0")
    # Corrupt one expected output state.
    yhex = fixture["test_cases"][0]["y_hex"]
    flipped = ("ff" if yhex[:2] != "ff" else "00") + yhex[2:]
    fixture["test_cases"][0]["y_hex"] = flipped
    p = tmp_path / "bad.json"
    _write(fixture, p)
    with pytest.raises(FixtureError) as exc:
        _verify_fixture(p)
    assert exc.value.subcode == FixtureSubcode.CROSS_VALIDATION_FAIL.value


def test_v02_random_path_still_supported() -> None:
    """Regression / T0 continuity: the v0.2 random-circuit fixture still verifies."""
    v02 = _REPO_ROOT / "fixtures" / "v0.2.json"
    if not v02.is_file():  # pragma: no cover - fixture is committed
        pytest.skip("v0.2 fixture not present")
    assert main(["--fixture", str(v02)]) == 0
