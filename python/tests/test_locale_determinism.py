"""Tests for `scripts/locale_env.sh` + `grover_tax.plot_config`.

Implements Rp-T6 from RFC-0013 §"Reproducibility envelope": every
locale-affecting variable is fixed before any measured subprocess.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib

from grover_tax.paths import repo_root

PYPROJECT = repo_root() / "pyproject.toml"
LOCALE_ENV = repo_root() / "scripts" / "locale_env.sh"


# -- matplotlib pin (#8 acceptance) --------------------------------------------


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_matplotlib_is_exactly_pinned() -> None:
    """Acceptance: `matplotlib` carries an exact-version pin."""
    pyproject = _load_pyproject()
    deps = pyproject["project"]["dependencies"]
    matplotlib_lines = [d for d in deps if d.startswith("matplotlib")]
    assert len(matplotlib_lines) == 1, f"expected one matplotlib pin, got {matplotlib_lines}"
    pin = matplotlib_lines[0]
    # Exact-pin form: `matplotlib==<version>`. `~=`, `>=`, `*` are rejected.
    assert "==" in pin, f"matplotlib pin is not exact-form (`==`): {pin!r}"
    assert "*" not in pin and ">=" not in pin and "~=" not in pin
    # The version itself must look like a semver triple.
    _, version = pin.split("==", 1)
    parts = version.split(".")
    assert len(parts) >= 2
    for p in parts:
        # All numeric, no `b1` / `rc2` / etc. Pre-release matplotlib is not
        # methodological.
        assert p.isdigit(), f"matplotlib version part {p!r} is not numeric: {pin!r}"


# -- locale_env.sh (Rp-T6) -----------------------------------------------------


def test_locale_env_sh_exists() -> None:
    assert LOCALE_ENV.is_file()


def test_locale_env_sh_exports_three_required_vars() -> None:
    """Per RFC-0013, the script must export `LANG=C`, `LC_ALL=C`, `TZ=UTC`."""
    text = LOCALE_ENV.read_text(encoding="utf-8")
    assert "export LANG=C" in text
    assert "export LC_ALL=C" in text
    assert "export TZ=UTC" in text


def test_locale_env_sh_sets_vars_when_sourced() -> None:
    """End-to-end: source the script and confirm the three vars are exported.

    Note: BSD `printenv` (macOS default) only accepts one name per call; we
    use `echo` over the three variables instead so the test runs on both
    Linux and macOS without depending on GNU coreutils.
    """
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {LOCALE_ENV} && "
            'echo "LANG=$LANG" && echo "LC_ALL=$LC_ALL" && echo "TZ=$TZ"',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().split("\n")
    assert lines == ["LANG=C", "LC_ALL=C", "TZ=UTC"], f"got {lines}"


def test_locale_env_sh_is_idempotent() -> None:
    """Sourcing twice has the same effect as sourcing once."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {LOCALE_ENV} && source {LOCALE_ENV} && "
            'echo "LANG=$LANG" && echo "LC_ALL=$LC_ALL" && echo "TZ=$TZ"',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split("\n") == ["LANG=C", "LC_ALL=C", "TZ=UTC"]


# -- plot_config (deterministic matplotlib) ------------------------------------


def test_plot_config_imports_without_pulling_in_matplotlib() -> None:
    """Importing `grover_tax.plot_config` is cheap — no matplotlib import yet.

    The matplotlib import is deferred to `configure()`, which is the only
    function tests call when they need the heavy dependency. The
    deferred-import contract keeps `grover_tax` import-time cheap.
    """
    # Confirm matplotlib isn't already loaded before our import. (If another
    # test in the same session already loaded matplotlib, skip the strict
    # check — pytest collects test files top-down and unrelated tests don't
    # touch matplotlib until #43 lands.)
    pre = "matplotlib" in sys.modules
    if not pre:
        import grover_tax.plot_config  # noqa: F401
        assert "matplotlib" not in sys.modules


def test_plot_config_constants_exist() -> None:
    from grover_tax.plot_config import DETERMINISTIC_RCPARAMS, PLOT_RNG_SEED
    assert isinstance(PLOT_RNG_SEED, int)
    assert PLOT_RNG_SEED > 0
    assert isinstance(DETERMINISTIC_RCPARAMS, dict)
    assert DETERMINISTIC_RCPARAMS["backend"] == "agg"
    assert DETERMINISTIC_RCPARAMS["image.cmap"] == "viridis"


def test_plot_config_configure_applies_rcparams() -> None:
    """`configure()` writes our params into matplotlib's runtime config."""
    from grover_tax.plot_config import DETERMINISTIC_RCPARAMS, configure
    configure()
    import matplotlib
    for key, expected in DETERMINISTIC_RCPARAMS.items():
        actual = matplotlib.rcParams[key]
        # `savefig.metadata` is a dict; the rcParams type is also dict.
        # Other keys round-trip as their declared types.
        if isinstance(expected, dict):
            assert dict(actual) == expected, (
                f"rcParam {key} mismatch: expected {expected}, got {actual}"
            )
        else:
            assert actual == expected, (
                f"rcParam {key} mismatch: expected {expected!r}, got {actual!r}"
            )


def test_plot_config_configure_is_idempotent() -> None:
    """Repeated `configure()` calls leave the rcParams in the same state."""
    from grover_tax.plot_config import configure
    configure()
    import matplotlib
    snapshot = {k: matplotlib.rcParams[k] for k in ("backend", "font.family", "image.cmap")}
    configure()
    after = {k: matplotlib.rcParams[k] for k in ("backend", "font.family", "image.cmap")}
    assert snapshot == after


def test_plot_config_configure_accepts_extra_overrides() -> None:
    """`configure(extra={...})` overlays extra params on top of the defaults."""
    from grover_tax.plot_config import configure
    configure(extra={"font.size": 12.0})
    import matplotlib
    assert matplotlib.rcParams["font.size"] == 12.0
    # Reset to defaults for downstream tests.
    configure()
