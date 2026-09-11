"""`meshcorectl logs` -- messages received by the device, the mesh analogue
of `kubectl logs`.

Like `kubectl logs`, this prints plain lines, not a table: a stream of
messages arriving over time isn't a resource list `get` would show, it's a
log. `-o json`/`-o yaml` still switch the line format for scripting, one
record per line, same as `-o json`'s effect on `kubectl logs --timestamps`
type output in other tools.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import click
import yaml
from meshcore import EventType

from ..connect import MeshCoreConnection
from ..durations import parse_duration
from ..mesh_data import drain_messages, fetch_channels, fetch_contacts, normalize_message
from ..output import OutputFormat


async def wait_until_interrupted() -> None:
    """Blocks until the process is interrupted (Ctrl-C), which `main()`
    already translates into a clean exit. Its own module-level function
    (rather than an inline `await asyncio.Event().wait()`) so tests can
    monkeypatch it to return immediately instead of hanging."""
    await asyncio.Event().wait()


def format_message_line(message: dict[str, Any], fmt: OutputFormat) -> str:
    if fmt is OutputFormat.JSON:
        return json.dumps(message)
    if fmt is OutputFormat.YAML:
        return yaml.safe_dump(message, sort_keys=False).rstrip("\n")
    return f"{message['name']}: {message['text']}"


@click.command(name="logs")
@click.option(
    "-f",
    "--follow",
    is_flag=True,
    help="Keep the connection open and print new messages as they arrive.",
)
@click.option(
    "--since",
    "since_text",
    default=None,
    metavar="DURATION",
    help="Only show already-queued messages newer than this, e.g. 30m, 2h.",
)
@click.option(
    "--rx",
    "raw_rx",
    is_flag=True,
    help="Follow the raw rx-log packet stream instead of messages (requires --follow).",
)
@click.pass_obj
def logs_command(state: Any, follow: bool, since_text: str | None, raw_rx: bool) -> None:
    """Show messages received by the device."""
    if raw_rx and not follow:
        raise click.ClickException("--rx has no effect without --follow")

    since_seconds: float | None = None
    if since_text is not None:
        try:
            since_seconds = parse_duration(since_text)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

    async def run(connection: MeshCoreConnection) -> None:
        if raw_rx:
            connection.subscribe(
                EventType.RX_LOG_DATA,
                lambda event: click.echo(json.dumps(event.payload, default=str)),
            )
            await wait_until_interrupted()
            return

        contacts = await fetch_contacts(connection)
        channels = await fetch_channels(connection)
        cutoff = time.time() - since_seconds if since_seconds is not None else None

        for raw in await drain_messages(connection):
            timestamp = raw.get("sender_timestamp")
            if cutoff is not None and timestamp is not None and timestamp < cutoff:
                continue
            message = normalize_message(raw, contacts=contacts, channels=channels)
            click.echo(format_message_line(message, state.output))

        if follow:

            def handle(event: Any) -> None:
                message = normalize_message(event.payload, contacts=contacts, channels=channels)
                click.echo(format_message_line(message, state.output))

            connection.subscribe(EventType.CONTACT_MSG_RECV, handle)
            connection.subscribe(EventType.CHANNEL_MSG_RECV, handle)
            await wait_until_interrupted()

    state.call(run)
