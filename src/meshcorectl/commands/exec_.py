"""`meshcorectl exec` -- run a raw console command on a repeater/room and
print its reply, the mesh analogue of `kubectl exec pod -- cmd`.
"""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import fetch_contacts, find_contact
from ..mesh_data import run_repeater_command as run_repeater_command_data
from ..selectors import SelectorError, filter_contacts

DEFAULT_REPLY_TIMEOUT = 8.0


@click.command(name="exec", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[REPEATER] -- CMD...")
@click.option(
    "-l",
    "--selector",
    "selector_text",
    default=None,
    metavar="SELECTOR",
    help="Run on every contact matching this filter instead of one by name.",
)
@click.option(
    "--timeout",
    "reply_timeout",
    type=float,
    default=DEFAULT_REPLY_TIMEOUT,
    show_default=True,
    metavar="SECONDS",
    help="How long to wait for the reply.",
)
@click.option("--dry-run", is_flag=True, help="Show what would run without running it.")
@click.pass_obj
def exec_command(
    state: Any,
    args: tuple[str, ...],
    selector_text: str | None,
    reply_timeout: float,
    dry_run: bool,
) -> None:
    """Run a raw console command on REPEATER (or every -l/--selector match).

    \b
    Usage: meshcorectl exec REPEATER -- CMD...

    REPEATER and CMD are split out of a single catch-all argument (rather
    than two separate Click arguments) on purpose: Click fills fixed
    positionals in declaration order regardless of `required=False`, so an
    optional REPEATER ahead of a variadic CMD would silently steal CMD's
    first word whenever -l/--selector was used instead. `--` is stripped by
    Click itself wherever it appears, so it doesn't show up in `args`.
    """
    tokens = list(args)
    if selector_text is None:
        if not tokens:
            raise click.ClickException("pass exactly one of REPEATER or -l/--selector")
        name: str | None = tokens[0]
        command_tokens = tokens[1:]
    else:
        name = None
        command_tokens = tokens

    if not command_tokens:
        raise click.ClickException("no command given (usage: exec REPEATER -- CMD...)")
    command_text = " ".join(command_tokens)

    async def run(connection: MeshCoreConnection) -> None:
        contacts = await fetch_contacts(connection)
        if name is not None:
            contact = find_contact(contacts, name)
            if contact is None:
                raise click.ClickException(f"no contact matching {name!r}")
            targets = [contact]
        else:
            try:
                targets = filter_contacts(contacts, selector_text)
            except SelectorError as exc:
                raise click.ClickException(str(exc)) from exc
            if not targets:
                click.echo("No contacts matched.", err=True)
                return

        multiple = len(targets) > 1
        for target in targets:
            if dry_run:
                click.echo(f"would run on {target['name']!r}: {command_text!r} (dry run)")
                continue
            reply = await run_repeater_command_data(
                connection, target, command_text, timeout=reply_timeout
            )
            if reply is None:
                click.echo(f"{target['name']}: (no reply within {reply_timeout}s)", err=True)
            elif multiple:
                click.echo(f"{target['name']}: {reply}")
            else:
                click.echo(reply)

    state.call(run)
