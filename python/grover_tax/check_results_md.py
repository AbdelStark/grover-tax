"""Methodology lint for `RESULTS.md`.

RFC-0011 §"Methodology lints" specifies that every generated `RESULTS.md`
must contain a fixed set of section headers and disclosure phrases. The
lint is intentionally greppy — its purpose is to catch the
already-renderered file going missing a key chunk of structure, not to
resist a determined obfuscator. Reviewer attention is the actual
defence; this lint is there so an obvious omission stops merge.

CLI:

    python -m grover_tax.check_results_md             # checks RESULTS.md at the repo root
    python -m grover_tax.check_results_md path/to/RESULTS.md

Exit codes:

    0 — every required section and phrase is present.
    6 — `REPORT.SCHEMA_INVALID`: one or more required substrings missing.
    2 — usage error.

The lint runs in CI on every PR touching `analyze.py` or the template;
failure blocks merge.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from grover_tax.errors import REPORT_EXIT_CODE, ReportSubcode

__all__ = [
    "REQUIRED_PHRASES",
    "REQUIRED_SECTIONS",
    "lint",
    "main",
]


# RFC-0011 §"Methodology lints (CI)": the eight section headers required
# in every `RESULTS.md` regardless of values.
REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "## Headline",
    "## Distributions",
    "## Stability",
    "## Apples-to-apples disclosures",
    "## Discards",
    "## Reproduction",
    "## Run metadata",
    "## Underlying numbers",
)

# RFC-0011 §"Methodology lints (CI)": the seven disclosure phrases that
# must appear somewhere in the document. Each one corresponds to a
# disclosure clause that a reader needs in order to understand the
# headline number.
REQUIRED_PHRASES: Final[tuple[str, ...]] = (
    "SHA-256",
    "Blake2s",
    "BabyBear",
    "M31",
    "Trusted setup",
    "taskpolicy",
    "RAYON_NUM_THREADS",
)


def lint(text: str) -> list[str]:
    """Return a list of missing substrings; empty list means the document is clean."""
    missing: list[str] = []
    missing.extend(s for s in REQUIRED_SECTIONS if s not in text)
    missing.extend(p for p in REQUIRED_PHRASES if p not in text)
    return missing


def _format_missing(missing: Iterable[str]) -> str:
    return "\n".join(f"  - missing: {m!r}" for m in missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_results_md",
        description="Lint RESULTS.md against the RFC-0011 methodology checklist.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        type=Path,
        help="Path to RESULTS.md (default: ./RESULTS.md at the repo root).",
    )
    args = parser.parse_args(argv)

    target = args.path if args.path is not None else Path.cwd() / "RESULTS.md"

    if not target.is_file():
        print(
            f"{ReportSubcode.MISSING_ARTIFACT.value}: file not found: {target}",
            file=sys.stderr,
        )
        return REPORT_EXIT_CODE

    text = target.read_text(encoding="utf-8")
    missing = lint(text)
    if missing:
        print(
            f"{ReportSubcode.SCHEMA_INVALID.value}: {len(missing)} required substring(s) "
            f"missing from {target}:",
            file=sys.stderr,
        )
        print(_format_missing(missing), file=sys.stderr)
        return REPORT_EXIT_CODE
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
