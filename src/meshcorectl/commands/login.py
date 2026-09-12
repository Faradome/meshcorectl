"""`meshcorectl login`/`logout` -- authenticate to a repeater/room server."""

from __future__ import annotations

import sys
from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import fetch_contacts, find_contact
from ..mesh_data import login as login_data
from ..mesh_data import logout as logout_data
from ..selectors import SelectorError, filter_contacts


def _resolve_password(password: str | None, password_stdin: bool) -> str:
    """Assumes the `--password`/`--password-stdin` mutual exclusion was
    already validated by the caller (see `login_command`) -- checked
    early, before connecting, not buried in here."""
    if password_stdin:
        return sys.stdin.readline().rstrip("\n")
    if password is not None:
        return password
    return click.prompt("Password", hide_input=True)


@click.command(name="login")
@click.argument("name", required=False, metavar="REPEATER")
@click.option(
    "-l",
    "--selector",
    "selector_text",
    default=None,
    metavar="SELECTOR",
    help="Log into every contact matching this filter instead of one by name.",
)
@click.option(
    "--password",
    default=None,
    help="Password (prefer --password-stdin, or the secure prompt, over shell history).",
)
@click.option("--password-stdin", is_flag=True, help="Read the password from stdin.")
@click.option("--dry-run", is_flag=True, help="Show what would run without logging in.")
@click.pass_obj
def login_command(
    state: Any,
    name: str | None,
    selector_text: str | None,
    password: str | None,
    password_stdin: bool,
    dry_run: bool,
) -> None:
    """Log into REPEATER (or room), or every -l/--selector match."""
    if (name is None) == (selector_text is None):
        raise click.ClickException("pass exactly one of REPEATER or -l/--selector")
    if password is not None and password_stdin:
        raise click.ClickException("pass only one of --password or --password-stdin")

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

        if dry_run:
            for target in targets:
                click.echo(f"would log into {target['name']!r} (dry run)")
            return

        secret = _resolve_password(password, password_stdin)
        context = state.resolve_context()
        timeout = state.effective_timeout(context)
        for target in targets:
            success = await login_data(connection, target, secret, timeout=timeout)
            click.echo(f"{target['name']!r}: {'login ok' if success else 'login failed'}")

    state.call(run)


@click.command(name="logout")
@click.argument("name", metavar="REPEATER")
@click.option("--dry-run", is_flag=True, help="Show what would run without logging out.")
@click.pass_obj
def logout_command(state: Any, name: str, dry_run: bool) -> None:
    """Log out of REPEATER (or room)."""

    async def run(connection: MeshCoreConnection) -> None:
        contacts = await fetch_contacts(connection)
        contact = find_contact(contacts, name)
        if contact is None:
            raise click.ClickException(f"no contact matching {name!r}")
        if dry_run:
            click.echo(f"would log out of {contact['name']!r} (dry run)")
            return
        await logout_data(connection, contact)
        click.echo(f"{contact['name']!r}: logged out")

    state.call(run)
