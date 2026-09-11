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
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import click

from . import __version__
from .commands.config_cmd import config_group
from .connect import MeshCoreConnection, connect
from .context_store import Context, ContextStore
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


def main() -> None:
    try:
        cli(prog_name="meshcorectl")
    except KeyboardInterrupt:
        click.echo("aborted", err=True)
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover - exercised via the console-script entry point
    main()
