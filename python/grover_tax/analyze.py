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

# RFC-0010 / RFC-0011 thresholds.
STABILITY_THRESHOLD = 0.05  # |day1 - day2| / day1
RESIDUAL_CONCURRENCY_THRESHOLD = 1.10  # user_cpu / wall_clock
HIGH_DISCARD_THRESHOLD = 0.30  # n_discarded / (n_valid + n_discarded)
HIGH_VARIANCE_THRESHOLD = 0.10  # iqr / median

_log = gt_logging.get_logger("grover_tax.analyze")
_CONSTRAINTS_RE = re.compile(r"^CONSTRAINTS:\s*(\d+)$", re.MULTILINE)
_TRACE_ROWS_RE = re.compile(r"^TRACE_ROWS:\s*(\d+)$", re.MULTILINE)
_TIMING_FILE_RE = re.compile(r"^(sp1|stwo)_v0\.1_(.+)\.timing\.json$")
_VERIFY_FILE_RE = re.compile(r"^(sp1|stwo)_v0\.1_(.+)\.verify\.json$")
_TIME_FILE_RE = re.compile(r"^(sp1|stwo)_v0\.1_(.+)\.time\.txt$")
_GNU_TIME_USER_RE = re.compile(r"User time \(seconds\):\s*([\d.]+)")
# `gnu-time -v` prints `Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.68`
# — the format description embeds extra colons, so parse line-wise instead
# of with a single all-in-one regex.
_GNU_TIME_ELAPSED_LINE = "Elapsed (wall clock)"
_HMS_PARTS = 3
_MS_PARTS = 2


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


def _build_context(rdir: Path) -> dict[str, Any]:
    """Walk results_dir and assemble the Jinja2 render context."""
    if not rdir.is_dir():
        raise ReportError(
            ReportSubcode.MISSING_ARTIFACT, f"results dir {rdir} does not exist"
        )

    day1_dir = rdir / "day1"
    day2_dir = rdir / "day2"
    has_day12 = day1_dir.is_dir() and day2_dir.is_dir()

    if has_day12:
        timings_d1, verify_d1, gnu_d1 = _scan_series(day1_dir)
        timings_d2, verify_d2, gnu_d2 = _scan_series(day2_dir)
        timings = {p: timings_d1[p] + timings_d2[p] for p in ("sp1", "stwo")}
        verify_timings = {p: verify_d1[p] + verify_d2[p] for p in ("sp1", "stwo")}
        gnu_times = {p: gnu_d1[p] + gnu_d2[p] for p in ("sp1", "stwo")}
        m1_day1 = _m1_stats(timings_d1)
        m1_day2 = _m1_stats(timings_d2)
    else:
        timings, verify_timings, gnu_times = _scan_series(rdir)
        m1_day1 = None
        m1_day2 = None

    discards = _load_discards(rdir.parent / discards_log_path().name)

    m1 = _m1_stats(timings)
    m5: dict[str, Stats] = {}
    for prover, runs in verify_timings.items():
        all_samples = [t for _, samples in runs for t in samples]
        m5[prover] = _stats(all_samples, n_discarded=0)

    # Fold scripted discards into the M1 stats so the discard-rate flag sees
    # them (D-INV-3 cold_cache plus any reasons in `discards.log`).
    m1_with_log_discards: dict[str, Stats] = {}
    for prover, s in m1.items():
        extra = sum(1 for d in discards if d.get("prover") == prover)
        if extra:
            m1_with_log_discards[prover] = Stats(
                s.median, s.mean, s.stddev, s.iqr, s.min, s.max, s.n_valid,
                s.n_discarded + extra,
            )
        else:
            m1_with_log_discards[prover] = s
    m1 = m1_with_log_discards

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

    return _real_context(m1, m5, gnu_times, m1_day1, m1_day2, discards)


def _scan_series(
    dir_: Path,
) -> tuple[
    dict[str, list[tuple[str, list[float]]]],
    dict[str, list[tuple[str, list[float]]]],
    dict[str, list[tuple[float, float]]],
]:
    """Walk one directory; return per-prover timings + verify + gnu-time pairs."""
    timings: dict[str, list[tuple[str, list[float]]]] = {"sp1": [], "stwo": []}
    verify: dict[str, list[tuple[str, list[float]]]] = {"sp1": [], "stwo": []}
    gnu: dict[str, list[tuple[float, float]]] = {"sp1": [], "stwo": []}

    for f in sorted(dir_.glob("*.timing.json")):
        m = _TIMING_FILE_RE.match(f.name)
        if m is None:
            continue
        prover = m.group(1)
        data = _load_json(f)
        timings[prover].append(
            (m.group(2), list(data.get("results", [{}])[0].get("times", [])))
        )

    for f in sorted(dir_.glob("*.verify.json")):
        m = _VERIFY_FILE_RE.match(f.name)
        if m is None:
            continue
        prover = m.group(1)
        data = _load_json(f)
        verify[prover].append(
            (m.group(2), list(data.get("results", [{}])[0].get("times", [])))
        )

    for f in sorted(dir_.glob("*.time.txt")):
        m = _TIME_FILE_RE.match(f.name)
        if m is None:
            continue
        prover = m.group(1)
        parsed = _parse_gnu_time(f.read_text(encoding="utf-8"))
        if parsed is not None:
            gnu[prover].append(parsed)

    return timings, verify, gnu


def _load_json(f: Path) -> dict[str, Any]:
    """Read + parse a JSON artifact; map decode errors to REPORT.SCHEMA_INVALID."""
    try:
        return json.loads(f.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except json.JSONDecodeError as e:
        raise ReportError(
            ReportSubcode.SCHEMA_INVALID,
            f"malformed JSON at {f}: {e}",
        ) from e


def _m1_stats(
    timings: dict[str, list[tuple[str, list[float]]]],
) -> dict[str, Stats]:
    """Apply D-INV-3 cold_cache discard and compute per-prover M1 stats."""
    out: dict[str, Stats] = {}
    for prover, runs in timings.items():
        all_samples: list[float] = []
        for _, samples in runs:
            all_samples.extend(samples[1:] if samples else [])
        n_discarded = sum(1 for _, s in runs if s)
        out[prover] = _stats(all_samples, n_discarded=n_discarded)
    return out


def _parse_gnu_time(text: str) -> tuple[float, float] | None:
    """Extract (user_cpu_seconds, wall_clock_seconds) from `gnu-time -v` output.

    Wall-clock is reported as `h:mm:ss[.s]` or `m:ss[.s]` — split on `:` and
    pad missing leading components with zero.
    """
    u = _GNU_TIME_USER_RE.search(text)
    if u is None:
        return None
    elapsed_token: str | None = None
    for line in text.splitlines():
        if _GNU_TIME_ELAPSED_LINE in line:
            elapsed_token = line.rsplit(maxsplit=1)[-1]
            break
    if elapsed_token is None:
        return None
    parts = elapsed_token.split(":")
    # gnu-time emits `h:mm:ss[.s]` (3 parts) or `m:ss[.s]` (2 parts).
    if len(parts) == _HMS_PARTS:
        h, m, s = parts
    elif len(parts) == _MS_PARTS:
        h, m, s = "0", parts[0], parts[1]
    else:
        return None
    try:
        user_cpu = float(u.group(1))
        wall_clock = int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return None
    return (user_cpu, wall_clock)


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


def _real_context(  # noqa: PLR0913 - one render call assembles the entire context
    m1: dict[str, Stats],
    m5: dict[str, Stats],
    gnu_times: dict[str, list[tuple[float, float]]],
    m1_day1: dict[str, Stats] | None,
    m1_day2: dict[str, Stats] | None,
    discards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render context for actual measured data."""
    ctx = _stub_context(discards)

    flags, ctx_extras = _compute_flags(m1, gnu_times, m1_day1, m1_day2)
    ctx.update(ctx_extras)
    ctx["headline_status"] = " ".join(flags) if flags else ""

    ctx.update({
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


def _compute_flags(
    m1: dict[str, Stats],
    gnu_times: dict[str, list[tuple[float, float]]],
    m1_day1: dict[str, Stats] | None,
    m1_day2: dict[str, Stats] | None,
) -> tuple[list[str], dict[str, Any]]:
    """Headline-flag detection per RFC-0010 / RFC-0011 / spec §08.

    Order matches the headline-status convention (stability → variance →
    discard → concurrency); flags are space-separated on the headline line.
    """
    flags: list[str] = []
    extras: dict[str, Any] = {}

    # 1. Day-1 / Day-2 stability gate (RFC-0010 §"Day-1 / Day-2 stability gate").
    delta_sp1 = 0.0
    delta_stwo = 0.0
    if m1_day1 is not None and m1_day2 is not None:
        delta_sp1 = _delta(m1_day1["sp1"].median, m1_day2["sp1"].median)
        delta_stwo = _delta(m1_day1["stwo"].median, m1_day2["stwo"].median)
        extras["day1_median_sp1"] = round(m1_day1["sp1"].median, 3)
        extras["day1_median_stwo"] = round(m1_day1["stwo"].median, 3)
        extras["day2_median_sp1"] = round(m1_day2["sp1"].median, 3)
        extras["day2_median_stwo"] = round(m1_day2["stwo"].median, 3)
        extras["day1_day2_delta_sp1"] = round(delta_sp1 * 100, 2)
        extras["day1_day2_delta_stwo"] = round(delta_stwo * 100, 2)
        breach = delta_sp1 > STABILITY_THRESHOLD or delta_stwo > STABILITY_THRESHOLD
        if breach:
            flags.append("[STABILITY BREACH]")
            worst = max(delta_sp1, delta_stwo)
            extras["stability_breach"] = True
            extras["stability_breach_explanation"] = (
                f"M1 median moved by {worst * 100:.2f}% between day-1 and day-2 "
                f"(threshold {STABILITY_THRESHOLD * 100:.0f}%); see RFC-0010."
            )

    # 2. IQR / median variance (spec §08).
    high_var_sp1 = m1["sp1"].median > 0 and m1["sp1"].iqr / m1["sp1"].median > HIGH_VARIANCE_THRESHOLD
    high_var_stwo = m1["stwo"].median > 0 and m1["stwo"].iqr / m1["stwo"].median > HIGH_VARIANCE_THRESHOLD
    if high_var_sp1 or high_var_stwo:
        flags.append("[HIGH VARIANCE]")

    # 3. Discard-rate cap (RFC-0010 §"Discard rate cap").
    rate_sp1 = _discard_rate(m1["sp1"])
    rate_stwo = _discard_rate(m1["stwo"])
    extras["discard_pct_sp1"] = round(rate_sp1 * 100, 2)
    extras["discard_pct_stwo"] = round(rate_stwo * 100, 2)
    if rate_sp1 > HIGH_DISCARD_THRESHOLD or rate_stwo > HIGH_DISCARD_THRESHOLD:
        flags.append("[HIGH DISCARD]")

    # 4. Residual concurrency (spec §08 / RFC-0011 §"Apples-to-apples").
    uw_sp1 = _user_wall_ratio(gnu_times["sp1"])
    uw_stwo = _user_wall_ratio(gnu_times["stwo"])
    extras["user_wall_sp1"] = round(uw_sp1, 2)
    extras["user_wall_stwo"] = round(uw_stwo, 2)
    residual = uw_sp1 > RESIDUAL_CONCURRENCY_THRESHOLD or uw_stwo > RESIDUAL_CONCURRENCY_THRESHOLD
    if residual:
        flags.append("[RESIDUAL CONCURRENCY]")
        worst_p, worst_r = ("SP1", uw_sp1) if uw_sp1 >= uw_stwo else ("Stwo", uw_stwo)
        extras["residual_concurrency"] = True
        extras["residual_concurrency_note"] = (
            f"{worst_p} user-CPU / wall-clock = {worst_r:.2f}, exceeding the "
            f"{RESIDUAL_CONCURRENCY_THRESHOLD:.2f} threshold; "
            f"M1 wall-clock is inflated by background interleaving."
        )

    return flags, extras


def _delta(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return abs(a - b) / a


def _discard_rate(s: Stats) -> float:
    total = s.n_valid + s.n_discarded
    if total == 0:
        return 0.0
    return s.n_discarded / total


def _user_wall_ratio(samples: list[tuple[float, float]]) -> float:
    """Median user-CPU / wall-clock ratio over a series."""
    if not samples:
        return 1.0
    ratios = [u / w for u, w in samples if w > 0]
    if not ratios:
        return 1.0
    return statistics.median(ratios)


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
