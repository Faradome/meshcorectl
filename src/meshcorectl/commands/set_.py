"""`meshcorectl set device` -- set a device parameter."""

from __future__ import annotations

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


# Click captures `help` from the docstring at decoration time, so the
# `{params}` placeholder is filled in on the resulting Command's `.help`
# afterward, not on the original function's `__doc__` (which no longer
# matters once decorated). textwrap keeps the (`\b`-protected, so
# Click won't re-wrap it) parameter list readable at a normal terminal
# width instead of one very long line.
_params_wrapped = textwrap.fill(", ".join(DEVICE_PARAMS), width=76)
set_device_command.help = (set_device_command.help or "").format(params=_params_wrapped)
