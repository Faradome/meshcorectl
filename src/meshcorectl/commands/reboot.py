"""`meshcorectl reboot` -- reboot the connected device.

No interactive y/n confirmation (PLAN.md §6 drops those): `--yes` is a
required flag instead, the same non-interactive-but-still-safe pattern as
`terraform apply -auto-approve` or `helm uninstall --no-hooks`.
"""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import reboot_device
from ..output import render_result


@click.command(name="reboot")
@click.option(
    "--yes",
    is_flag=True,
    help="Confirm the reboot; required, since there is no interactive prompt.",
)
@click.option("--dry-run", is_flag=True, help="Show what would happen without rebooting.")
@click.pass_obj
def reboot_command(state: Any, yes: bool, dry_run: bool) -> None:
    """Reboot the connected device."""
    if dry_run:
        click.echo("would reboot the device (dry run)")
        return
    if not yes:
        raise click.ClickException("pass --yes to confirm rebooting the device")

    async def run(connection: MeshCoreConnection) -> None:
        await reboot_device(connection)

    state.call(run)
    click.echo(render_result({"rebooted": True}, state.output, "reboot requested"))
