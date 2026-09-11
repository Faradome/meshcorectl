"""`meshcorectl config` — manage named connection contexts.

Deliberately mirrors `kubectl config`: `get-contexts`, `current-context`,
`use-context`, `set-context`, `delete-context`, `view`.
"""

from __future__ import annotations

import json

import click
import yaml

from ..context_store import ConnectionSpec, ContextNotFoundError
from ..output import OutputFormat
from ..output.table import format_table


@click.group(name="config")
def config_group() -> None:
    """Manage connection contexts (BLE/serial/TCP device profiles)."""


@config_group.command("get-contexts")
@click.pass_obj
def get_contexts(state) -> None:
    """List all configured contexts."""
    cfg = state.store.load()
    if not cfg.contexts:
        click.echo(
            "No contexts defined. Create one with 'meshcorectl config set-context'.", err=True
        )
        return
    rows = [
        {
            "current": "*" if name == cfg.current_context else "",
            "name": name,
            "connection": context.connection.summary(),
            "timeout": context.timeout if context.timeout is not None else "",
        }
        for name, context in sorted(cfg.contexts.items())
    ]
    click.echo(
        format_table(
            rows,
            [
                ("CURRENT", "current"),
                ("NAME", "name"),
                ("CONNECTION", "connection"),
                ("TIMEOUT", "timeout"),
            ],
        )
    )


@config_group.command("current-context")
@click.pass_obj
def current_context(state) -> None:
    """Print the name of the current context."""
    cfg = state.store.load()
    if not cfg.current_context:
        raise click.ClickException("current-context is not set")
    click.echo(cfg.current_context)


@config_group.command("use-context")
@click.argument("name")
@click.pass_obj
def use_context(state, name: str) -> None:
    """Set the current context to NAME."""
    try:
        state.store.use_context(name)
    except ContextNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f'switched to context "{name}"')


@config_group.command("set-context")
@click.argument("name")
@click.option(
    "--ble-address", default=None, metavar="ADDR", help="BLE MAC address (or UUID on macOS)."
)
@click.option(
    "--ble-name",
    "ble_name_filter",
    default=None,
    metavar="SUBSTRING",
    help="Match a substring of the device's advertised BLE name, when the address isn't known.",
)
@click.option(
    "--serial-port", default=None, metavar="PATH", help="Serial device, e.g. /dev/ttyUSB0."
)
@click.option("--serial-baudrate", default=115200, show_default=True, type=int)
@click.option(
    "--tcp-host", default=None, metavar="HOST", help="Hostname/IP of a TCP-exposed radio."
)
@click.option("--tcp-port", default=5000, show_default=True, type=int)
@click.option(
    "--timeout",
    "context_timeout",
    type=float,
    default=None,
    metavar="SECONDS",
    help="Default per-command timeout for this context.",
)
@click.option(
    "--current/--no-current",
    "set_current",
    default=False,
    help="Also make this the current context (the first context you create always becomes "
    "current).",
)
@click.pass_obj
def set_context(
    state,
    name: str,
    ble_address: str | None,
    ble_name_filter: str | None,
    serial_port: str | None,
    serial_baudrate: int,
    tcp_host: str | None,
    tcp_port: int,
    context_timeout: float | None,
    set_current: bool,
) -> None:
    """Create or update a connection context named NAME."""
    kinds_given = {
        "ble": ble_address is not None or ble_name_filter is not None,
        "serial": serial_port is not None,
        "tcp": tcp_host is not None,
    }
    selected = [kind for kind, given in kinds_given.items() if given]
    if len(selected) > 1:
        raise click.ClickException(
            f"conflicting connection flags for: {', '.join(selected)} "
            "(a context can only use one of --ble-*, --serial-*, or --tcp-*)"
        )
    if not selected:
        raise click.ClickException(
            "no connection specified: pass --ble-address/--ble-name, --serial-port, or --tcp-host"
        )

    kind = selected[0]
    if kind == "ble":
        connection = ConnectionSpec(kind="ble", address=ble_address, name_filter=ble_name_filter)
    elif kind == "serial":
        connection = ConnectionSpec(kind="serial", port=serial_port, baudrate=serial_baudrate)
    else:
        connection = ConnectionSpec(kind="tcp", host=tcp_host, tcp_port=tcp_port)

    state.store.set_context(
        name, connection=connection, timeout=context_timeout, set_current=set_current
    )
    now_current = set_current or state.store.load().current_context == name
    click.echo(f'context "{name}" set.' + (" (current)" if now_current else ""))


@config_group.command("delete-context")
@click.argument("name")
@click.pass_obj
def delete_context(state, name: str) -> None:
    """Delete context NAME."""
    try:
        was_current = state.store.delete_context(name)
    except ContextNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f'context "{name}" deleted.')
    if was_current:
        click.echo(
            "note: that was the current context; set a new one with "
            "'meshcorectl config use-context'.",
            err=True,
        )


@config_group.command("view")
@click.pass_obj
def view(state) -> None:
    """Print the full contents of the config file."""
    cfg = state.store.load()
    if state.output is OutputFormat.JSON:
        click.echo(json.dumps(cfg.to_dict(), indent=2))
    else:
        click.echo(yaml.safe_dump(cfg.to_dict(), sort_keys=False), nl=False)
