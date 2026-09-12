"""The root Click group: global flags, logging setup, and `CliState`.

Every command module receives `CliState` via `@click.pass_obj` and uses
`state.resolve_context()` / `state.connect()` to reach a device — command
code never touches `ContextStore` or `connect.connect()` directly, which is
what keeps `tests/commands/*` fast: inject a fake `MeshCoreConnection`
instead of calling `state.connect()`.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import click

from . import __version__, resource_specs  # noqa: F401 - import registers resource specs
from .commands.advert import advert_command
from .commands.config_cmd import config_group
from .commands.create import create_group
from .commands.delete import delete_group
from .commands.describe import describe_group
from .commands.exec_ import exec_command
from .commands.get import get_group
from .commands.login import login_command, logout_command
from .commands.logs import logs_command
from .commands.reboot import reboot_command
from .commands.scan import scan_command
from .commands.send import send_group
from .commands.set_ import set_group
from .commands.top import top_group
from .commands.trace import trace_command
from .commands.version import version_command
from .connect import ConnectError, MeshCoreConnection, connect
from .context_store import Context, ContextStore
from .mesh_data import MeshDataError
from .output import OutputFormat

DEFAULT_TIMEOUT = 10.0

_T = TypeVar("_T")


@dataclass
class CliState:
    """Resolved global options + the context store, threaded through every command."""

    store: ContextStore
    context_override: str | None
    output: OutputFormat
    timeout_override: float | None
    verbosity: int

    def resolve_context(self) -> Context:
        """The `Context` a command should use: `--context` override, else
        the store's `current-context`.

        Raises `click.ClickException` (not a raw store exception) since
        this is always called from inside a command and the message is
        meant to reach the user as-is.
        """
        name = self.context_override
        if name is None:
            cfg = self.store.load()
            name = cfg.current_context
        if name is None:
            raise click.ClickException(
                "no context specified: pass --context NAME or run "
                "'meshcorectl config use-context NAME' "
                "(see 'meshcorectl config set-context --help' to create one)"
            )
        try:
            return self.store.get_context(name)
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc

    def effective_timeout(self, context: Context) -> float:
        """Precedence: `--timeout` flag > the context's own timeout > the
        config file's `defaults.timeout` > `DEFAULT_TIMEOUT`."""
        if self.timeout_override is not None:
            return self.timeout_override
        if context.timeout is not None:
            return context.timeout
        configured = self.store.load().defaults.get("timeout")
        return float(configured) if configured is not None else DEFAULT_TIMEOUT

    async def connect(self) -> MeshCoreConnection:
        """Resolve the current context and open a live connection to it."""
        context = self.resolve_context()
        return await connect(
            context.connection,
            timeout=self.effective_timeout(context),
            debug=self.verbosity >= 2,
        )

    def run_async(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Convenience for commands: `state.run_async(state.connect())`."""
        return asyncio.run(coro)

    @asynccontextmanager
    async def connected(self) -> AsyncIterator[MeshCoreConnection]:
        """`async with state.connected() as conn:` -- connect, yield, always
        disconnect, even if the command body raises."""
        connection = await self.connect()
        try:
            yield connection
        finally:
            await connection.disconnect()

    def run_command(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Run `coro` (typically built around `async with state.connected()`),
        translating connection/device failures into the one
        `click.ClickException` every command surfaces -- never a raw
        traceback from `connect.ConnectError`/`mesh_data.MeshDataError`."""
        try:
            return self.run_async(coro)
        except (ConnectError, MeshDataError) as exc:
            raise click.ClickException(str(exc)) from exc

    def call(self, fn: Callable[[MeshCoreConnection], Coroutine[Any, Any, _T]]) -> _T:
        """The one-liner most read/write commands use: connect, call
        `fn(connection)`, disconnect, translate errors -- e.g.
        `state.call(fetch_contacts)`, or `state.call(lambda conn:
        fetch_telemetry(conn, contact))` for a call needing extra args."""

        async def run() -> _T:
            async with self.connected() as connection:
                return await fn(connection)

        return self.run_command(run())


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s", force=True)


@click.group(name="meshcorectl")
@click.option(
    "--context",
    "context_override",
    default=None,
    metavar="NAME",
    help="Connection context to use (overrides the current context).",
)
@click.option(
    "-o",
    "--output",
    "output_str",
    type=click.Choice([f.value for f in OutputFormat]),
    default=OutputFormat.TABLE.value,
    show_default=True,
    help="Output format.",
)
@click.option(
    "--timeout",
    "timeout_override",
    type=float,
    default=None,
    metavar="SECONDS",
    help="Per-command timeout (overrides the context/config default).",
)
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Increase logging verbosity (-v for info, -vv for debug).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    metavar="PATH",
    help="Path to the meshcorectl config file (default: ~/.config/meshcorectl/config.yaml).",
)
@click.version_option(version=__version__, prog_name="meshcorectl")
@click.pass_context
def cli(
    ctx: click.Context,
    context_override: str | None,
    output_str: str,
    timeout_override: float | None,
    verbosity: int,
    config_path: Path | None,
) -> None:
    """meshcorectl: a kubectl-style CLI for MeshCore companion radios."""
    _configure_logging(verbosity)
    ctx.obj = CliState(
        store=ContextStore(config_path),
        context_override=context_override,
        output=OutputFormat(output_str),
        timeout_override=timeout_override,
        verbosity=verbosity,
    )


cli.add_command(config_group)
cli.add_command(get_group)
cli.add_command(describe_group)
cli.add_command(create_group)
cli.add_command(delete_group)
cli.add_command(send_group)
cli.add_command(exec_command)
cli.add_command(login_command)
cli.add_command(logout_command)
cli.add_command(top_group)
cli.add_command(logs_command)
cli.add_command(trace_command)
cli.add_command(advert_command)
cli.add_command(reboot_command)
cli.add_command(set_group)
cli.add_command(scan_command)
cli.add_command(version_command)


def main() -> None:
    try:
        cli(prog_name="meshcorectl")
    except KeyboardInterrupt:
        click.echo("aborted", err=True)
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover - exercised via the console-script entry point
    main()
