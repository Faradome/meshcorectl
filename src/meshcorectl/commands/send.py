"""`meshcorectl send` -- send a message to a contact/channel."""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import (
    AmbiguousMatchError,
    fetch_channels,
    fetch_contacts,
    find_channel,
    find_contact,
)
from ..mesh_data import send_channel_message as send_channel_message_data
from ..mesh_data import send_message as send_message_data
from ..selectors import SelectorError, filter_contacts


@click.group(name="send")
def send_group() -> None:
    """Send a message to a contact or a channel."""


@send_group.command("message", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[CONTACT] TEXT")
@click.option(
    "-l",
    "--selector",
    "selector_text",
    default=None,
    metavar="SELECTOR",
    help="Send to every contact matching this filter instead of one by name.",
)
@click.option(
    "--wait-ack",
    is_flag=True,
    help="Wait for delivery confirmation, retrying (and flooding) automatically.",
)
@click.option("--dry-run", is_flag=True, help="Show what would be sent without sending it.")
@click.pass_obj
def send_message(
    state: Any,
    args: tuple[str, ...],
    selector_text: str | None,
    wait_ack: bool,
    dry_run: bool,
) -> None:
    """Send TEXT to CONTACT, or to every contact matching -l/--selector.

    CONTACT and TEXT come out of a single catch-all argument, not two
    separate Click arguments: an optional leading CONTACT ahead of a
    required TEXT has the same Click positional-filling ambiguity `exec`'s
    docstring explains, so it's resolved the same way here. An unquoted
    multi-word message is joined back together with spaces.
    """
    tokens = list(args)
    if selector_text is None:
        if len(tokens) < 2:
            raise click.ClickException(
                "pass CONTACT and TEXT, or -l/--selector and TEXT (see --help)"
            )
        name: str | None = tokens[0]
        text = " ".join(tokens[1:])
    else:
        if not tokens:
            raise click.ClickException(
                "pass CONTACT and TEXT, or -l/--selector and TEXT (see --help)"
            )
        name = None
        text = " ".join(tokens)

    async def run(connection: MeshCoreConnection) -> None:
        contacts = await fetch_contacts(connection)
        if name is not None:
            try:
                contact = find_contact(contacts, name)
            except AmbiguousMatchError as exc:
                raise click.ClickException(str(exc)) from exc
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
                click.echo(f"would send to {target['name']!r}: {text!r} (dry run)")
                continue
            result = await send_message_data(connection, target, text, wait_ack=wait_ack)
            status = "acked" if result.get("acked") else "sent"
            click.echo(f"{status}: {target['name']!r}")

    state.call(run)


@send_group.command("channel")
@click.argument("index_or_name", metavar="CHANNEL")
@click.argument("text")
@click.option("--dry-run", is_flag=True, help="Show what would be sent without sending it.")
@click.pass_obj
def send_channel(state: Any, index_or_name: str, text: str, dry_run: bool) -> None:
    """Send TEXT to CHANNEL (by index or name)."""

    async def run(connection: MeshCoreConnection) -> None:
        channels = await fetch_channels(connection)
        channel = find_channel(channels, index_or_name)
        if channel is None:
            raise click.ClickException(f"no channel matching {index_or_name!r}")
        if dry_run:
            click.echo(f"would send to channel {channel['name']!r}: {text!r} (dry run)")
            return
        await send_channel_message_data(connection, channel, text)
        click.echo(f"sent: {channel['name']!r}")

    state.call(run)
