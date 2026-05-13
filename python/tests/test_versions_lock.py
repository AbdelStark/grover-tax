"""Tests for the versions.lock schema + `scripts/lock_versions.sh`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from grover_tax.paths import repo_root

SCHEMA_PATH = repo_root() / "docs" / "spec" / "schemas" / "versions-lock-v1.schema.json"
LOCK_VERSIONS_SH = repo_root() / "scripts" / "lock_versions.sh"


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_schema_is_draft_2020_12_conformant() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def _example_lock() -> dict[str, object]:
    """A coherent, schema-valid object matching the spec's example shape."""
    return {
        "schema_version": 1,
        "generated_at": "2026-05-13T14:32:01Z",
        "generator_commit": "0" * 40,
        "rustc": {
            "version": "1.83.0",
            "commit_hash": "abc123",
            "host": "aarch64-apple-darwin",
        },
        "cargo": {"version": "1.83.0"},
        "sp1": {"version": "1.0.0", "sp1up_toolchain": "stable"},
        "stwo": {
            "commit": "1" * 40,
            "remote": "https://github.com/starkware-libs/stwo",
        },
        "cairo": {"version": "2.6.0"},
        "uv": {"version": "0.9.18", "sha256": "a" * 64},
        "python": {"version": "3.13.11"},
        "hyperfine": {"version": "1.18.0"},
        "gnu_time": {"version": "1.9", "binary": "/opt/homebrew/bin/gtime"},
        "host": {
            "platform": "darwin",
            "arch": "aarch64",
            "model": "Mac16,5",
            "cpu_brand": "Apple M4 Max",
            "cores_total": 16,
            "ram_gb": 48,
            "kernel": "25.2.0",
        },
    }


def test_canonical_example_validates() -> None:
    _validator().validate(_example_lock())


def test_unknown_stwo_commit_accepted() -> None:
    """The 'unknown' sentinel for stwo.commit is intentional while #5 is open."""
    obj = _example_lock()
    obj["stwo"]["commit"] = "unknown"  # type: ignore[index]
    _validator().validate(obj)


def test_schema_version_must_be_one() -> None:
    obj = _example_lock()
    obj["schema_version"] = 2
    errors = list(_validator().iter_errors(obj))
    assert any(e.validator == "const" for e in errors)


def test_missing_rustc_field_rejected() -> None:
    obj = _example_lock()
    del obj["rustc"]
    errors = list(_validator().iter_errors(obj))
    assert any("rustc" in e.message for e in errors)


def test_unknown_platform_rejected() -> None:
    obj = _example_lock()
    obj["host"]["platform"] = "windows"  # type: ignore[index]
    errors = list(_validator().iter_errors(obj))
    assert any(e.validator == "enum" for e in errors)


def test_short_uv_sha256_rejected() -> None:
    obj = _example_lock()
    obj["uv"]["sha256"] = "abc"  # type: ignore[index]
    errors = list(_validator().iter_errors(obj))
    assert any("sha256" in (str(p) for p in e.absolute_path) for e in errors)


def test_python_version_must_be_312_or_313() -> None:
    obj = _example_lock()
    obj["python"]["version"] = "3.11.5"  # type: ignore[index]
    errors = list(_validator().iter_errors(obj))
    assert any("version" in (str(p) for p in e.absolute_path) for e in errors)


# -- lock_versions.sh -----------------------------------------------------------


def _run_dry() -> str:
    """Run the script in DRY=1 mode; return stdout as text."""
    result = subprocess.run(
        ["bash", str(LOCK_VERSIONS_SH)],
        env={"PATH": __import__("os").environ["PATH"], "DRY": "1", "HOME": str(Path.home())},
        check=True,
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    return result.stdout


def test_lock_versions_sh_runs_to_completion() -> None:
    """Acceptance bullet: script runs end-to-end."""
    out = _run_dry()
    assert out.strip(), "DRY=1 produced empty output"
    json.loads(out)  # raises if not valid JSON


def test_lock_versions_sh_dry_does_not_overwrite_disk_artifact(tmp_path: Path) -> None:
    """DRY=1 prints to stdout; no `versions.lock` is written next to the repo."""
    out_path = repo_root() / "versions.lock"
    pre_existed = out_path.exists()
    pre_mtime = out_path.stat().st_mtime if pre_existed else None
    _run_dry()
    if pre_existed:
        assert out_path.stat().st_mtime == pre_mtime
    else:
        assert not out_path.exists(), "DRY=1 must not create versions.lock"


def test_lock_versions_sh_output_is_byte_stable_modulo_volatile_fields() -> None:
    """Acceptance bullet: two DRY=1 invocations are byte-stable modulo
    `generated_at` and `generator_commit`."""
    a = json.loads(_run_dry())
    b = json.loads(_run_dry())
    # Drop the two fields that legitimately change per invocation.
    a.pop("generated_at", None)
    a.pop("generator_commit", None)
    b.pop("generated_at", None)
    b.pop("generator_commit", None)
    assert a == b


def test_lock_versions_sh_output_has_sorted_keys() -> None:
    """Stable diffs require `jq --sort-keys` output. Confirm by re-emitting."""
    out = _run_dry()
    parsed = json.loads(out)
    # `json.dumps(..., sort_keys=True, indent=2)` of the parsed object must
    # match `out` modulo the trailing newline jq adds.
    re_emitted = json.dumps(parsed, sort_keys=True, indent=2)
    assert out.strip() == re_emitted.strip()


@pytest.mark.parametrize(
    "field_path",
    ["schema_version", "generated_at", "rustc", "uv", "host", "python"],
)
def test_lock_versions_sh_produces_required_field(field_path: str) -> None:
    """Every required top-level key surfaces in the live output."""
    out = json.loads(_run_dry())
    assert field_path in out, f"missing {field_path!r} from lock_versions.sh output"
