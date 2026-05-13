"""Tests for `grover_tax.plot` (#43)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from grover_tax.errors import REPORT_EXIT_CODE
from grover_tax.plot import main


def _write_timing(path: Path, times: list[float]) -> None:
    path.write_text(
        json.dumps({"results": [{"command": "x", "times": times}]}),
        encoding="utf-8",
    )


def _seed_basic_results(rdir: Path) -> None:
    """12 M1 + 40 M5 samples per prover at fixed values."""
    rdir.mkdir(parents=True, exist_ok=True)
    sp1 = [1.0 + i * 0.05 for i in range(12)]
    stwo = [0.5 + i * 0.02 for i in range(12)]
    _write_timing(rdir / "sp1_v0.1_r1.timing.json", sp1)
    _write_timing(rdir / "stwo_v0.1_r1.timing.json", stwo)
    _write_timing(rdir / "sp1_v0.1_r1.verify.json", [0.04] * 40)
    _write_timing(rdir / "stwo_v0.1_r1.verify.json", [0.03] * 40)


def test_plot_emits_three_pngs(tmp_path: Path) -> None:
    rdir = tmp_path / "results"
    _seed_basic_results(rdir)
    rc = main(["--results-dir", str(rdir)])
    assert rc == 0
    plots = rdir / "plots"
    for name in ("wallclock_hist.png", "medians_bar.png", "day1_day2.png"):
        p = plots / name
        assert p.is_file(), f"missing {name}"
        # PNG signature.
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert p.stat().st_size > 1000


def test_plot_is_byte_deterministic(tmp_path: Path) -> None:
    """RFC-0011 R-T6: re-running on identical inputs → byte-identical PNGs."""
    rdir1 = tmp_path / "run1" / "results"
    rdir2 = tmp_path / "run2" / "results"
    _seed_basic_results(rdir1)
    _seed_basic_results(rdir2)
    assert main(["--results-dir", str(rdir1)]) == 0
    assert main(["--results-dir", str(rdir2)]) == 0

    def _hashes(rdir: Path) -> dict[str, str]:
        plots = rdir / "plots"
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(plots.iterdir())
        }

    assert _hashes(rdir1) == _hashes(rdir2)


def test_plot_handles_no_data(tmp_path: Path) -> None:
    """Empty results/ → all three PNGs still emitted (with placeholders)."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    rc = main(["--results-dir", str(rdir)])
    assert rc == 0
    plots = rdir / "plots"
    for name in ("wallclock_hist.png", "medians_bar.png", "day1_day2.png"):
        assert (plots / name).is_file(), f"missing {name}"


def test_plot_handles_imbalanced_samples(tmp_path: Path) -> None:
    """One prover has fewer M1 samples → both prover series still plot."""
    rdir = tmp_path / "results"
    rdir.mkdir()
    _write_timing(rdir / "sp1_v0.1_r1.timing.json", [1.0] * 12)
    _write_timing(rdir / "stwo_v0.1_r1.timing.json", [0.5] * 5)
    _write_timing(rdir / "sp1_v0.1_r1.verify.json", [0.04] * 40)
    _write_timing(rdir / "stwo_v0.1_r1.verify.json", [0.03] * 20)
    assert main(["--results-dir", str(rdir)]) == 0
    assert (rdir / "plots" / "wallclock_hist.png").is_file()


def test_plot_day1_day2_uses_subdirs(tmp_path: Path) -> None:
    """When results/day1/ + day2/ both exist, the day plot uses them."""
    rdir = tmp_path / "results"
    day1 = rdir / "day1"
    day2 = rdir / "day2"
    _seed_basic_results(day1)
    _seed_basic_results(day2)
    # No top-level timing.json — exercises the day-aware path only.
    assert main(["--results-dir", str(rdir)]) == 0
    plots = rdir / "plots"
    assert (plots / "day1_day2.png").is_file()
    # Compare against the no-day1/day2 placeholder: they must differ.
    rdir2 = tmp_path / "no_days" / "results"
    _seed_basic_results(rdir2)
    main(["--results-dir", str(rdir2)])
    placeholder = (rdir2 / "plots" / "day1_day2.png").read_bytes()
    with_days = (plots / "day1_day2.png").read_bytes()
    assert placeholder != with_days


def test_plot_exits_six_when_results_dir_missing(tmp_path: Path) -> None:
    rc = main(["--results-dir", str(tmp_path / "missing")])
    assert rc == REPORT_EXIT_CODE
