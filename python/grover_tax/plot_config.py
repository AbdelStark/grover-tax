"""Deterministic matplotlib configuration for `plot.py` (#43).

Per RFC-0013 §"Reproducibility envelope" plot byte-stability requires a
fixed font fallback, fixed image-rendering parameters, fixed RNG seed for
any random aspects (e.g. scatter jitter), and a fixed colourmap. This
module is the single source of truth for those settings; `plot.py` (#43)
calls `configure()` once at the top of its `main()` before any
`matplotlib.pyplot` invocation.

The exact matplotlib version pin lives in `pyproject.toml`
(`matplotlib==3.10.7`). Bumping it requires running this module's
self-test and confirming byte-stable plots — the pin is methodological,
not casual.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "DETERMINISTIC_RCPARAMS",
    "PLOT_RNG_SEED",
    "configure",
]

# Deterministic RNG seed used by `plot.py` for any matplotlib-side stochastic
# aspect (scatter jitter, hatching). Pinned and never changed without a
# fixture-version bump.
PLOT_RNG_SEED: int = 0x67726F76  # b"grov" — stable, distinctive.

# rcParams that suppress every source of plot non-determinism we know about.
# Documented per-key so a future bump can be reviewed in isolation.
DETERMINISTIC_RCPARAMS: dict[str, Any] = {
    # Font: DejaVu Sans is bundled with matplotlib on every platform, so the
    # rendering is host-independent. Anti-aliasing is on by default; we keep
    # it on so the PNG matches the reference rig.
    "font.family": ["DejaVu Sans"],
    "font.size": 10.0,
    # Hatch pattern density is host-dependent on some matplotlib versions;
    # pin it.
    "hatch.linewidth": 1.0,
    # PNG metadata can leak the wall-clock timestamp of the render. `plot.py`
    # passes `metadata={"Software": "grover-tax v0.1"}` as a savefig kwarg
    # rather than an rcParam (matplotlib's rcParams don't expose metadata
    # control). The two rcParams below pin everything else about savefig.
    "savefig.format": "png",
    "savefig.dpi": 100,
    # PDF output is not used in v0.1 but pinning the backend stops a future
    # accidental switch from drifting.
    "backend": "agg",
    # Colourmap default — `viridis` is colourblind-safe (RFC-0011 §"Distribution
    # plot specifications").
    "image.cmap": "viridis",
    # Axes and tick formatting — pinned so locale changes can't drift labels.
    "axes.formatter.use_locale": False,
    "axes.unicode_minus": False,
}


def configure(extra: Mapping[str, Any] | None = None) -> None:
    """Apply the deterministic matplotlib configuration.

    Args:
        extra: Optional additional `rcParams` to merge on top. Passed-in
            keys override the defaults; useful for one-off tests that need
            to customise a single param without touching the shared dict.

    Calling `configure()` more than once is safe — it idempotently
    re-applies the same params and re-seeds the same RNG. Tests that need
    a fresh RNG state should call `numpy.random.seed(PLOT_RNG_SEED)` (or
    pass a `Generator` themselves).
    """
    # Import inside the function so importing this module never has the
    # side effect of importing matplotlib (which is heavy and pulls in
    # numpy + pillow). Only the actual `configure()` call pays that cost.
    import matplotlib  # noqa: PLC0415 - deferred-import keeps `grover_tax` import-time cheap

    matplotlib.use("agg", force=True)
    matplotlib.rcParams.update(DETERMINISTIC_RCPARAMS)
    if extra:
        matplotlib.rcParams.update(extra)
