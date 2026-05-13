"""Smoke tests for `docs/spec/templates/RESULTS.md.j2`.

The full renderer + methodology lint live in `analyze.py` (#41) and
`check_results_md.py` (#44). These tests cover only the template-as-content
contract from issue #40:

* The template parses as Jinja2.
* It renders against a synthetic context (no missing variables, no
  TemplateError).
* Every section header listed in RFC-0011's methodology lint is present.
* Every required phrase from RFC-0011's methodology lint is present.
"""

from __future__ import annotations

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from grover_tax.paths import repo_root

TEMPLATE_DIR = repo_root() / "docs" / "spec" / "templates"
TEMPLATE_NAME = "RESULTS.md.j2"


# Per RFC-0011 §"Methodology lints (CI)".
REQUIRED_SECTIONS = [
    "## Headline",
    "## Distributions",
    "## Stability",
    "## Apples-to-apples disclosures",
    "## Discards",
    "## Reproduction",
    "## Run metadata",
    "## Underlying numbers",
]

REQUIRED_PHRASES = [
    "SHA-256",
    "Blake2s",
    "BabyBear",
    "M31",
    "Trusted setup",
    "taskpolicy",
    "RAYON_NUM_THREADS",
]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def _synthetic_context() -> dict[str, object]:
    """One coherent set of values for every placeholder used by the template."""
    return {
        "project_version": "v0.1.0",
        "generated_at": "2026-05-13T14:35:12Z",
        "headline_status": "",
        "n_sp1": 10,
        "n_stwo": 10,
        "m1_unit": "s",
        "m1_sp1_median": 100.0,
        "m1_stwo_median": 50.0,
        "ratio_m1": 2.00,
        "m1_sp1_iqr": 1.2,
        "m1_stwo_iqr": 0.8,
        "m1_sp1_min": 99.0,
        "m1_sp1_max": 102.0,
        "m1_stwo_min": 49.5,
        "m1_stwo_max": 51.2,
        "n_verify_sp1": 10,
        "n_verify_stwo": 10,
        "m5_unit": "ms",
        "m5_sp1_median": 30.0,
        "m5_stwo_median": 40.0,
        "ratio_m5": 0.75,
        "m2_sp1": 8192.0,
        "m2_stwo": 1024.0,
        "ratio_m2": 8.0,
        "m6_sp1": 192,
        "m6_stwo": 1024,
        "ratio_m6": 0.19,
        "m7_sp1": "1.0M constraints",
        "m7_stwo": "300K constraints",
        "m8_sp1": 60.0,
        "m9_sp1": 1024.0,
        "day1_median_sp1": 100.0,
        "day1_median_stwo": 50.0,
        "day2_median_sp1": 101.0,
        "day2_median_stwo": 51.0,
        "day1_day2_delta_sp1": 1.0,
        "day1_day2_delta_stwo": 2.0,
        "stability_breach": False,
        "stability_breach_explanation": "",
        "groth16_ceremony_origin": "upstream-trusted-setup-v0.x",
        "affinity_macos_or_linux": "taskpolicy -c utility",
        "user_wall_sp1": 1.0,
        "user_wall_stwo": 1.0,
        "residual_concurrency": False,
        "residual_concurrency_note": "",
        "d_cold_sp1": 1,
        "d_cold_stwo": 1,
        "d_thermal_sp1": 0,
        "d_thermal_stwo": 0,
        "d_gpu_sp1": 0,
        "d_gpu_stwo": 0,
        "d_swap_sp1": 0,
        "d_swap_stwo": 0,
        "d_env_sp1": 0,
        "d_env_stwo": 0,
        "d_other_sp1": 0,
        "d_other_stwo": 0,
        "discard_pct_sp1": 10.0,
        "discard_pct_stwo": 10.0,
        "workload_pin_commit": "0" * 40,
        "fixture_sha256": "1" * 64,
        "versions_lock_sha256": "2" * 64,
        "host_summary": "Apple M4 Max, 48 GB RAM, macOS 26.2",
        "day1_date": "2026-05-13",
        "day2_date": "2026-05-14",
        "spec_version": "v0.1",
        "analyze_commit": "abc" * 13 + "d",  # 40-char placeholder
    }


def test_template_file_exists() -> None:
    assert (TEMPLATE_DIR / TEMPLATE_NAME).is_file()


def test_template_parses_as_jinja2() -> None:
    """No syntax errors; loader can compile the template."""
    _env().get_template(TEMPLATE_NAME)


def test_template_renders_against_synthetic_context() -> None:
    """All placeholders resolve under StrictUndefined; no TemplateError."""
    rendered = _env().get_template(TEMPLATE_NAME).render(**_synthetic_context())
    assert isinstance(rendered, str)
    assert rendered.strip()  # not empty


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_template_contains_required_section(section: str) -> None:
    """RFC-0011's methodology lint requires these section headers."""
    rendered = _env().get_template(TEMPLATE_NAME).render(**_synthetic_context())
    assert section in rendered, f"missing required section header: {section!r}"


@pytest.mark.parametrize("phrase", REQUIRED_PHRASES)
def test_template_contains_required_phrase(phrase: str) -> None:
    """RFC-0011's methodology lint requires these disclosure phrases."""
    rendered = _env().get_template(TEMPLATE_NAME).render(**_synthetic_context())
    assert phrase in rendered, f"missing required disclosure phrase: {phrase!r}"


def test_stability_breach_branch_renders() -> None:
    """The `{% if stability_breach %}` branch is reachable."""
    ctx = _synthetic_context()
    ctx["stability_breach"] = True
    ctx["stability_breach_explanation"] = "P-core T exceeded budget on day 2"
    rendered = _env().get_template(TEMPLATE_NAME).render(**ctx)
    assert "Stability breach" in rendered
    assert "P-core T exceeded budget on day 2" in rendered


def test_residual_concurrency_branch_renders() -> None:
    ctx = _synthetic_context()
    ctx["residual_concurrency"] = True
    ctx["residual_concurrency_note"] = "user-CPU 1.4x on SP1"
    rendered = _env().get_template(TEMPLATE_NAME).render(**ctx)
    assert "residual concurrency" in rendered
    assert "user-CPU 1.4x on SP1" in rendered


def test_ratio_convention_is_sp1_over_stwo() -> None:
    """RFC-0011's ratio convention: SP1 / Stwo, reported as-is."""
    ctx = _synthetic_context()
    # ratio_m1 is the renderer's concern (#41); here we just verify the
    # template surfaces it where RFC-0011 says it should.
    ctx["ratio_m1"] = 0.50
    rendered = _env().get_template(TEMPLATE_NAME).render(**ctx)
    # The ratio appears in the "Ratio (SP1 / Stwo)" column header *and* in
    # the data cell; the value is reported as-is even when < 1.
    assert "Ratio (SP1 / Stwo)" in rendered
    assert "0.5×" in rendered  # noqa: RUF001 - multiplication sign is the spec literal
