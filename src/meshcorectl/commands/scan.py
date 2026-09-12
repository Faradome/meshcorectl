"""`meshcorectl scan` -- non-interactive discovery of BLE/serial candidates.

A plain read-only listing: pick an address/port from the output and pass it
to `meshcorectl config set-context`.
"""

from __future__ import annotations

from typing import Any

import click
import serial.tools.list_ports
from bleak import BleakScanner
from bleak.exc import BleakError

from ..output import output_option, render, resolve_output


@click.command(name="scan")
@click.option("--ble/--no-ble", "include_ble", default=True, help="Include BLE devices.")
@click.option(
    "--serial/--no-serial", "include_serial", default=True, help="Include serial ports."
)
@click.option(
    "--timeout",
    "timeout",
    type=float,
    default=2.0,
    show_default=True,
    metavar="SECONDS",
    help="BLE scan duration.",
)
@output_option
@click.pass_obj
def scan_command(
    state: Any,
    include_ble: bool,
    include_serial: bool,
    timeout: float,
    output_override: str | None,
) -> None:
    """List discoverable BLE and serial candidates."""
    rows = state.run_async(_scan(include_ble, include_serial, timeout))
    if not rows:
        click.echo("No candidates found.", err=True)
        return
    click.echo(render(rows, resolve_output(state.output, output_override), kind="scan-result"))


async def _scan(include_ble: bool, include_serial: bool, timeout: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if include_ble:
        rows.extend(await scan_ble(timeout))
    if include_serial:
        rows.extend(scan_serial())
    return rows


async def scan_ble(timeout: float) -> list[dict[str, Any]]:
    try:
        devices = await BleakScanner.discover(timeout=timeout)
    except BleakError as exc:
        click.echo(f"BLE scan unavailable: {exc}", err=True)
        return []
    return [
        {"kind": "ble", "address": device.address, "name": device.name}
        for device in devices
        if device.name and device.name.startswith("MeshCore-")
    ]


def scan_serial() -> list[dict[str, Any]]:
    return [
        {"kind": "serial", "address": port.device, "name": port.description}
        for port in serial.tools.list_ports.comports()
    ]
