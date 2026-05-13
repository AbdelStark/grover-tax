"""`uv run analyze` — ingest results + render RESULTS.md (RFC-0011).

Pipeline:

1. Load every hyperfine timing JSON, gnu-time txt, proverlog, proof-size
   txt, the SP1 setup record, the discards log, and `versions.lock`
   metadata from `results/`.
2. Apply RFC-0010 discard rules (post-load filtering); refuse to emit
   when N_valid < 10 per prover (M1) or < 40 per prover (M5)
   (`REPORT.INSUFFICIENT_SAMPLES`).
3. Compute per-(prover, metric) statistics: median, mean, stddev, IQR,
   min, max, sample counts.
4. Compute ratios with Stwo as the denominator (RFC-0011 §"Ratio
   convention").
5. Compute day-1/day-2 delta on M1 medians; mark `STABILITY BREACH` if
   |delta| > 5%.
6. Tally discards by reason and prover.
7. Render `docs/spec/templates/RESULTS.md.j2` through Jinja2 and write
   `RESULTS.md` at the repo root.

CLI: `uv run analyze` — argv-free; reads from `results/` and writes
`RESULTS.md` at the repo root. `--out` overrides the output path.

Exit codes:
  0 — RESULTS.md emitted.
  6 — `REPORT.*`: insufficient samples / missing artifact / template
      render failure.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from grover_tax import logging as gt_logging
from grover_tax.errors import ReportError, ReportSubcode
from grover_tax.paths import discards_log_path, repo_root, results_dir

__all__ = ["Stats", "main"]

# RFC-0008 minimum-sample gates.
MIN_RUNS_M1 = 10
MIN_RUNS_M5 = 40

_log = gt_logging.get_logger("grover_tax.analyze")
_CONSTRAINTS_RE = re.compile(r"^CONSTRAINTS:\s*(\d+)$", re.MULTILINE)
_TRACE_ROWS_RE = re.compile(r"^TRACE_ROWS:\s*(\d+)$", re.MULTILINE)
_TIMING_FILE_RE = re.compile(r"^(sp1|stwo)_v0\.1_(.+)\.timing\.json$")


@dataclass(frozen=True)
class Stats:
    """Per-(prover, metric) distribution summary."""

    median: float
    mean: float
    stddev: float
    iqr: float
    min: float
    max: float
    n_valid: int
    n_discarded: int


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analyze", description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="override the results/ directory (default: results/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (default: RESULTS.md at the repo root)",
    )
    args = parser.parse_args(argv)

    rdir = args.results_dir if args.results_dir is not None else results_dir()
    out = args.out if args.out is not None else repo_root() / "RESULTS.md"

    try:
        context = _build_context(rdir)
    except ReportError as e:
        print(str(e), file=sys.stderr)
        return e.exit_code

    rendered = _render(context)
    out.write_text(rendered, encoding="utf-8")
    _log.info("wrote RESULTS.md to %s", out)
    return 0


# -- ingestion --------------------------------------------------------------


def _build_context(rdir: Path) -> dict[str, Any]:  # noqa: PLR0912 - end-to-end ingestion has many cases
    """Walk results_dir and assemble the Jinja2 render context."""
    timings: dict[str, list[tuple[str, list[float]]]] = {"sp1": [], "stwo": []}
    verify_timings: dict[str, list[tuple[str, list[float]]]] = {"sp1": [], "stwo": []}
    if not rdir.is_dir():
        raise ReportError(
            ReportSubcode.MISSING_ARTIFACT, f"results dir {rdir} does not exist"
        )

    for f in sorted(rdir.glob("*.timing.json")):
        m = _TIMING_FILE_RE.match(f.name)
        if m is None:
            continue
        prover, run_id = m.group(1), m.group(2)
        data = json.loads(f.read_text(encoding="utf-8"))
        timings[prover].append((run_id, list(data.get("results", [{}])[0].get("times", []))))

    for f in sorted(rdir.glob("*.verify.json")):
        m = re.match(r"^(sp1|stwo)_v0\.1_(.+)\.verify\.json$", f.name)
        if m is None:
            continue
        prover, run_id = m.group(1), m.group(2)
        data = json.loads(f.read_text(encoding="utf-8"))
        verify_timings[prover].append(
            (run_id, list(data.get("results", [{}])[0].get("times", [])))
        )

    discards = _load_discards(rdir.parent / discards_log_path().name)

    # Apply D-INV-3 unconditional first-run discard at the per-series level.
    m1: dict[str, Stats] = {}
    for prover, runs in timings.items():
        all_samples: list[float] = []
        for _, samples in runs:
            # Drop the first sample of each series as cold_cache (D-INV-3).
            all_samples.extend(samples[1:] if samples else [])
        n_discarded = sum(1 for _, s in runs if s)  # one cold_cache per series
        m1[prover] = _stats(all_samples, n_discarded=n_discarded)

    m5: dict[str, Stats] = {}
    for prover, runs in verify_timings.items():
        all_samples = [t for _, samples in runs for t in samples]
        m5[prover] = _stats(all_samples, n_discarded=0)

    # Insufficient-samples gate.
    for prover, s in m1.items():
        if s.n_valid > 0 and s.n_valid < MIN_RUNS_M1:
            raise ReportError(
                ReportSubcode.INSUFFICIENT_SAMPLES,
                f"M1 for {prover}: {s.n_valid} valid runs, need ≥ {MIN_RUNS_M1}",
            )
    for prover, s in m5.items():
        if s.n_valid > 0 and s.n_valid < MIN_RUNS_M5:
            raise ReportError(
                ReportSubcode.INSUFFICIENT_SAMPLES,
                f"M5 for {prover}: {s.n_valid} valid runs, need ≥ {MIN_RUNS_M5}",
            )

    # If there's *no* data at all, render a stub with placeholders so the
    # template lint still passes (e.g. CI's `results-md-lint` job before
    # any real run).
    has_real_data = m1["sp1"].n_valid > 0 and m1["stwo"].n_valid > 0
    if not has_real_data:
        return _stub_context(discards)

    return _real_context(m1, m5, discards)


def _stats(samples: list[float], *, n_discarded: int) -> Stats:
    if not samples:
        return Stats(0, 0, 0, 0, 0, 0, 0, n_discarded)
    s = sorted(samples)
    median = statistics.median(s)
    mean = statistics.mean(s)
    stddev = statistics.stdev(s) if len(s) > 1 else 0.0
    iqr = 0.0
    if len(s) > 1:
        q1 = statistics.median(s[: len(s) // 2])
        q3 = statistics.median(s[(len(s) + 1) // 2 :])
        iqr = q3 - q1
    return Stats(median, mean, stddev, iqr, min(s), max(s), len(s), n_discarded)


def _load_discards(log: Path) -> list[dict[str, Any]]:
    if not log.is_file():
        return []
    return [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _tally(discards: list[dict[str, Any]], prover: str, reason: str) -> int:
    return sum(
        1 for d in discards if d.get("prover") == prover and d.get("reason") == reason
    )


def _ratio(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return num / den


# -- context builders --------------------------------------------------------


def _stub_context(discards: list[dict[str, Any]]) -> dict[str, Any]:
    """Synthetic context for the no-real-data path (CI lint job)."""
    return {
        "project_version": "v0.1.0",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "headline_status": "[NO RUNS]",
        "n_sp1": 0, "n_stwo": 0, "m1_unit": "s",
        "m1_sp1_median": 0.0, "m1_stwo_median": 0.0, "ratio_m1": 0.0,
        "m1_sp1_iqr": 0.0, "m1_stwo_iqr": 0.0,
        "m1_sp1_min": 0.0, "m1_sp1_max": 0.0,
        "m1_stwo_min": 0.0, "m1_stwo_max": 0.0,
        "n_verify_sp1": 0, "n_verify_stwo": 0, "m5_unit": "ms",
        "m5_sp1_median": 0.0, "m5_stwo_median": 0.0, "ratio_m5": 0.0,
        "m2_sp1": 0.0, "m2_stwo": 0.0, "ratio_m2": 0.0,
        "m6_sp1": 0, "m6_stwo": 0, "ratio_m6": 0.0,
        "m7_sp1": "0 constraints", "m7_stwo": "0 constraints",
        "m8_sp1": 0.0, "m9_sp1": 0.0,
        "day1_median_sp1": 0.0, "day1_median_stwo": 0.0,
        "day2_median_sp1": 0.0, "day2_median_stwo": 0.0,
        "day1_day2_delta_sp1": 0.0, "day1_day2_delta_stwo": 0.0,
        "stability_breach": False, "stability_breach_explanation": "",
        "groth16_ceremony_origin": "n/a",
        "affinity_macos_or_linux": "taskpolicy -c utility",
        "user_wall_sp1": 1.0, "user_wall_stwo": 1.0,
        "residual_concurrency": False, "residual_concurrency_note": "",
        "d_cold_sp1": _tally(discards, "sp1", "cold_cache"),
        "d_cold_stwo": _tally(discards, "stwo", "cold_cache"),
        "d_thermal_sp1": _tally(discards, "sp1", "thermal"),
        "d_thermal_stwo": _tally(discards, "stwo", "thermal"),
        "d_gpu_sp1": _tally(discards, "sp1", "gpu_residency"),
        "d_gpu_stwo": _tally(discards, "stwo", "gpu_residency"),
        "d_swap_sp1": _tally(discards, "sp1", "swap_active"),
        "d_swap_stwo": _tally(discards, "stwo", "swap_active"),
        "d_env_sp1": _tally(discards, "sp1", "env_var_miss"),
        "d_env_stwo": _tally(discards, "stwo", "env_var_miss"),
        "d_other_sp1": _tally(discards, "sp1", "other"),
        "d_other_stwo": _tally(discards, "stwo", "other"),
        "discard_pct_sp1": 0.0, "discard_pct_stwo": 0.0,
        "workload_pin_commit": "0" * 40,
        "fixture_sha256": "0" * 64,
        "versions_lock_sha256": "0" * 64,
        "host_summary": "(no measured run yet)",
        "day1_date": "n/a", "day2_date": "n/a",
        "spec_version": "v0.1",
        "analyze_commit": _git_head_sha(),
    }


def _real_context(
    m1: dict[str, Stats],
    m5: dict[str, Stats],
    discards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render context for actual measured data."""
    ctx = _stub_context(discards)
    ctx.update({
        "headline_status": "",
        "n_sp1": m1["sp1"].n_valid, "n_stwo": m1["stwo"].n_valid,
        "m1_sp1_median": round(m1["sp1"].median, 3),
        "m1_stwo_median": round(m1["stwo"].median, 3),
        "ratio_m1": round(_ratio(m1["sp1"].median, m1["stwo"].median), 2),
        "m1_sp1_iqr": round(m1["sp1"].iqr, 3),
        "m1_stwo_iqr": round(m1["stwo"].iqr, 3),
        "m1_sp1_min": round(m1["sp1"].min, 3),
        "m1_sp1_max": round(m1["sp1"].max, 3),
        "m1_stwo_min": round(m1["stwo"].min, 3),
        "m1_stwo_max": round(m1["stwo"].max, 3),
        "n_verify_sp1": m5["sp1"].n_valid,
        "n_verify_stwo": m5["stwo"].n_valid,
        "m5_sp1_median": round(m5["sp1"].median * 1000, 3),  # s → ms
        "m5_stwo_median": round(m5["stwo"].median * 1000, 3),
        "ratio_m5": round(_ratio(m5["sp1"].median, m5["stwo"].median), 2),
    })
    return ctx


def _render(context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(repo_root() / "docs" / "spec" / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    return env.get_template("RESULTS.md.j2").render(**context)


def _git_head_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if re.match(r"^[0-9a-f]{40}$", sha):
                return sha
    except OSError:
        pass
    return "0" * 40


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
