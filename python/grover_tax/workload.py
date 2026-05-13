"""Parser for `WORKLOAD.md`.

`WORKLOAD.md` is the frozen contract that ties `grover-tax` to upstream
`tanujkhattar/zkp_ecc` at a specific commit (RFC-0001). This module reads it,
detects the `TBD` sentinel, validates the `upstream_commit` is a 40-character
lowercase hex SHA, and exposes a typed `Workload` dataclass.

The on-disk format is a YAML-ish frontmatter block followed by a Markdown
table; full schema in `docs/rfcs/RFC-0001-workload-pinning.md`
§"`WORKLOAD.md` schema". This parser accepts that exact shape and rejects
others rather than trying to be permissive — a permissive parser would
silently absorb hand edits that change the workload pin.

Raises `FixtureError("FIXTURE.WORKLOAD_NOT_PINNED")` on the first `TBD`
sighting or a malformed `upstream_commit`. The matching CLI gate is
`scripts/check_workload.sh`; both must agree on what "pinned" means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from grover_tax.errors import FixtureError, FixtureSubcode

__all__ = ["Workload", "WorkloadField", "load_workload_md"]

_FRONTMATTER_DELIM = "---"
_TBD_TOKEN_RE = re.compile(r"\bTBD\b")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|\s*-{3,}\s*\|")
_REQUIRED_FRONTMATTER_KEYS = (
    "upstream_repo",
    "upstream_commit",
    "pinned_at",
    "pinned_by",
    "fixture_target_version",
)

# `WORKLOAD.md`'s six-row table has exactly four columns: Field, Source,
# Value, Notes. These constants name the dimensions so the parser doesn't
# carry bare magic numbers.
_TABLE_COLUMNS = 4
_TABLE_ROWS = 6


@dataclass(frozen=True)
class WorkloadField:
    """One row of the `WORKLOAD.md` six-field table."""

    name: str
    source: str
    value: str
    notes: str


@dataclass(frozen=True)
class Workload:
    """Parsed `WORKLOAD.md` contents.

    Frontmatter keys land as named attributes; the table is exposed both as
    an ordered tuple (`fields`) and as a name → row mapping (`by_name`) so
    downstream consumers can address rows by their stable left-column key.
    """

    upstream_repo: str
    upstream_commit: str
    pinned_at: str
    pinned_by: str
    fixture_target_version: str
    fields: tuple[WorkloadField, ...]

    @property
    def by_name(self) -> dict[str, WorkloadField]:
        """Map each table row's left-column `name` to its row."""
        return {field.name: field for field in self.fields}


def load_workload_md(path: str | Path) -> Workload:
    """Read and validate `WORKLOAD.md` at `path`.

    Validation order:

    1. The file exists.
    2. The whole file contains no `TBD` word-boundary tokens.
    3. The frontmatter block is present, well-formed, and carries every
       required key from `_REQUIRED_FRONTMATTER_KEYS`.
    4. `upstream_commit` is a 40-character lowercase hex SHA.
    5. The six-row table follows the frontmatter and parses cleanly.

    Raises:
        FixtureError(FIXTURE.WORKLOAD_NOT_PINNED): on any `TBD`, malformed
            SHA, missing frontmatter key, or malformed table structure.
        FileNotFoundError: if `path` does not exist.
    """
    text = Path(path).read_text(encoding="utf-8")

    # Step 2: TBD sentinel is the cheapest reject path; do it first so a
    # half-filled file fails fast with the agreed error.
    if _TBD_TOKEN_RE.search(text):
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"{path} still contains TBD",
        )

    frontmatter, body = _split_frontmatter(text, path)
    _assert_required_keys(frontmatter, path)

    upstream_commit = frontmatter["upstream_commit"]
    if not _SHA_RE.match(upstream_commit):
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"upstream_commit malformed (want 40-char lowercase hex SHA, got {upstream_commit!r})",
        )

    fields = _parse_table(body, path)

    return Workload(
        upstream_repo=frontmatter["upstream_repo"],
        upstream_commit=upstream_commit,
        pinned_at=frontmatter["pinned_at"],
        pinned_by=frontmatter["pinned_by"],
        fixture_target_version=frontmatter["fixture_target_version"],
        fields=fields,
    )


def _split_frontmatter(text: str, path: str | Path) -> tuple[dict[str, str], str]:
    """Split `text` into (frontmatter_dict, body) at the leading `---` block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"{path} has no leading `---` frontmatter delimiter",
        )

    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            end_idx = i
            break
    if end_idx is None:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"{path} has no closing `---` frontmatter delimiter",
        )

    frontmatter: dict[str, str] = {}
    for raw in lines[1:end_idx]:
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            raise FixtureError(
                FixtureSubcode.WORKLOAD_NOT_PINNED,
                f"{path}: frontmatter line missing `:` separator: {raw!r}",
            )
        key, _, value = line.partition(":")
        frontmatter[key.strip()] = value.strip()

    body = "\n".join(lines[end_idx + 1 :])
    return frontmatter, body


def _assert_required_keys(frontmatter: dict[str, str], path: str | Path) -> None:
    missing = [k for k in _REQUIRED_FRONTMATTER_KEYS if k not in frontmatter]
    if missing:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"{path}: frontmatter missing keys {missing}",
        )


def _parse_table(body: str, path: str | Path) -> tuple[WorkloadField, ...]:
    """Parse the Markdown table after the frontmatter.

    Accepts the exact shape RFC-0001 §"`WORKLOAD.md` schema" defines: four
    columns (Field, Source location, Value, Notes), a `---|---|---|---`
    divider, then exactly six data rows. Any deviation raises
    `FIXTURE.WORKLOAD_NOT_PINNED`.
    """
    lines = body.splitlines()
    header_idx: int | None = None
    for i, raw in enumerate(lines):
        if _TABLE_DIVIDER_RE.match(raw):
            header_idx = i
            break

    if header_idx is None or header_idx == 0:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"{path}: workload table not found",
        )

    rows: list[WorkloadField] = []
    for raw in lines[header_idx + 1 :]:
        cells = _split_table_row(raw)
        if cells is None:
            # First non-table line ends the table.
            break
        if len(cells) != _TABLE_COLUMNS:
            raise FixtureError(
                FixtureSubcode.WORKLOAD_NOT_PINNED,
                f"{path}: workload table row has {len(cells)} cells, "
                f"want {_TABLE_COLUMNS}: {raw!r}",
            )
        rows.append(
            WorkloadField(name=cells[0], source=cells[1], value=cells[2], notes=cells[3])
        )

    if len(rows) != _TABLE_ROWS:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"{path}: workload table has {len(rows)} rows, want {_TABLE_ROWS}",
        )

    return tuple(rows)


def _split_table_row(raw: str) -> list[str] | None:
    """Split a `| a | b | c | d |` row into its cells.

    Returns `None` if `raw` is not a pipe-delimited table row.
    """
    stripped = raw.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    # Drop the leading and trailing pipes, then split.
    inner = stripped[1:-1]
    return [cell.strip() for cell in inner.split("|")]
