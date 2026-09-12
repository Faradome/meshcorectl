"""`meshcorectl set device` -- set a device parameter."""

from __future__ import annotations

import inspect
import textwrap
from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import DEVICE_PARAMS, set_device_param
from ..output import output_option, render_result, resolve_output


@click.group(name="set")
def set_group() -> None:
    """Set a device parameter."""


@set_group.command("device")
@click.argument("param", metavar="PARAM")
@click.argument("value", metavar="VALUE")
@click.option("--dry-run", is_flag=True, help="Show what would be set without setting it.")
@output_option
@click.pass_obj
def set_device_command(
    state: Any, param: str, value: str, dry_run: bool, output_override: str | None
) -> None:
    """Set device parameter PARAM to VALUE.

    \b
    Known parameters: {params}
    """
    if dry_run:
        click.echo(f"would set {param} to {value!r} (dry run)")
        return
    if param not in DEVICE_PARAMS:
        raise click.ClickException(
            f"unknown device parameter {param!r} (expected one of: {', '.join(DEVICE_PARAMS)})"
        )

    async def run(connection: MeshCoreConnection) -> None:
        await set_device_param(connection, param, value)

    state.call(run)
    text = f"{param} set to {value!r}"
    fmt = resolve_output(state.output, output_override)
    click.echo(render_result({"param": param, "value": value}, fmt, text))


def _format_params_help(raw_help: str, params: tuple[str, ...]) -> str:
    """Fill `raw_help`'s `{params}` placeholder with `params`, wrapped to a
    readable width.

    `raw_help` is dedented (`inspect.cleandoc`) *before* substituting, not
    after: Python only auto-dedents docstrings at compile time starting in
    3.13, so on 3.10-3.12 a bare `f.__doc__` still carries its original
    source indentation. Substituting a multi-line, zero-indent wrapped
    value into that indented text and dedenting afterward (which is what
    Click's own `--help` rendering does to `.help`) breaks: the newly
    inserted line has no indentation of its own, which drags the computed
    common indent down to zero and defeats the dedent for every other line.
    Dedenting first avoids the whole problem, on every Python version.
    """
    wrapped = textwrap.fill(", ".join(params), width=76)
    return inspect.cleandoc(raw_help).format(params=wrapped)


# Click captures `help` from the docstring at decoration time, so `{params}`
# is filled in on the Command's `.help` afterward, not the original
# function's `__doc__`.
set_device_command.help = _format_params_help(set_device_command.help or "", DEVICE_PARAMS)
