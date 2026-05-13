"""Repo-relative paths for `grover_tax`.

The benchmark deliberately writes every artifact to a path *relative* to the
repo root (see `docs/spec/05-observability.md` §"Redaction" — absolute paths
in logs are a portability and audit-trail hazard). This module provides the
single source of truth for those paths.

Module behaviour:

- `repo_root()` discovers the repo root by walking upward from this module's
  on-disk location until it finds the marker `pyproject.toml`. Cached, since
  the answer cannot change within a Python process.
- Module-level constants under `repo_root()` are computed lazily by callers
  via the helper accessors below — they are not eagerly resolved at import
  time so the module can be imported from contexts that may inspect path
  layout (tests, docs build).

Raises `FileNotFoundError` if no `pyproject.toml` exists between this file
and the filesystem root. That can only happen if the package has been
installed in a non-source-tree mode and called from outside any checkout —
behaviour explicitly out of scope per the issue.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

__all__ = [
    "discards_log_path",
    "fixture_path",
    "fixtures_dir",
    "plots_dir",
    "repo_root",
    "results_dir",
    "schemas_dir",
    "versions_lock_path",
    "workload_md_path",
]

_REPO_MARKER = "pyproject.toml"


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the repo root, identified by an ancestor containing `pyproject.toml`.

    Cached for the process lifetime; the answer cannot change while a Python
    process is running.
    """
    start = Path(__file__).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / _REPO_MARKER).is_file():
            return candidate
    raise FileNotFoundError(
        f"repo_root(): no `{_REPO_MARKER}` found above {start}; "
        "the package appears to be installed outside a grover-tax source checkout"
    )


def workload_md_path() -> Path:
    """Path to `WORKLOAD.md` at the repo root (the workload-pin contract, RFC-0001)."""
    return repo_root() / "WORKLOAD.md"


def fixtures_dir() -> Path:
    """Directory holding the canonical fixtures (`fixtures/v0.1.json`, etc.)."""
    return repo_root() / "fixtures"


def fixture_path(version: str = "v0.1") -> Path:
    """Path to `fixtures/<version>.json`. `version` defaults to the current `v0.1`."""
    return fixtures_dir() / f"{version}.json"


def results_dir() -> Path:
    """Directory holding all per-run measurement artifacts (`<prover>_<ver>_<run>.*`)."""
    return repo_root() / "results"


def plots_dir() -> Path:
    """Directory holding generated plot PNGs (`results/plots/*.png`)."""
    return results_dir() / "plots"


def discards_log_path() -> Path:
    """Append-only log of discarded measurement runs (`results/discards.log`)."""
    return results_dir() / "discards.log"


def schemas_dir() -> Path:
    """Directory holding JSON Schemas (`docs/spec/schemas/`)."""
    return repo_root() / "docs" / "spec" / "schemas"


def versions_lock_path() -> Path:
    """Path to the pinned-toolchain manifest (`versions.lock`)."""
    return repo_root() / "versions.lock"
