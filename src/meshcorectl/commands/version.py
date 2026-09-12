"""`meshcorectl version` -- client (this CLI) + device firmware/protocol
version, mirroring `kubectl version`'s Client/Server split.
"""

from __future__ import annotations

import json
from typing import Any

import click
import yaml

from .. import __version__
from ..mesh_data import fetch_device
from ..output import OutputFormat, output_option, resolve_output


@click.command(name="version")
@click.option(
    "--client",
    "client_only",
    is_flag=True,
    help="Only print the client (this CLI's) version; don't connect to a device.",
)
@output_option
@click.pass_obj
def version_command(state: Any, client_only: bool, output_override: str | None) -> None:
    """Print the client version and, unless --client, the device's version."""
    info: dict[str, Any] = {"client_version": __version__}
    if not client_only:
        device = state.call(fetch_device)
        info["device"] = {
            "name": device.get("name"),
            "model": device.get("model"),
            "version": device.get("ver"),
            "protocol": device.get("fw ver"),
            "build": device.get("fw_build"),
        }
    click.echo(format_version(info, resolve_output(state.output, output_override)))


def format_version(info: dict[str, Any], fmt: OutputFormat) -> str:
    if fmt is OutputFormat.JSON:
        return json.dumps(info, indent=2)
    if fmt is OutputFormat.YAML:
        return yaml.safe_dump(info, sort_keys=False).rstrip("\n")

    lines = [f"Client Version: {info['client_version']}"]
    device = info.get("device")
    if device is not None:
        lines.append(f"Device Name:    {device.get('name') or '-'}")
        lines.append(f"Device Model:   {device.get('model') or '-'}")
        lines.append(
            f"Device Version: {device.get('version') or '-'} "
            f"(protocol {device.get('protocol') if device.get('protocol') is not None else '-'})"
        )
        lines.append(f"Device Build:   {device.get('build') or '-'}")
    return "\n".join(lines)
