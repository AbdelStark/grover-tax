"""Tests for `grover_tax.analyze` (#41)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from grover_tax.analyze import MIN_RUNS_M1, MIN_RUNS_M5, Stats, _stats, main
from grover_tax.errors import REPORT_EXIT_CODE
from grover_tax.paths import repo_root


def _write_hyperfine_json(path: Path, times: list[float]) -> None:
    path.write_text(
        json.dumps({"results": [{"command": "x", "times": times}]}),
        encoding="utf-8",
    )


def test_stats_on_empty_samples_returns_zero() -> None:
    s = _stats([], n_discarded=0)
    assert s == Stats(0, 0, 0, 0, 0, 0, 0, 0)


def test_stats_single_sample() -> None:
    s = _stats([1.0], n_discarded=2)
    assert s.median == 1.0
    assert s.mean == 1.0
    assert s.stddev == 0.0
    assert s.iqr == 0.0
    assert s.min == 1.0
    assert s.max == 1.0
    assert s.n_valid == 1
    assert s.n_discarded == 2


def test_stats_ten_samples() -> None:
    s = _stats([i + 1.0 for i in range(10)], n_discarded=1)
    assert s.median == 5.5
    assert s.min == 1.0
    assert s.max == 10.0
    assert s.n_valid == 10


def test_main_emits_stub_results_md_when_no_runs(tmp_path: Path) -> None:
    """No timing data → emit a `[NO RUNS]` stub passing all RFC-0011 lints."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    out = tmp_path / "RESULTS.md"
    rc = main(["--results-dir", str(rdir), "--out", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "[NO RUNS]" in text
    # Methodology-lint sections present.
    for h in ("## Headline", "## Distributions", "## Stability", "## Apples-to-apples disclosures", "## Discards", "## Reproduction", "## Run metadata", "## Underlying numbers"):
        assert h in text


def test_main_renders_real_data(tmp_path: Path) -> None:
    """≥ MIN_RUNS_M1 samples per prover → real-context render."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    # 12 samples each — D-INV-3 drops one (first), leaving 11 ≥ MIN_RUNS_M1=10.
    sp1_times = [10.0 + i * 0.1 for i in range(12)]
    stwo_times = [5.0 + i * 0.05 for i in range(12)]
    _write_hyperfine_json(rdir / "sp1_v0.1_r1.timing.json", sp1_times)
    _write_hyperfine_json(rdir / "stwo_v0.1_r1.timing.json", stwo_times)
    # Verify timings — need ≥ 40 valid.
    sp1_verify = [0.03] * 40
    stwo_verify = [0.04] * 40
    _write_hyperfine_json(rdir / "sp1_v0.1_r1.verify.json", sp1_verify)
    _write_hyperfine_json(rdir / "stwo_v0.1_r1.verify.json", stwo_verify)

    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[NO RUNS]" not in text
    # Ratio SP1 / Stwo ~ 10.55 / 5.275 ~ 2.0.
    assert "2.0" in text or "2.01" in text


def test_main_refuses_below_minimum_samples(tmp_path: Path) -> None:
    """N < 10 per prover M1 → REPORT.INSUFFICIENT_SAMPLES."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    _write_hyperfine_json(rdir / "sp1_v0.1_r1.timing.json", [1.0, 1.1, 1.2])  # too few
    _write_hyperfine_json(rdir / "stwo_v0.1_r1.timing.json", [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5])
    out = tmp_path / "RESULTS.md"
    rc = main(["--results-dir", str(rdir), "--out", str(out)])
    assert rc == REPORT_EXIT_CODE


def test_main_exits_six_when_results_dir_missing(tmp_path: Path) -> None:
    rdir = tmp_path / "missing"
    out = tmp_path / "RESULTS.md"
    rc = main(["--results-dir", str(rdir), "--out", str(out)])
    assert rc == REPORT_EXIT_CODE


def test_min_runs_constants_match_rfc_0008() -> None:
    """RFC-0008 hard-pins 10 / 50 runs; the gate uses 10 / 40 (>=40 = >=50 - 10 cold)."""
    assert MIN_RUNS_M1 == 10
    assert MIN_RUNS_M5 == 40


def test_rendered_results_md_passes_methodology_lint(tmp_path: Path) -> None:
    """End-to-end: `analyze` → `RESULTS.md` → `check-results-md` clean."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    result = subprocess.run(
        ["uv", "run", "check-results-md", str(out)],
        capture_output=True, text=True, check=False,
        cwd=str(repo_root()),
    )
    assert result.returncode == 0, result.stderr
