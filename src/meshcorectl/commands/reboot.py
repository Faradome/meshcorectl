"""`meshcorectl reboot` -- reboot the connected device.

No interactive y/n prompt: `--yes` is a required flag instead, the same
pattern as `terraform apply -auto-approve`.
"""

from __future__ import annotations

from typing import Any

import click

from ..connect import MeshCoreConnection
from ..mesh_data import reboot_device
from ..output import output_option, render_result, resolve_output


@click.command(name="reboot")
@click.option(
    "--yes",
    is_flag=True,
    help="Confirm the reboot; required, since there is no interactive prompt.",
)
@click.option("--dry-run", is_flag=True, help="Show what would happen without rebooting.")
@output_option
@click.pass_obj
def reboot_command(state: Any, yes: bool, dry_run: bool, output_override: str | None) -> None:
    """Reboot the connected device."""
    if dry_run:
        click.echo("would reboot the device (dry run)")
        return
    if not yes:
        raise click.ClickException("pass --yes to confirm rebooting the device")

    async def run(connection: MeshCoreConnection) -> None:
        await reboot_device(connection)

    state.call(run)
    fmt = resolve_output(state.output, output_override)
    click.echo(render_result({"rebooted": True}, fmt, "reboot requested"))
