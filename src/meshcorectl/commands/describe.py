"""`meshcorectl describe` -- verbose, human-only detail views.

Mirrors a deliberate `kubectl describe` quirk: unlike `get`, `describe`
ignores `-o`/`--output` entirely and always prints the same labeled,
multi-line text -- there's no JSON/YAML "describe" shape, only a human one.
For machine-readable output use `get ... -o json`/`-o yaml` instead.
"""

from __future__ import annotations

import datetime
from typing import Any

import click

from ..mesh_data import AmbiguousMatchError, fetch_contacts, fetch_device, find_contact


@click.group(name="describe")
def describe_group() -> None:
    """Show a detailed, human-readable view of one resource."""


@describe_group.command("device")
@click.pass_obj
def describe_device(state: Any) -> None:
    """Describe the connected device."""
    device = state.call(fetch_device)
    click.echo(_describe_device_text(device))


@describe_group.command("contact")
@click.argument("name")
@click.pass_obj
def describe_contact(state: Any, name: str) -> None:
    """Describe one contact by name or public-key prefix."""
    contacts = state.call(fetch_contacts)
    try:
        contact = find_contact(contacts, name)
    except AmbiguousMatchError as exc:
        raise click.ClickException(str(exc)) from exc
    if contact is None:
        raise click.ClickException(f"no contact matching {name!r}")
    click.echo(_describe_contact_text(contact))


def _dash(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def _format_epoch(epoch: Any) -> str:
    if not epoch:
        return "-"
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _describe_device_text(device: dict[str, Any]) -> str:
    lines = [
        f"Name:          {_dash(device.get('name'))}",
        f"Model:         {_dash(device.get('model'))}",
        f"Firmware:      {_dash(device.get('ver'))} (protocol {_dash(device.get('fw ver'))})",
        f"Build:         {_dash(device.get('fw_build'))}",
        f"Public Key:    {_dash(device.get('public_key'))}",
        "Radio:         "
        f"{_dash(device.get('radio_freq'))}MHz  bw={_dash(device.get('radio_bw'))}  "
        f"sf={_dash(device.get('radio_sf'))}  cr={_dash(device.get('radio_cr'))}",
        f"Location:      {_dash(device.get('adv_lat'))}, {_dash(device.get('adv_lon'))}",
        f"Max Contacts:  {_dash(device.get('max_contacts'))}",
        f"Max Channels:  {_dash(device.get('max_channels'))}",
        f"Repeater Mode: {'yes' if device.get('repeat') else 'no'}",
    ]
    return "\n".join(lines)


def _describe_contact_text(contact: dict[str, Any]) -> str:
    lines = [
        f"Name:         {_dash(contact.get('name'))}",
        f"Type:         {_dash(contact.get('type'))}",
        f"Public Key:   {_dash(contact.get('public_key'))}",
        f"Path:         {_dash(contact.get('path'))}",
        f"Last Advert:  {_format_epoch(contact.get('last_advert'))}",
        f"Last Update:  {_format_epoch(contact.get('lastmod'))}",
        f"Flags:        {_dash(contact.get('flags'))}",
        f"Location:     {_dash(contact.get('adv_lat'))}, {_dash(contact.get('adv_lon'))}",
    ]
    return "\n".join(lines)
