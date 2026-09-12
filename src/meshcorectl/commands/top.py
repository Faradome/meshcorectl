"""`meshcorectl top` -- telemetry, the mesh analogue of `kubectl top node/pod`."""

from __future__ import annotations

import time
from typing import Any

import click

from ..connect import MeshCoreConnection
from ..durations import parse_duration
from ..mesh_data import fetch_contacts, fetch_telemetry, fetch_telemetry_history, find_contact
from ..output import output_option, render, resolve_output


@click.group(name="top")
def top_group() -> None:
    """Show telemetry (instant readings, or --history min/max/avg)."""


@top_group.command("contact")
@click.argument("name")
@click.option(
    "--history",
    is_flag=True,
    help="Show min/max/avg history instead of instant readings.",
)
@click.option(
    "--since",
    "since_text",
    default="1h",
    show_default=True,
    metavar="DURATION",
    help="History window for --history, e.g. 30m, 2h, 1d.",
)
@output_option
@click.pass_obj
def top_contact(
    state: Any, name: str, history: bool, since_text: str, output_override: str | None
) -> None:
    """Request telemetry from a contact (typically a sensor)."""
    start = end = 0
    if history:
        try:
            duration = parse_duration(since_text)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        end = int(time.time())
        start = end - int(duration)

    # Contact resolution and the telemetry fetch share one connection, like
    # send/delete/exec/login.
    async def run(connection: MeshCoreConnection) -> list[dict[str, Any]]:
        contacts = await fetch_contacts(connection)
        contact = find_contact(contacts, name)
        if contact is None:
            raise click.ClickException(f"no contact matching {name!r}")
        if history:
            return await fetch_telemetry_history(connection, contact, start=start, end=end)
        return await fetch_telemetry(connection, contact)

    readings = state.call(run)
    kind = "telemetry-history" if history else "telemetry"

    if not readings:
        click.echo("No telemetry readings.", err=True)
        return
    click.echo(render(readings, resolve_output(state.output, output_override), kind=kind))
