"""`meshcorectl top` -- telemetry, the mesh analogue of `kubectl top node/pod`."""

from __future__ import annotations

import time
from typing import Any

import click

from ..connect import MeshCoreConnection
from ..durations import parse_duration
from ..mesh_data import fetch_contacts, fetch_telemetry, fetch_telemetry_history, find_contact
from ..output import render


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
@click.pass_obj
def top_contact(state: Any, name: str, history: bool, since_text: str) -> None:
    """Request telemetry from a contact (typically a sensor)."""
    contacts = state.call(fetch_contacts)
    contact = find_contact(contacts, name)
    if contact is None:
        raise click.ClickException(f"no contact matching {name!r}")

    if history:
        try:
            duration = parse_duration(since_text)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        end = int(time.time())
        start = end - int(duration)

        async def fetch_history(connection: MeshCoreConnection) -> list[dict[str, Any]]:
            return await fetch_telemetry_history(connection, contact, start=start, end=end)

        readings = state.call(fetch_history)
        kind = "telemetry-history"
    else:

        async def fetch_instant(connection: MeshCoreConnection) -> list[dict[str, Any]]:
            return await fetch_telemetry(connection, contact)

        readings = state.call(fetch_instant)
        kind = "telemetry"

    if not readings:
        click.echo("No telemetry readings.", err=True)
        return
    click.echo(render(readings, state.output, kind=kind))
