"""Tests for `grover_tax.analyze` (#41, #42)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from grover_tax.analyze import (
    HIGH_DISCARD_THRESHOLD,
    HIGH_VARIANCE_THRESHOLD,
    MIN_RUNS_M1,
    MIN_RUNS_M5,
    RESIDUAL_CONCURRENCY_THRESHOLD,
    STABILITY_THRESHOLD,
    Stats,
    _parse_gnu_time,
    _stats,
    main,
)
from grover_tax.errors import REPORT_EXIT_CODE
from grover_tax.paths import repo_root


def _write_hyperfine_json(path: Path, times: list[float]) -> None:
    path.write_text(
        json.dumps({"results": [{"command": "x", "times": times}]}),
        encoding="utf-8",
    )


def _write_gnu_time(path: Path, user_cpu: float, wall_clock: float) -> None:
    """Write a synthetic gnu-time -v output file."""
    minutes = int(wall_clock // 60)
    seconds = wall_clock - minutes * 60
    path.write_text(
        "\tCommand being timed: \"...\"\n"
        f"\tUser time (seconds): {user_cpu:.2f}\n"
        "\tSystem time (seconds): 0.05\n"
        "\tPercent of CPU this job got: 110%\n"
        f"\tElapsed (wall clock) time (h:mm:ss or m:ss): {minutes}:{seconds:05.2f}\n"
        "\tMaximum resident set size (kbytes): 4096\n",
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


def test_parse_gnu_time_minutes_seconds_format() -> None:
    text = (
        "Command being timed: \"...\"\n"
        "User time (seconds): 1.23\n"
        "System time (seconds): 0.05\n"
        "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.68\n"
    )
    parsed = _parse_gnu_time(text)
    assert parsed is not None
    user, wall = parsed
    assert user == 1.23
    assert abs(wall - 1.68) < 1e-9


def test_parse_gnu_time_hours_minutes_seconds_format() -> None:
    text = (
        "User time (seconds): 100.0\n"
        "Elapsed (wall clock) time (h:mm:ss or m:ss): 1:02:30.5\n"
    )
    parsed = _parse_gnu_time(text)
    assert parsed is not None
    user, wall = parsed
    assert user == 100.0
    assert abs(wall - (3600 + 120 + 30.5)) < 1e-9


def test_parse_gnu_time_returns_none_on_garbage() -> None:
    assert _parse_gnu_time("not a gnu-time file") is None


def _write_full_series(
    dir_: Path,
    prover: str,
    run_id: str,
    timings: list[float],
    verify: list[float],
    *,
    user_cpu: float | None = None,
    wall_clock: float | None = None,
) -> None:
    base = dir_ / f"{prover}_v0.1_{run_id}"
    _write_hyperfine_json(Path(f"{base}.timing.json"), timings)
    _write_hyperfine_json(Path(f"{base}.verify.json"), verify)
    if user_cpu is not None and wall_clock is not None:
        _write_gnu_time(Path(f"{base}.time.txt"), user_cpu, wall_clock)


def test_stability_breach_at_six_percent(tmp_path: Path) -> None:
    """Day-1 = 1.0 s, day-2 = 1.06 s → 6% delta → [STABILITY BREACH]."""
    rdir = tmp_path / "results"
    day1 = rdir / "day1"
    day2 = rdir / "day2"
    day1.mkdir(parents=True)
    day2.mkdir()
    # Day-1: 12 sp1 samples ~ 1.0 s, 12 stwo ~ 0.5 s.
    _write_full_series(day1, "sp1", "r1", [1.0] * 12, [0.04] * 40)
    _write_full_series(day1, "stwo", "r1", [0.5] * 12, [0.03] * 40)
    # Day-2: sp1 ~ 1.06 s (6% above day-1).
    _write_full_series(day2, "sp1", "r1", [1.06] * 12, [0.04] * 40)
    _write_full_series(day2, "stwo", "r1", [0.5] * 12, [0.03] * 40)

    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[STABILITY BREACH]" in text


def test_no_stability_breach_at_four_percent(tmp_path: Path) -> None:
    """Day-1 = 1.0 s, day-2 = 1.04 s → 4% delta → no flag."""
    rdir = tmp_path / "results"
    day1 = rdir / "day1"
    day2 = rdir / "day2"
    day1.mkdir(parents=True)
    day2.mkdir()
    _write_full_series(day1, "sp1", "r1", [1.0] * 12, [0.04] * 40)
    _write_full_series(day1, "stwo", "r1", [0.5] * 12, [0.03] * 40)
    _write_full_series(day2, "sp1", "r1", [1.04] * 12, [0.04] * 40)
    _write_full_series(day2, "stwo", "r1", [0.5] * 12, [0.03] * 40)

    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[STABILITY BREACH]" not in text


def test_residual_concurrency_at_one_fifteen(tmp_path: Path) -> None:
    """user-CPU / wall-clock = 1.15 → > 1.10 → [RESIDUAL CONCURRENCY]."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    # 12 samples per prover, median wall-clock ≈ 1.0 s; gnu-time user-CPU / wall = 1.15.
    _write_full_series(rdir, "sp1", "r1", [1.0] * 12, [0.04] * 40, user_cpu=1.15, wall_clock=1.0)
    _write_full_series(rdir, "stwo", "r1", [0.5] * 12, [0.03] * 40, user_cpu=0.55, wall_clock=0.5)
    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[RESIDUAL CONCURRENCY]" in text


def test_no_residual_concurrency_at_one_oh_five(tmp_path: Path) -> None:
    """user-CPU / wall-clock = 1.05 → ≤ 1.10 → no flag."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    _write_full_series(rdir, "sp1", "r1", [1.0] * 12, [0.04] * 40, user_cpu=1.05, wall_clock=1.0)
    _write_full_series(rdir, "stwo", "r1", [0.5] * 12, [0.03] * 40, user_cpu=0.52, wall_clock=0.5)
    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[RESIDUAL CONCURRENCY]" not in text


def test_high_variance_above_threshold(tmp_path: Path) -> None:
    """IQR / median > 10% → [HIGH VARIANCE]."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    # 12 samples; first drops as cold-cache; 11 remaining span 0.8..1.3 step 0.05:
    #   median = 1.05, Q1 = 0.9, Q3 = 1.2, IQR = 0.3, IQR/median ≈ 0.286 → > 0.10.
    sp1 = [0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3]
    stwo = [0.5] * 12  # tight Stwo; breach must come from SP1.
    _write_full_series(rdir, "sp1", "r1", sp1, [0.04] * 40)
    _write_full_series(rdir, "stwo", "r1", stwo, [0.03] * 40)
    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[HIGH VARIANCE]" in text


def test_high_variance_below_threshold(tmp_path: Path) -> None:
    """Tight series → no [HIGH VARIANCE]."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    # 11 distinct samples after cold-cache drop; IQR/median well under 10%.
    sp1 = [0.93, 0.94, 0.952, 0.964, 0.976, 0.988, 1.0, 1.012, 1.024, 1.036, 1.048, 1.06]
    stwo = [0.5] * 12
    _write_full_series(rdir, "sp1", "r1", sp1, [0.04] * 40)
    _write_full_series(rdir, "stwo", "r1", stwo, [0.03] * 40)
    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[HIGH VARIANCE]" not in text


def test_high_discard_at_thirty_three_percent(tmp_path: Path) -> None:
    """Discard log entries push the discard rate over 30% → [HIGH DISCARD]."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    # 11 valid samples per prover after cold-cache; add 6 sp1 thermal discards →
    # rate = 7/(11+7) ≈ 0.389 > 0.30 (cold_cache + 6 thermal).
    _write_full_series(rdir, "sp1", "r1", [1.0] * 12, [0.04] * 40)
    _write_full_series(rdir, "stwo", "r1", [0.5] * 12, [0.03] * 40)
    discards = rdir.parent / "discards.log"
    discards.write_text(
        "\n".join(
            json.dumps({"prover": "sp1", "reason": "thermal", "run_id": f"r1_{i}"})
            for i in range(6)
        ) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[HIGH DISCARD]" in text


def test_multiple_flags_are_space_separated(tmp_path: Path) -> None:
    """Two simultaneous breaches → two flags on the headline."""
    rdir = tmp_path / "results"
    day1 = rdir / "day1"
    day2 = rdir / "day2"
    day1.mkdir(parents=True)
    day2.mkdir()
    # Stability breach + residual concurrency.
    _write_full_series(day1, "sp1", "r1", [1.0] * 12, [0.04] * 40, user_cpu=1.2, wall_clock=1.0)
    _write_full_series(day1, "stwo", "r1", [0.5] * 12, [0.03] * 40, user_cpu=0.5, wall_clock=0.5)
    _write_full_series(day2, "sp1", "r1", [1.10] * 12, [0.04] * 40, user_cpu=1.32, wall_clock=1.1)
    _write_full_series(day2, "stwo", "r1", [0.5] * 12, [0.03] * 40, user_cpu=0.5, wall_clock=0.5)

    out = tmp_path / "RESULTS.md"
    assert main(["--results-dir", str(rdir), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[STABILITY BREACH]" in text
    assert "[RESIDUAL CONCURRENCY]" in text
    # Both must appear on the same line, space-separated.
    headline_line = next(line for line in text.splitlines() if "[STABILITY BREACH]" in line)
    assert "[RESIDUAL CONCURRENCY]" in headline_line


def test_flag_threshold_constants_match_spec() -> None:
    """Sanity-check the four thresholds are the values the spec asserts."""
    assert STABILITY_THRESHOLD == 0.05
    assert RESIDUAL_CONCURRENCY_THRESHOLD == 1.10
    assert HIGH_DISCARD_THRESHOLD == 0.30
    assert HIGH_VARIANCE_THRESHOLD == 0.10


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
