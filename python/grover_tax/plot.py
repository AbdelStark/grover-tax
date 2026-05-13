"""`uv run plot` — render the three RFC-0011 plots.

Produces three PNGs under `results/plots/`:

* `wallclock_hist.png` — overlaid histograms of M1 (proof gen wall-clock),
  50 bins, viridis colours, legend top-right.
* `medians_bar.png` — M1 and M5 medians with IQR error bars
  (two subplots, one panel per metric).
* `day1_day2.png` — side-by-side day-1 vs day-2 medians per prover,
  delta percentage annotated above each pair. If `results/day1/` and
  `results/day2/` are not both populated, the plot is rendered with
  a "No day-1 / day-2 data yet" annotation so the embed in
  `RESULTS.md` does not 404.

The renderer is *deterministic*: every plot is fully reproducible from
its inputs.

* `matplotlib.use("Agg")` removes any display backend dependency.
* `font.family = DejaVu Sans` (matplotlib-bundled) avoids host-font
  drift between macOS and Linux.
* PNG metadata (`Software`, `Creation Time`) is stripped so two runs
  on the same inputs produce byte-identical files (RFC-0011 R-T6).

CLI: `uv run plot [--results-dir <path>] [--out <path>]`.

Exit codes:
  0 — every plot emitted.
  6 — `REPORT.MISSING_ARTIFACT`: results directory does not exist.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib as mpl
import matplotlib.pyplot as plt

from grover_tax import logging as gt_logging
from grover_tax.errors import ReportError, ReportSubcode
from grover_tax.paths import results_dir

__all__ = ["main"]

_log = gt_logging.get_logger("grover_tax.plot")

_TIMING_FILE_RE = re.compile(r"^(sp1|stwo)_v0\.1_(.+)\.timing\.json$")
_VERIFY_FILE_RE = re.compile(r"^(sp1|stwo)_v0\.1_(.+)\.verify\.json$")

# Strip non-reproducible PNG metadata so the output is byte-deterministic.
_PNG_METADATA: dict[str, str | None] = {"Software": None, "Creation Time": None}

# Two-series colourblind-safe palette — viridis at 0.25 and 0.75.
_VIRIDIS = mpl.colormaps["viridis"]
_SP1_COLOR = _VIRIDIS(0.25)
_STWO_COLOR = _VIRIDIS(0.75)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plot", description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    rdir = args.results_dir if args.results_dir is not None else results_dir()
    outdir = args.out if args.out is not None else rdir / "plots"

    try:
        _configure_matplotlib()
        if not rdir.is_dir():
            raise ReportError(
                ReportSubcode.MISSING_ARTIFACT,
                f"results dir {rdir} does not exist",
            )
        outdir.mkdir(parents=True, exist_ok=True)

        samples = _load_m1(rdir)
        _plot_wallclock_hist(samples, outdir / "wallclock_hist.png")

        m1_stats = _stats_by_prover(samples)
        m5_stats = _stats_by_prover(_load_m5(rdir))
        _plot_medians_bar(m1_stats, m5_stats, outdir / "medians_bar.png")

        day1 = rdir / "day1"
        day2 = rdir / "day2"
        if day1.is_dir() and day2.is_dir():
            day1_stats = _stats_by_prover(_load_m1(day1))
            day2_stats = _stats_by_prover(_load_m1(day2))
            _plot_day1_day2(day1_stats, day2_stats, outdir / "day1_day2.png")
        else:
            _plot_day1_day2_placeholder(outdir / "day1_day2.png")

        _log.info("plots written to %s", outdir)
        return 0
    except ReportError as e:
        print(str(e), file=sys.stderr)
        return e.exit_code


def _configure_matplotlib() -> None:
    """Lock font + reset rcParams to deterministic values."""
    mpl.rcParams.update({
        "font.family": "DejaVu Sans",
        "savefig.dpi": 100,
        "figure.dpi": 100,
        # Force consistent layout across versions.
        "figure.autolayout": False,
        "axes.grid": False,
        # Strip metadata that varies between runs.
        "savefig.bbox": "tight",
        # Avoid using locale-specific minus signs.
        "axes.unicode_minus": False,
    })


# -- data loading ------------------------------------------------------------


def _load_m1(rdir: Path) -> dict[str, list[float]]:
    """Per-prover M1 samples (cold-cache first sample dropped per series)."""
    out: dict[str, list[float]] = {"sp1": [], "stwo": []}
    for f in sorted(rdir.glob("*.timing.json")):
        m = _TIMING_FILE_RE.match(f.name)
        if m is None:
            continue
        prover = m.group(1)
        data = json.loads(f.read_text(encoding="utf-8"))
        times = list(data.get("results", [{}])[0].get("times", []))
        if times:
            out[prover].extend(times[1:])  # D-INV-3 cold_cache drop
    return out


def _load_m5(rdir: Path) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {"sp1": [], "stwo": []}
    for f in sorted(rdir.glob("*.verify.json")):
        m = _VERIFY_FILE_RE.match(f.name)
        if m is None:
            continue
        prover = m.group(1)
        data = json.loads(f.read_text(encoding="utf-8"))
        out[prover].extend(data.get("results", [{}])[0].get("times", []))
    return out


def _stats_by_prover(samples: dict[str, list[float]]) -> dict[str, tuple[float, float]]:
    """Return (median, iqr) per prover."""
    out: dict[str, tuple[float, float]] = {}
    for prover, s in samples.items():
        if not s:
            out[prover] = (0.0, 0.0)
            continue
        sorted_s = sorted(s)
        median = statistics.median(sorted_s)
        iqr = 0.0
        if len(sorted_s) > 1:
            q1 = statistics.median(sorted_s[: len(sorted_s) // 2])
            q3 = statistics.median(sorted_s[(len(sorted_s) + 1) // 2 :])
            iqr = q3 - q1
        out[prover] = (median, iqr)
    return out


# -- plots -------------------------------------------------------------------


def _plot_wallclock_hist(samples: dict[str, list[float]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    if samples["sp1"]:
        ax.hist(
            samples["sp1"],
            bins=50,
            alpha=0.6,
            color=_SP1_COLOR,
            label="SP1 + Groth16",
        )
    if samples["stwo"]:
        ax.hist(
            samples["stwo"],
            bins=50,
            alpha=0.6,
            color=_STWO_COLOR,
            label="Stwo",
        )
    ax.set_xlabel("Wall-clock (s)")
    ax.set_ylabel("Count")
    ax.set_title("Proof generation wall-clock (M1) — overlaid histograms")
    if samples["sp1"] or samples["stwo"]:
        ax.legend(loc="upper right")
    else:
        ax.text(
            0.5, 0.5, "No M1 samples available",
            ha="center", va="center", transform=ax.transAxes,
        )
    fig.savefig(out, metadata=_PNG_METADATA)
    plt.close(fig)


def _plot_medians_bar(
    m1: dict[str, tuple[float, float]],
    m5: dict[str, tuple[float, float]],
    out: Path,
) -> None:
    fig, (ax_m1, ax_m5) = plt.subplots(1, 2, figsize=(10.0, 5.0))

    provers = ["SP1", "Stwo"]
    colors = [_SP1_COLOR, _STWO_COLOR]

    m1_medians = [m1["sp1"][0], m1["stwo"][0]]
    m1_iqrs = [m1["sp1"][1], m1["stwo"][1]]
    ax_m1.bar(provers, m1_medians, yerr=m1_iqrs, capsize=8, color=colors)
    ax_m1.set_ylabel("Wall-clock (s)")
    ax_m1.set_title("M1: Proof generation median (error bars = IQR)")

    # Convert verifier seconds to milliseconds for the bar chart.
    m5_medians = [m5["sp1"][0] * 1000, m5["stwo"][0] * 1000]
    m5_iqrs = [m5["sp1"][1] * 1000, m5["stwo"][1] * 1000]
    ax_m5.bar(provers, m5_medians, yerr=m5_iqrs, capsize=8, color=colors)
    ax_m5.set_ylabel("Wall-clock (ms)")
    ax_m5.set_title("M5: Verifier median (error bars = IQR)")

    fig.savefig(out, metadata=_PNG_METADATA)
    plt.close(fig)


def _plot_day1_day2(
    day1: dict[str, tuple[float, float]],
    day2: dict[str, tuple[float, float]],
    out: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 5.0))

    provers = ["SP1", "Stwo"]
    x_positions = [0.0, 1.0]
    width = 0.35

    d1 = [day1["sp1"][0], day1["stwo"][0]]
    d2 = [day2["sp1"][0], day2["stwo"][0]]

    ax.bar(
        [x - width / 2 for x in x_positions], d1,
        width=width, label="Day 1", color=_SP1_COLOR,
    )
    ax.bar(
        [x + width / 2 for x in x_positions], d2,
        width=width, label="Day 2", color=_STWO_COLOR,
    )
    ax.set_xticks(x_positions)
    ax.set_xticklabels(provers)
    ax.set_ylabel("M1 median wall-clock (s)")
    ax.set_title("Day-1 vs Day-2 M1 medians")
    ax.legend(loc="upper right")

    for x, a, b in zip(x_positions, d1, d2, strict=False):
        if a == 0:
            continue
        delta = (b - a) / a * 100
        top = max(a, b)
        ax.annotate(
            f"{delta:+.2f}%",
            xy=(x, top), xytext=(0, 12), textcoords="offset points",
            ha="center", fontsize=10,
        )

    fig.savefig(out, metadata=_PNG_METADATA)
    plt.close(fig)


def _plot_day1_day2_placeholder(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    ax.axis("off")
    ax.text(
        0.5, 0.5, "No day-1 / day-2 data yet",
        ha="center", va="center", transform=ax.transAxes, fontsize=14,
    )
    ax.set_title("Day-1 vs Day-2 M1 medians")
    fig.savefig(out, metadata=_PNG_METADATA)
    plt.close(fig)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
