"""`meshcorectl delete` -- remove a contact (by name or -l selector), or
clear a channel slot.

No `pending-contacts` subcommand: "pending" contacts are client-side
bookkeeping accumulated over a session (see `get.py`'s `pending-contacts`,
which watches for a window instead of reading a cache, for the same
reason). A one-shot connection never accumulates anything across
invocations, so there's nothing for `delete pending-contacts` to clear.
"""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import delete_channel, fetch_channels, fetch_contacts, find_channel, find_contact
from ..mesh_data import remove_contact as remove_contact_data
from ..selectors import SelectorError, filter_contacts


@click.group(name="delete")
def delete_group() -> None:
    """Delete a contact, or clear a channel slot."""


@delete_group.command("contact")
@click.argument("name", required=False, metavar="NAME")
@click.option(
    "-l",
    "--selector",
    "selector_text",
    default=None,
    metavar="SELECTOR",
    help="Delete every contact matching this filter instead of one by name, e.g. 't=client,u>30d'.",
)
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting it.")
@click.pass_obj
def delete_contact(state: Any, name: str | None, selector_text: str | None, dry_run: bool) -> None:
    """Delete one contact by NAME, or every contact matching -l/--selector."""
    if (name is None) == (selector_text is None):
        raise click.ClickException("pass exactly one of NAME or -l/--selector")

    async def run(connection: MeshCoreConnection) -> None:
        contacts = await fetch_contacts(connection)
        if name is not None:
            contact = find_contact(contacts, name)
            if contact is None:
                raise click.ClickException(f"no contact matching {name!r}")
            targets = [contact]
        else:
            try:
                targets = filter_contacts(contacts, selector_text)
            except SelectorError as exc:
                raise click.ClickException(str(exc)) from exc
            if not targets:
                click.echo("No contacts matched.", err=True)
                return

        for target in targets:
            if dry_run:
                click.echo(f"contact {target['name']!r} would be deleted (dry run)")
                continue
            await remove_contact_data(connection, target)
            click.echo(f"contact {target['name']!r} deleted")

    state.call(run)


@delete_group.command("channel")
@click.argument("index_or_name", metavar="INDEX_OR_NAME")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting it.")
@click.pass_obj
def delete_channel_command(state: Any, index_or_name: str, dry_run: bool) -> None:
    """Clear channel INDEX_OR_NAME (there's no true delete: the name and
    secret are cleared instead)."""

    async def run(connection: MeshCoreConnection) -> None:
        channels = await fetch_channels(connection)
        channel = find_channel(channels, index_or_name)
        if channel is None:
            raise click.ClickException(f"no channel matching {index_or_name!r}")
        if dry_run:
            click.echo(f"channel {channel['name']!r} would be cleared (dry run)")
            return
        await delete_channel(connection, channel["index"])
        click.echo(f"channel {channel['name']!r} cleared")

    state.call(run)
