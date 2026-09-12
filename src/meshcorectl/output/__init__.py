"""Output-format dispatch: table / wide / json / yaml / name.

Every read command funnels its result through `render()` here instead of
hand-rolling per-command JSON/table logic, so one place governs what
`-o json`, `-o yaml`, `-o wide`, and `-o name` mean across every resource
kind.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any, TypeVar

import click
import yaml

from . import resources as resources
from . import table as table
from .table import format_table as format_table
from .table import lookup as lookup


class OutputFormat(str, Enum):
    TABLE = "table"
    WIDE = "wide"
    JSON = "json"
    YAML = "yaml"
    NAME = "name"

    def __str__(self) -> str:  # nicer in error/help messages than repr
        return self.value


def render(
    data: Mapping[str, Any] | Sequence[Mapping[str, Any]], fmt: OutputFormat, kind: str
) -> str:
    """Render one resource object or a list of them as `fmt`.

    `data` may be a single mapping (e.g. `get device`, `get contact NAME`)
    or a sequence of mappings (e.g. `get contacts`). JSON/YAML preserve
    that shape (one object vs. an array); table/wide/name always operate
    row-wise, so a single object is treated as a one-row table.
    """
    payload: Any
    rows: list[Mapping[str, Any]]
    if isinstance(data, Mapping):
        payload = data
        rows = [data]
    else:
        payload = rows = list(data)

    if fmt is OutputFormat.JSON:
        return json.dumps(payload, indent=2, default=str)

    if fmt is OutputFormat.YAML:
        return yaml.safe_dump(payload, sort_keys=False).rstrip("\n")

    if fmt is OutputFormat.NAME:
        spec = resources.get(kind)
        return "\n".join(str(lookup(row, spec.name_key)) for row in rows)

    spec = resources.get(kind)
    columns = spec.columns + spec.wide_columns if fmt is OutputFormat.WIDE else spec.columns
    return format_table(rows, columns)


def render_result(result: Mapping[str, Any], fmt: OutputFormat, text: str) -> str:
    """For mutating commands with no natural "resource list" shape
    (send/login/advert/...): `-o json`/`-o yaml` render `result`; anything
    else (table/wide/name, the default) is `text` -- a plain confirmation
    line, the same convention `kubectl create`'s "pod/foo created" follows.
    """
    if fmt is OutputFormat.JSON:
        return json.dumps(result, indent=2, default=str)
    if fmt is OutputFormat.YAML:
        return yaml.safe_dump(result, sort_keys=False).rstrip("\n")
    return text


_F = TypeVar("_F", bound=Callable[..., Any])


def output_option(f: _F) -> _F:
    """A per-command `-o/--output` override.

    The global `-o` (on the root group) only takes effect before the
    subcommand (`meshcorectl -o json get device`); Click has no mechanism
    for a parent group's option to apply after a subcommand. This decorator
    adds a local `-o` to the command itself so `get device -o json` also
    works, matching kubectl. `resolve_output()` prefers the local value over
    the global one when both are given.
    """
    return click.option(
        "-o",
        "--output",
        "output_override",
        type=click.Choice([fmt.value for fmt in OutputFormat]),
        default=None,
        metavar="FORMAT",
        help="Output format for this command (table|wide|json|yaml|name); overrides the global -o.",
    )(f)


def resolve_output(state_output: OutputFormat, output_override: str | None) -> OutputFormat:
    """`state_output` is the global `-o` (already resolved by the root
    group); `output_override` is this command's own `-o`, if given."""
    return OutputFormat(output_override) if output_override is not None else state_output
