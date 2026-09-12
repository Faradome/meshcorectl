"""`meshcorectl create` -- import a contact card, or define a channel."""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import create_channel, import_contact
from ..output import output_option, render, render_result, resolve_output


@click.group(name="create")
def create_group() -> None:
    """Create a resource: import a contact, or define a channel."""


@create_group.command("contact")
@click.option("--uri", required=True, metavar="URI", help="A meshcore:// contact card URI.")
@click.option("--dry-run", is_flag=True, help="Show what would be imported without doing it.")
@output_option
@click.pass_obj
def create_contact(state: Any, uri: str, dry_run: bool, output_override: str | None) -> None:
    """Import a contact from its meshcore:// card URI."""
    if dry_run:
        click.echo(f"would import contact from {uri} (dry run)")
        return
    state.call(lambda conn: import_contact(conn, uri))
    result = {"imported": True, "uri": uri}
    fmt = resolve_output(state.output, output_override)
    click.echo(render_result(result, fmt, f"contact imported from {uri}"))


@create_group.command("channel")
@click.argument("index", type=int)
@click.argument("name")
@click.argument("key", required=False, metavar="[KEY]")
@click.option("--dry-run", is_flag=True, help="Show what would be created without doing it.")
@output_option
@click.pass_obj
def create_channel_command(
    state: Any, index: int, name: str, key: str | None, dry_run: bool, output_override: str | None
) -> None:
    """Define channel INDEX with NAME and optional 32-hex-char KEY.

    When KEY is omitted, the device derives it from NAME (only works when
    NAME starts with '#').
    """
    if dry_run:
        click.echo(f"would create channel {index} named {name!r} (dry run)")
        return

    async def run(connection: MeshCoreConnection) -> dict[str, Any]:
        return await create_channel(connection, index, name, key)

    channel = state.call(run)
    click.echo(render(channel, resolve_output(state.output, output_override), kind="channel"))
