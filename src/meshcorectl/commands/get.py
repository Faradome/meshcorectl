"""`meshcorectl get` -- read resources: device, contacts, channels,
pending-contacts, path, time.
"""

from __future__ import annotations

import asyncio
from typing import Any

import click
from meshcore import EventType

from ..mesh_data import (
    collect_events,
    fetch_channels,
    fetch_contacts,
    fetch_device,
    fetch_time,
    find_contact,
    normalize_contact,
)
from ..output import render


@click.group(name="get")
def get_group() -> None:
    """Get one or more resources (device, contacts, channels, ...)."""


@get_group.command("device")
@click.pass_obj
def get_device(state: Any) -> None:
    """Show the connected device's advertised info and firmware/protocol query."""
    device = state.call(fetch_device)
    click.echo(render(device, state.output, kind="device"))


@get_group.command("contacts")
@click.pass_obj
def get_contacts(state: Any) -> None:
    """List every contact (client/repeater/room/sensor) known to the device."""
    contacts = state.call(fetch_contacts)
    if not contacts:
        click.echo("No contacts.", err=True)
        return
    click.echo(render(contacts, state.output, kind="contact"))


@get_group.command("contact")
@click.argument("name")
@click.pass_obj
def get_contact(state: Any, name: str) -> None:
    """Show one contact by name or public-key prefix."""
    contacts = state.call(fetch_contacts)
    contact = find_contact(contacts, name)
    if contact is None:
        raise click.ClickException(f"no contact matching {name!r}")
    click.echo(render(contact, state.output, kind="contact"))


@get_group.command("channels")
@click.pass_obj
def get_channels(state: Any) -> None:
    """List every configured channel."""
    channels = state.call(fetch_channels)
    if not channels:
        click.echo("No channels configured.", err=True)
        return
    click.echo(render(channels, state.output, kind="channel"))


@get_group.command("channel")
@click.argument("index_or_name")
@click.pass_obj
def get_channel(state: Any, index_or_name: str) -> None:
    """Show one channel by index or name."""
    channels = state.call(fetch_channels)
    channel = find_channel(channels, index_or_name)
    if channel is None:
        raise click.ClickException(f"no channel matching {index_or_name!r}")
    click.echo(render(channel, state.output, kind="channel"))


def find_channel(channels: list[dict[str, Any]], index_or_name: str) -> dict[str, Any] | None:
    if index_or_name.isdigit():
        index = int(index_or_name)
        return next((c for c in channels if c["index"] == index), None)
    needle = index_or_name.lower()
    return next((c for c in channels if c["name"].lower() == needle), None)


@get_group.command("pending-contacts")
@click.pass_obj
def get_pending_contacts(state: Any) -> None:
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
    click.echo(render(contacts, state.output, kind="pending-contact"))


@get_group.command("path")
@click.argument("name")
@click.pass_obj
def get_path(state: Any, name: str) -> None:
    """Show the routing path to a contact (flood, direct, or a hop list)."""
    contacts = state.call(fetch_contacts)
    contact = find_contact(contacts, name)
    if contact is None:
        raise click.ClickException(f"no contact matching {name!r}")
    result = {"name": contact["name"], "path": contact["path"]}
    click.echo(render(result, state.output, kind="path"))


@get_group.command("time")
@click.pass_obj
def get_time(state: Any) -> None:
    """Show the device's current clock."""
    result = state.call(fetch_time)
    click.echo(render(result, state.output, kind="time"))
