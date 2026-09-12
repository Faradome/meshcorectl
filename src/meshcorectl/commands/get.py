"""`meshcorectl get` -- read resources: device, contacts, channels,
pending-contacts, path, time.
"""

from __future__ import annotations

import asyncio
from typing import Any

import click
from meshcore import EventType

from ..mesh_data import (
    AmbiguousMatchError,
    collect_events,
    fetch_channels,
    fetch_contacts,
    fetch_device,
    fetch_time,
    find_channel,
    find_contact,
    normalize_contact,
)
from ..output import output_option, render, resolve_output
from ..selectors import SelectorError, filter_contacts


@click.group(name="get")
def get_group() -> None:
    """Get one or more resources (device, contacts, channels, ...)."""


@get_group.command("device")
@output_option
@click.pass_obj
def get_device(state: Any, output_override: str | None) -> None:
    """Show the connected device's advertised info and firmware/protocol query."""
    device = state.call(fetch_device)
    click.echo(render(device, resolve_output(state.output, output_override), kind="device"))


@get_group.command("contacts")
@click.option(
    "-l",
    "--selector",
    "selector_text",
    default=None,
    metavar="SELECTOR",
    help="Only list contacts matching this filter, e.g. 't=repeater,u<2d'.",
)
@output_option
@click.pass_obj
def get_contacts(state: Any, selector_text: str | None, output_override: str | None) -> None:
    """List every contact (client/repeater/room/sensor) known to the device."""
    contacts = state.call(fetch_contacts)
    if selector_text is not None:
        # `is not None`, not truthy: an explicitly empty `-l ""` (e.g. an
        # unset shell variable expanding to nothing) must be rejected by
        # filter_contacts as an invalid selector, not silently treated the
        # same as "-l wasn't passed at all" and match everything.
        try:
            contacts = filter_contacts(contacts, selector_text)
        except SelectorError as exc:
            raise click.ClickException(str(exc)) from exc
    if not contacts:
        click.echo("No contacts.", err=True)
        return
    click.echo(render(contacts, resolve_output(state.output, output_override), kind="contact"))


@get_group.command("contact")
@click.argument("name")
@output_option
@click.pass_obj
def get_contact(state: Any, name: str, output_override: str | None) -> None:
    """Show one contact by name or public-key prefix."""
    contacts = state.call(fetch_contacts)
    try:
        contact = find_contact(contacts, name)
    except AmbiguousMatchError as exc:
        raise click.ClickException(str(exc)) from exc
    if contact is None:
        raise click.ClickException(f"no contact matching {name!r}")
    click.echo(render(contact, resolve_output(state.output, output_override), kind="contact"))


@get_group.command("channels")
@click.option(
    "-A",
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Include empty (unconfigured) channel slots.",
)
@output_option
@click.pass_obj
def get_channels(state: Any, show_all: bool, output_override: str | None) -> None:
    """List every configured channel.

    A device reserves a fixed number of channel slots (commonly 40) whether
    or not they're in use; empty slots are hidden by default -- same as
    `send channel`/`delete channel`, which never treat one as a valid
    target. Pass --all to include them too, in every output format.
    """
    channels = state.call(fetch_channels)
    if not show_all:
        channels = [c for c in channels if c["name"]]
    if not channels:
        hint = "No channels configured."
        if not show_all:
            hint += " (pass --all to include empty slots)"
        click.echo(hint, err=True)
        return
    click.echo(render(channels, resolve_output(state.output, output_override), kind="channel"))


@get_group.command("channel")
@click.argument("index_or_name")
@output_option
@click.pass_obj
def get_channel(state: Any, index_or_name: str, output_override: str | None) -> None:
    """Show one channel by index or name."""
    channels = state.call(fetch_channels)
    channel = find_channel(channels, index_or_name)
    if channel is None:
        raise click.ClickException(f"no channel matching {index_or_name!r}")
    click.echo(render(channel, resolve_output(state.output, output_override), kind="channel"))


@get_group.command("pending-contacts")
@output_option
@click.pass_obj
def get_pending_contacts(state: Any, output_override: str | None) -> None:
    """Watch for adverts from not-yet-added contacts, for one timeout window.

    Unlike a long-lived session, a one-shot connection has no pre-existing
    cache of pending adverts to show: this actively listens for the
    current --timeout (or the context/config default) and reports whatever
    arrives in that window. Re-run (or pass a longer --timeout) to catch
    more.
    """

    async def watch(connection: Any) -> list[dict[str, Any]]:
        context = state.resolve_context()
        duration = state.effective_timeout(context)
        return await collect_events(
            connection, EventType.NEW_CONTACT, duration, sleep=asyncio.sleep
        )

    pending = state.call(watch)
    contacts = [normalize_contact(c) for c in pending]
    if not contacts:
        click.echo("No pending contacts seen in this window.", err=True)
        return
    fmt = resolve_output(state.output, output_override)
    click.echo(render(contacts, fmt, kind="pending-contact"))


@get_group.command("path")
@click.argument("name")
@output_option
@click.pass_obj
def get_path(state: Any, name: str, output_override: str | None) -> None:
    """Show the routing path to a contact (flood, direct, or a hop list)."""
    contacts = state.call(fetch_contacts)
    try:
        contact = find_contact(contacts, name)
    except AmbiguousMatchError as exc:
        raise click.ClickException(str(exc)) from exc
    if contact is None:
        raise click.ClickException(f"no contact matching {name!r}")
    result = {"name": contact["name"], "path": contact["path"]}
    click.echo(render(result, resolve_output(state.output, output_override), kind="path"))


@get_group.command("time")
@output_option
@click.pass_obj
def get_time(state: Any, output_override: str | None) -> None:
    """Show the device's current clock."""
    result = state.call(fetch_time)
    click.echo(render(result, resolve_output(state.output, output_override), kind="time"))
