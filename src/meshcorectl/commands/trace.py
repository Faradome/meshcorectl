"""`meshcorectl trace` -- trace the route through specific repeaters."""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import run_trace
from ..output import output_option, render, resolve_output


@click.command(name="trace")
@click.argument("path", metavar="PATH")
@click.option(
    "--timeout",
    "timeout_override",
    type=float,
    default=None,
    metavar="SECONDS",
    help="Override the device-suggested wait for the trace reply.",
)
@output_option
@click.pass_obj
def trace_command(
    state: Any, path: str, timeout_override: float | None, output_override: str | None
) -> None:
    """Trace the route through PATH, a comma-separated list of repeater
    public-key prefixes (e.g. "23,5f,3a")."""

    async def run(connection: MeshCoreConnection) -> list[dict[str, Any]]:
        return await run_trace(connection, path, timeout=timeout_override)

    hops = state.call(run)
    if not hops:
        click.echo("No hops in the trace reply.", err=True)
        return
    click.echo(render(hops, resolve_output(state.output, output_override), kind="trace-hop"))
