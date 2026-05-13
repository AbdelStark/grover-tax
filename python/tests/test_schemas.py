"""Schema-validation tests for the three persisted-artifact schemas.

Each schema is exercised against:
  * one canonical good document (`python/tests/fixtures/good/*.json`),
  * the 20 hand-crafted bad fixtures under `python/tests/fixtures/bad/`
    (fixture schema only; the other two have negative cases inline).

The 20 bad fixtures are the spec-required suite from issue #14: each one
mutates exactly one cell of the canonical good fixture, in a different way,
so that the path to the failure points at a single schema rule. The tests
load each one, validate against the schema, and assert that the path /
validator-name produced by `jsonschema` matches the documented expectation.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from grover_tax.paths import repo_root

SCHEMAS_DIR = repo_root() / "docs" / "spec" / "schemas"
FIXTURE_SCHEMA = SCHEMAS_DIR / "fixture-v0.1.schema.json"
SETUP_SCHEMA = SCHEMAS_DIR / "setup-v1.schema.json"
DISCARDS_SCHEMA = SCHEMAS_DIR / "discards-v1.schema.json"

GOOD_DIR = Path(__file__).parent / "fixtures" / "good"
BAD_DIR = Path(__file__).parent / "fixtures" / "bad"


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _has_matching_error(errors: list[jsonschema.ValidationError], expected: str) -> bool:
    """Check that at least one of `errors` matches `expected`.

    `expected` syntax:
      * ``"validator:<name>"``  — matches when ``err.validator == name``.
      * ``"required:<field>"``  — matches when the validator is ``required``
        and the error message names that field.
      * any other string        — matches when the substring appears in the
        json-path *or* in the error message (which is where the missing-key
        field name lives for `required` violations).
    """
    for err in errors:
        path_str = "/".join(str(p) for p in err.absolute_path)
        if expected.startswith("validator:"):
            if err.validator == expected.split(":", 1)[1]:
                return True
        elif expected.startswith("required:"):
            field = expected.split(":", 1)[1]
            if err.validator == "required" and field in err.message:
                return True
        elif expected in path_str or expected in err.message:
            return True
    return False


# Each entry: (bad-fixture filename, expected_path_segment_or_validator).
# The second element is a substring that *must* appear in the failure's path or
# validator name, so the test asserts the right rule fired — not just "some
# rule failed". `validator:<name>` matches a top-level rule (e.g. `required`,
# `additionalProperties`); a bare string matches inside the json-path.
BAD_FIXTURE_EXPECTATIONS: list[tuple[str, str]] = [
    ("01_missing_version.json", "validator:required"),
    ("02_wrong_version.json", "version"),
    ("03_missing_generator_commit.json", "validator:required"),
    ("04_short_generator_commit.json", "generator_commit"),
    ("05_uppercase_workload_commit.json", "workload_pin_commit"),
    ("06_missing_seed_hex.json", "validator:required"),
    ("07_short_seed_hex.json", "seed_hex"),
    ("08_seed_hex_with_uppercase.json", "seed_hex"),
    ("09_n_samples_zero.json", "n_samples"),
    ("10_n_samples_float.json", "n_samples"),
    ("11_bit_stripe_width_zero.json", "bit_stripe_width"),
    ("12_wrong_format_version.json", "circuit_serialisation_format_version"),
    ("13_odd_byte_serialisation.json", "circuit_byte_serialisation_hex"),
    ("14_uppercase_sha256_commit.json", "circuit_commitment_sha256_hex"),
    ("15_short_blake2s_commit.json", "circuit_commitment_blake2s_hex"),
    ("16_missing_test_cases.json", "validator:required"),
    ("17_empty_test_cases.json", "test_cases"),
    ("18_short_x_hex.json", "x_hex"),
    ("19_short_y_hex.json", "y_hex"),
    ("20_extra_top_level_field.json", "validator:additionalProperties"),
]


def test_fixture_schema_is_draft_2020_12_conformant() -> None:
    schema = _load_schema(FIXTURE_SCHEMA)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_setup_schema_is_draft_2020_12_conformant() -> None:
    schema = _load_schema(SETUP_SCHEMA)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_discards_schema_is_draft_2020_12_conformant() -> None:
    schema = _load_schema(DISCARDS_SCHEMA)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_canonical_good_fixture_validates() -> None:
    schema = _load_schema(FIXTURE_SCHEMA)
    fixture = _load_json(GOOD_DIR / "fixture_canonical.json")
    Draft202012Validator(schema).validate(fixture)


def test_bad_fixtures_directory_has_exactly_twenty_files() -> None:
    """RFC-0011 §"fixture: schemas" requires 20 hand-crafted bad fixtures."""
    bad_files = sorted(BAD_DIR.glob("*.json"))
    assert len(bad_files) == 20, f"expected 20 bad fixtures, got {len(bad_files)}"


@pytest.mark.parametrize(("filename", "expected"), BAD_FIXTURE_EXPECTATIONS)
def test_bad_fixture_fails_with_expected_path(filename: str, expected: str) -> None:
    schema = _load_schema(FIXTURE_SCHEMA)
    validator = Draft202012Validator(schema)
    fixture = _load_json(BAD_DIR / filename)
    errors = list(validator.iter_errors(fixture))
    assert errors, f"{filename}: schema unexpectedly accepted invalid fixture"
    assert _has_matching_error(errors, expected), (
        f"{filename}: no error matched expected `{expected}`. "
        f"Errors: {[(e.validator, list(e.absolute_path), e.message) for e in errors]}"
    )


def test_canonical_setup_record_validates() -> None:
    schema = _load_schema(SETUP_SCHEMA)
    record = {
        "schema_version": 1,
        "run_id": "1715610912-abcd123",
        "wall_clock_s": 42.5,
        "user_cpu_s": 40.2,
        "sys_cpu_s": 2.0,
        "peak_rss_mib": 1024.0,
        "proving_key_bytes": 1_073_741_824,
        "verifying_key_bytes": 192,
        "groth16_ceremony_origin": "upstream-trusted-setup-v0.x",
    }
    Draft202012Validator(schema).validate(record)


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        ("schema_version_wrong", "schema_version"),
        ("missing_run_id", "required:run_id"),
        ("negative_wall_clock", "wall_clock_s"),
        ("empty_origin", "groth16_ceremony_origin"),
        ("float_proving_key_bytes", "proving_key_bytes"),
        ("extra_field", "validator:additionalProperties"),
    ],
)
def test_bad_setup_records(mutation: str, expected_path: str) -> None:
    schema = _load_schema(SETUP_SCHEMA)
    record = {
        "schema_version": 1,
        "run_id": "r",
        "wall_clock_s": 1.0,
        "user_cpu_s": 1.0,
        "sys_cpu_s": 0.5,
        "peak_rss_mib": 256.0,
        "proving_key_bytes": 1,
        "verifying_key_bytes": 1,
        "groth16_ceremony_origin": "ok",
    }
    if mutation == "schema_version_wrong":
        record["schema_version"] = 2
    elif mutation == "missing_run_id":
        del record["run_id"]
    elif mutation == "negative_wall_clock":
        record["wall_clock_s"] = -1.0
    elif mutation == "empty_origin":
        record["groth16_ceremony_origin"] = ""
    elif mutation == "float_proving_key_bytes":
        record["proving_key_bytes"] = 1.5
    elif mutation == "extra_field":
        record["extra"] = "rejected"

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(record))
    assert errors, f"setup mutation {mutation!r}: schema unexpectedly accepted"
    assert _has_matching_error(errors, expected_path), (
        f"{mutation}: no error matched `{expected_path}`. Errors: {errors}"
    )


def test_canonical_discards_record_validates() -> None:
    schema = _load_schema(DISCARDS_SCHEMA)
    record = {
        "ts": "2026-05-13T14:35:12Z",
        "run_id": "1715610912-abcd123",
        "prover": "sp1",
        "reason": "thermal",
        "detail": "P-core T = 97C, above 95C threshold",
        "measurement_artifact": "results/sp1_v0.1_1715610912-abcd123.timing.json",
    }
    Draft202012Validator(schema).validate(record)


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        ("missing_ts", "required:ts"),
        ("bad_prover_enum", "prover"),
        ("bad_reason_enum", "reason"),
        ("empty_measurement_artifact", "measurement_artifact"),
        ("extra_field", "validator:additionalProperties"),
    ],
)
def test_bad_discards_records(mutation: str, expected_path: str) -> None:
    schema = _load_schema(DISCARDS_SCHEMA)
    record = {
        "ts": "2026-05-13T14:35:12Z",
        "run_id": "r",
        "prover": "sp1",
        "reason": "thermal",
        "detail": "d",
        "measurement_artifact": "results/x.json",
    }
    if mutation == "missing_ts":
        del record["ts"]
    elif mutation == "bad_prover_enum":
        record["prover"] = "groth16"
    elif mutation == "bad_reason_enum":
        record["reason"] = "tired"
    elif mutation == "empty_measurement_artifact":
        record["measurement_artifact"] = ""
    elif mutation == "extra_field":
        record["surprise"] = "rejected"

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(record))
    assert errors, f"discards mutation {mutation!r}: schema unexpectedly accepted"
    assert _has_matching_error(errors, expected_path), (
        f"{mutation}: no error matched `{expected_path}`. Errors: {errors}"
    )


def test_schema_id_uses_github_raw_url() -> None:
    """Per the issue note: `$id` should be the GitHub raw-URL form."""
    for path in (FIXTURE_SCHEMA, SETUP_SCHEMA, DISCARDS_SCHEMA):
        schema = _load_schema(path)
        assert schema["$id"].startswith("https://raw.githubusercontent.com/AbdelStark/grover-tax/")


def test_jsonschema_is_importable() -> None:
    """Smoke-test that `jsonschema` is on the install path (acceptance bullet)."""
    assert hasattr(jsonschema, "Draft202012Validator")
