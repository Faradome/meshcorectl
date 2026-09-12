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
from ..output import OutputFormat, output_option, resolve_output


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
@output_option
@click.pass_obj
def logs_command(
    state: Any,
    follow: bool,
    since_text: str | None,
    raw_rx: bool,
    output_override: str | None,
) -> None:
    """Show messages received by the device."""
    if raw_rx and not follow:
        raise click.ClickException("--rx has no effect without --follow")

    since_seconds: float | None = None
    if since_text is not None:
        try:
            since_seconds = parse_duration(since_text)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

    fmt = resolve_output(state.output, output_override)

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

        def show(raw: dict[str, Any]) -> None:
            timestamp = raw.get("sender_timestamp")
            if cutoff is not None and timestamp is not None and timestamp < cutoff:
                return
            message = normalize_message(raw, contacts=contacts, channels=channels)
            click.echo(format_message_line(message, fmt))

        for raw in await drain_messages(connection):
            show(raw)

        if follow:
            # CONTACT_MSG_RECV/CHANNEL_MSG_RECV are not passively pushed:
            # they only fire as a side effect of an explicit
            # commands.get_msg() call, normally triggered by a
            # MESSAGES_WAITING notification. So subscribe to
            # MESSAGES_WAITING and drain again (via the same
            # drain_messages() used for the initial batch) whenever it fires.
            fetch_task: asyncio.Task[None] | None = None

            async def drain_new_messages() -> None:
                for raw in await drain_messages(connection):
                    show(raw)

            def handle_messages_waiting(_event: Any) -> None:
                nonlocal fetch_task
                if fetch_task is None or fetch_task.done():
                    fetch_task = asyncio.create_task(drain_new_messages())

            connection.subscribe(EventType.MESSAGES_WAITING, handle_messages_waiting)
            await wait_until_interrupted()

    state.call(run)
