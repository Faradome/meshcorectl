"""A dependency-free, kubectl-style plain-text table writer.

Real `kubectl get` output is column-aligned plain text with no color and no
box-drawing (it's Go's `text/tabwriter` under the hood), and every column —
including numeric-looking ones like RESTARTS or AGE — is left-justified, not
right-aligned. This module matches that exactly: no ANSI color, alignment
and spacing only (PLAN.md Decision 3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

EMPTY = "-"
COLUMN_GAP = "   "


def lookup(row: Mapping[str, Any], key: str) -> Any:
    """Fetch `key` from `row`, supporting dotted paths (e.g. "battery.percent").

    Returns None if any segment is missing or not a mapping, rather than
    raising — a missing field renders as the empty placeholder, it doesn't
    blow up table formatting.
    """
    value: Any = row
    for segment in key.split("."):
        if not isinstance(value, Mapping) or segment not in value:
            return None
        value = value[segment]
    return value


def _cell(value: Any) -> str:
    if value is None:
        return EMPTY
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value) if value else EMPTY
    text = str(value)
    return text if text != "" else EMPTY


def format_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[tuple[str, str]]) -> str:
    """Render `rows` as an aligned plain-text table.

    `columns` is an ordered list of (HEADER, field_key) pairs; `field_key`
    may be a dotted path (see `lookup`). Returns the block as a single
    string (header + one line per row), joined with newlines and no
    trailing newline — callers `click.echo()` it.
    """
    headers = [header for header, _ in columns]
    body = [[_cell(lookup(row, key)) for _, key in columns] for row in rows]

    widths = [len(header) for header in headers]
    for line in body:
        for i, cell in enumerate(line):
            widths[i] = max(widths[i], len(cell))

    lines = [_format_row(headers, widths)]
    lines.extend(_format_row(line, widths) for line in body)
    return "\n".join(lines)


def _format_row(cells: Sequence[str], widths: Sequence[int]) -> str:
    # Last column is never right-padded, so lines don't carry trailing
    # whitespace (which both looks wrong and breaks tools like `git diff`
    # on any saved output).
    padded = [cell.ljust(width) for cell, width in zip(cells[:-1], widths[:-1], strict=False)]
    padded.append(cells[-1] if cells else "")
    return COLUMN_GAP.join(padded)
