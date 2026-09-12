"""`meshcorectl advert` -- send an advertisement packet."""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import send_advert
from ..output import render_result


@click.command(name="advert")
@click.option(
    "--flood", is_flag=True, help="Flood the advert instead of sending a normal (zero-hop) one."
)
@click.option("--dry-run", is_flag=True, help="Show what would be sent without sending it.")
@click.pass_obj
def advert_command(state: Any, flood: bool, dry_run: bool) -> None:
    """Send an advertisement packet announcing this device."""
    if dry_run:
        click.echo(f"would send{' a flood' if flood else ''} advert (dry run)")
        return

    async def run(connection: MeshCoreConnection) -> None:
        await send_advert(connection, flood=flood)

    state.call(run)
    text = "advert sent" + (" (flood)" if flood else "")
    click.echo(render_result({"sent": True, "flood": flood}, state.output, text))
