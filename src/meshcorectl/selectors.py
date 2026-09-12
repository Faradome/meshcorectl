"""`-l/--selector` filter grammar -- ported from the original tool's
`apply_to <filter> <cmd>` command (PLAN.md Decision 4), but as a flag
reusable on `get`, `delete`, `send`, `exec`, and `login` instead of its own
bespoke batch-apply verb: `meshcorectl delete contact -l 't=1,u>2d'`.

Grammar: comma-separated clauses, each `field<op>value` (ops: `<`, `>`,
`=`) or a bare flag clause (`d`, `f`):

    t=repeater   contact type is "repeater" (name or the original's numeric
                 code both work: t=2 means the same thing)
    h>2          more than 2 hops away
    u<2d         last updated more than 2 days ago
    u>1h         last updated within the last hour
    d            direct (0 hops) -- same as h=0
    f            flood (unknown path) -- same as h<0

Clauses are ANDed together. Operates on the same normalized contact dicts
`mesh_data.normalize_contact` produces (needs `type`/`hops`/`lastmod`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .durations import parse_duration
from .mesh_data import contact_type_name

_FLAG_FIELDS = frozenset({"d", "f"})
_VALUE_FIELDS = frozenset({"t", "h", "u"})
_OPS = ("<=", ">=", "<", ">", "=")


class SelectorError(ValueError):
    """An invalid `-l` selector string."""


@dataclass(frozen=True)
class Clause:
    field: str
    op: str | None
    value: str | None


def parse_selector(text: str) -> list[Clause]:
    """Parse a comma-separated selector string into `Clause`s.

    Raises `SelectorError` for anything that isn't a recognized field or a
    well-formed `field<op>value` segment.
    """
    clauses: list[Clause] = []
    for raw_segment in text.split(","):
        segment = raw_segment.strip()
        if not segment:
            continue
        if segment in _FLAG_FIELDS:
            clauses.append(Clause(field=segment, op=None, value=None))
            continue
        clauses.append(_parse_value_clause(segment))
    if not clauses:
        raise SelectorError("empty selector")
    return clauses


def _parse_value_clause(segment: str) -> Clause:
    for op in _OPS:
        if op in segment:
            field, _, value = segment.partition(op)
            field = field.strip()
            value = value.strip()
            if field not in _VALUE_FIELDS:
                raise SelectorError(
                    f"unknown selector field {field!r} in {segment!r} "
                    f"(expected one of: {', '.join(sorted(_VALUE_FIELDS | _FLAG_FIELDS))})"
                )
            if not value:
                raise SelectorError(f"missing value in selector clause {segment!r}")
            return Clause(field=field, op=op, value=value)
    raise SelectorError(
        f"invalid selector clause {segment!r}: expected 'field<op>value' (op one of "
        f"{', '.join(_OPS)}), or a bare 'd'/'f' flag"
    )


def matches(contact: dict[str, Any], clauses: list[Clause]) -> bool:
    return all(_matches_one(contact, clause) for clause in clauses)


def _matches_one(contact: dict[str, Any], clause: Clause) -> bool:
    hops = contact.get("hops")
    if clause.field == "d":
        return hops == 0
    if clause.field == "f":
        return hops is None or hops < 0
    if clause.field == "t":
        assert clause.value is not None  # value fields always carry a value
        return contact.get("type") == _normalize_type_value(clause.value)
    if clause.field == "h":
        assert clause.value is not None and clause.op is not None
        return _compare(hops, clause.op, int(clause.value))
    if clause.field == "u":
        assert clause.value is not None and clause.op is not None
        lastmod = contact.get("lastmod")
        return _compare(lastmod, clause.op, _resolve_time_value(clause.value))
    raise SelectorError(f"unknown selector field {clause.field!r}")  # pragma: no cover - defensive


def _normalize_type_value(value: str) -> str:
    if value.isdigit():
        return contact_type_name(int(value))
    return value.lower()


def _compare(actual: float | None, op: str, expected: float) -> bool:
    if actual is None:
        return False
    if op == "<":
        return actual < expected
    if op == ">":
        return actual > expected
    return actual == expected  # op == "="


def _resolve_time_value(value: str) -> float:
    """A bare number is an absolute epoch timestamp; a duration-suffixed
    value ("2d", "1h", "30m") is that long ago, computed against wall-clock
    time at selector-evaluation time."""
    try:
        return time.time() - parse_duration(value)
    except ValueError:
        return float(value)


def filter_contacts(
    contacts: list[dict[str, Any]], selector_text: str | None
) -> list[dict[str, Any]]:
    """Apply an optional `-l` selector to a contact list; `None`/empty
    returns every contact unfiltered."""
    if not selector_text:
        return contacts
    clauses = parse_selector(selector_text)
    return [c for c in contacts if matches(c, clauses)]


__all__ = [
    "Clause",
    "SelectorError",
    "filter_contacts",
    "matches",
    "parse_selector",
]
