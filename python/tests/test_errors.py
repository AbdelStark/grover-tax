"""Unit tests for `grover_tax.errors`."""

from __future__ import annotations

import pytest

from grover_tax.errors import (
    BUILD_EXIT_CODE,
    FIXTURE_EXIT_CODE,
    MEASUREMENT_SERIES_EXIT_CODE,
    MEASUREMENT_WRAPPER_EXIT_CODE,
    PROVER_EXIT_CODE,
    REPORT_EXIT_CODE,
    BuildError,
    BuildSubcode,
    FixtureError,
    FixtureSubcode,
    GroverTaxError,
    MeasurementError,
    MeasurementSubcode,
    ProverError,
    ProverSubcode,
    ReportError,
    ReportSubcode,
)


def test_exit_codes_match_error_model() -> None:
    """Per `docs/spec/04-error-model.md`, exit codes are stable."""
    assert BUILD_EXIT_CODE == 3
    assert FIXTURE_EXIT_CODE == 4
    assert PROVER_EXIT_CODE == 1
    assert MEASUREMENT_WRAPPER_EXIT_CODE == 2
    assert MEASUREMENT_SERIES_EXIT_CODE == 5
    assert REPORT_EXIT_CODE == 6


def test_subcode_enum_values_are_stable_strings() -> None:
    """Subcodes are stable identifiers — never change their string form."""
    assert BuildSubcode.RUSTC_MISMATCH.value == "BUILD.RUSTC_MISMATCH"
    assert FixtureSubcode.WORKLOAD_NOT_PINNED.value == "FIXTURE.WORKLOAD_NOT_PINNED"
    assert ProverSubcode.WITNESS_REJECTED.value == "PROVER.WITNESS_REJECTED"
    assert MeasurementSubcode.GPU_RESIDENT.value == "MEASUREMENT.GPU_RESIDENT"
    assert ReportSubcode.INSUFFICIENT_SAMPLES.value == "REPORT.INSUFFICIENT_SAMPLES"


def test_grover_tax_error_render_with_message() -> None:
    err = FixtureError(FixtureSubcode.WORKLOAD_NOT_PINNED, "WORKLOAD.md still contains TBD")
    assert str(err) == "FIXTURE.WORKLOAD_NOT_PINNED: WORKLOAD.md still contains TBD"
    assert err.subcode == "FIXTURE.WORKLOAD_NOT_PINNED"
    assert err.message == "WORKLOAD.md still contains TBD"
    assert err.exit_code == FIXTURE_EXIT_CODE


def test_grover_tax_error_render_without_message() -> None:
    err = ProverError(ProverSubcode.OOM)
    assert str(err) == "PROVER.OOM"
    assert err.message == ""


def test_each_error_subclass_binds_to_expected_exit_code() -> None:
    assert BuildError(BuildSubcode.CARGO_FAIL).exit_code == BUILD_EXIT_CODE
    assert FixtureError(FixtureSubcode.SCHEMA_INVALID).exit_code == FIXTURE_EXIT_CODE
    assert ProverError(ProverSubcode.TIMEOUT).exit_code == PROVER_EXIT_CODE
    assert MeasurementError(MeasurementSubcode.SWAP_ACTIVE).exit_code == MEASUREMENT_WRAPPER_EXIT_CODE
    assert ReportError(ReportSubcode.MISSING_ARTIFACT).exit_code == REPORT_EXIT_CODE


def test_measurement_error_series_level_promotes_exit_code() -> None:
    series = MeasurementError(MeasurementSubcode.VERSIONS_DRIFT, "drift", series_level=True)
    assert series.exit_code == MEASUREMENT_SERIES_EXIT_CODE
    # Per-instance promotion does not leak to the class default.
    assert MeasurementError.exit_code == MEASUREMENT_WRAPPER_EXIT_CODE


def test_errors_accept_raw_string_subcode() -> None:
    """Callers may pass the literal subcode string (useful for cross-language echoes)."""
    err = FixtureError("FIXTURE.WORKLOAD_NOT_PINNED", "raw")
    assert err.subcode == "FIXTURE.WORKLOAD_NOT_PINNED"
    assert err.exit_code == FIXTURE_EXIT_CODE


@pytest.mark.parametrize(
    ("cls", "subcode"),
    [
        (BuildError, BuildSubcode.UV_SYNC_FAIL),
        (FixtureError, FixtureSubcode.SEED_DRIFT),
        (ProverError, ProverSubcode.STDOUT_GRAMMAR_VIOLATION),
        (MeasurementError, MeasurementSubcode.GOVERNOR_MISS),
        (ReportError, ReportSubcode.STABILITY_BREACH),
    ],
)
def test_all_subclasses_inherit_from_grover_tax_error(cls: type, subcode: object) -> None:
    err = cls(subcode)
    assert isinstance(err, GroverTaxError)
    assert isinstance(err, Exception)


@pytest.mark.parametrize(
    "subcode",
    [
        BuildSubcode.SP1_PATCH_FAIL,
        BuildSubcode.STWO_SHA_DRIFT,
        BuildSubcode.LICENSE_CHECK_FAIL,
        FixtureSubcode.CROSS_VALIDATION_FAIL,
        FixtureSubcode.COMMITMENT_MISMATCH,
        FixtureSubcode.DRIFT,
        ProverSubcode.VERIFIER_REJECTED,
        MeasurementSubcode.ENV_VAR_MISS,
        MeasurementSubcode.AFFINITY_MISS,
        MeasurementSubcode.THERMAL_EXCEEDED,
        MeasurementSubcode.AC_POWER_MISS,
        MeasurementSubcode.LOWPOWER_ENABLED,
        ReportSubcode.SCHEMA_INVALID,
    ],
)
def test_every_subcode_resolves_to_string(subcode: object) -> None:
    """Smoke-test that every documented subcode is reachable via its enum."""
    assert "." in getattr(subcode, "value")
