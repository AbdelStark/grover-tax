"""Tests for `grover_tax.check_results_md`.

This covers the lint script's behaviour. The wider R-T test suite (renderer
+ plot determinism + ratio convention) lives in `test_results_template.py`
and — once `analyze.py` lands (#41) — in `test_analyze.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from grover_tax.check_results_md import (
    REQUIRED_PHRASES,
    REQUIRED_SECTIONS,
    lint,
    main,
)
from grover_tax.errors import REPORT_EXIT_CODE
from grover_tax.paths import repo_root


def _render_results_md() -> str:
    """Render the canonical template against a coherent synthetic context."""
    env = Environment(
        loader=FileSystemLoader(str(repo_root() / "docs" / "spec" / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    ctx = {
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
        "analyze_commit": "a" * 40,
    }
    return env.get_template("RESULTS.md.j2").render(**ctx)


def test_required_lists_match_rfc_0011() -> None:
    """RFC-0011 says: 8 sections, 7 phrases. Lockstep with the lint."""
    assert len(REQUIRED_SECTIONS) == 8
    assert len(REQUIRED_PHRASES) == 7


def test_lint_passes_on_canonical_render() -> None:
    """A canonical-context render of the template has no missing substrings."""
    rendered = _render_results_md()
    assert lint(rendered) == []


@pytest.mark.parametrize("missing_section", REQUIRED_SECTIONS)
def test_lint_fails_when_section_removed(missing_section: str) -> None:
    """Acceptance bullet: lint flags every missing section."""
    rendered = _render_results_md()
    # Replace the section header with something that does NOT itself contain
    # the required substring. (`f"DROPPED {missing_section}"` would still
    # contain it; the empty-string drop avoids that aliasing.)
    tampered = rendered.replace(missing_section, "")
    missing = lint(tampered)
    assert missing_section in missing


@pytest.mark.parametrize("missing_phrase", REQUIRED_PHRASES)
def test_lint_fails_when_phrase_removed(missing_phrase: str) -> None:
    """Acceptance bullet: lint flags every missing phrase."""
    rendered = _render_results_md()
    # Same aliasing concern — replace with an unrelated marker.
    tampered = rendered.replace(missing_phrase, "REDACTED")
    missing = lint(tampered)
    assert missing_phrase in missing


def test_main_exits_zero_on_clean_file(tmp_path: Path) -> None:
    p = tmp_path / "RESULTS.md"
    p.write_text(_render_results_md(), encoding="utf-8")
    assert main([str(p)]) == 0


def test_main_exits_six_on_dirty_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance bullet: exit-code 6 + missing-substring report on stderr."""
    p = tmp_path / "RESULTS.md"
    rendered = _render_results_md()
    # Strip a section and a phrase.
    rendered = rendered.replace("## Headline", "<gone>")
    rendered = rendered.replace("SHA-256", "<gone>")
    p.write_text(rendered, encoding="utf-8")
    rc = main([str(p)])
    captured = capsys.readouterr()
    assert rc == REPORT_EXIT_CODE
    assert "REPORT.SCHEMA_INVALID" in captured.err
    assert "'## Headline'" in captured.err
    assert "'SHA-256'" in captured.err


def test_main_exits_six_on_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "no_such_file.md"
    rc = main([str(missing)])
    captured = capsys.readouterr()
    assert rc == REPORT_EXIT_CODE
    assert "REPORT.MISSING_ARTIFACT" in captured.err


def test_main_defaults_to_cwd_results_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default `path` resolves to `./RESULTS.md` in the caller's cwd."""
    (tmp_path / "RESULTS.md").write_text(_render_results_md(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
