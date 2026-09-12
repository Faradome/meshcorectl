"""Per-resource-kind column definitions, looked up by `output.render()`.

Resource commands (`get contacts`, `get channels`, ...) register their
column layout here once, at import time, instead of every command
reimplementing table-vs-wide-vs-name logic.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResourceSpec:
    """How one resource kind renders as a table.

    `columns` is used for the default `-o table`; `wide_columns` are
    appended after them for `-o wide` (kubectl's `-o wide` convention).
    `name_key` (a `output.table.lookup`-style dotted path) is what
    `-o name` prints, one per line.
    """

    columns: tuple[tuple[str, str], ...]
    wide_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    name_key: str = "name"


_REGISTRY: dict[str, ResourceSpec] = {}


def register(kind: str, spec: ResourceSpec) -> None:
    """Register (or replace) the table layout for `kind`."""
    _REGISTRY[kind] = spec


def get(kind: str) -> ResourceSpec:
    try:
        return _REGISTRY[kind]
    except KeyError:
        raise KeyError(
            f"no resource spec registered for kind {kind!r} "
            f"(known kinds: {sorted(_REGISTRY) or 'none'})"
        ) from None


def is_registered(kind: str) -> bool:
    return kind in _REGISTRY


def unregister(kind: str) -> None:
    """Remove `kind`'s registration, if any. Mainly useful for test cleanup."""
    _REGISTRY.pop(kind, None)


@contextmanager
def temporary(kind: str, spec: ResourceSpec) -> Iterator[None]:
    """Register `spec` for the duration of a `with` block, then remove it.

    Test-only helper: lets a test exercise `output.render()`'s dispatch
    logic against a synthetic resource kind without leaking that
    registration into other tests.
    """
    previous = _REGISTRY.get(kind)
    register(kind, spec)
    try:
        yield
    finally:
        if previous is None:
            _REGISTRY.pop(kind, None)
        else:
            _REGISTRY[kind] = previous
