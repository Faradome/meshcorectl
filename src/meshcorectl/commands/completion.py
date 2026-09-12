"""`meshcorectl completion` -- print a shell completion script.

Click already does the hard part (matching commands/options/arguments as
you type); this just exposes it the way `kubectl completion`/`gh
completion` do, as a discoverable subcommand, instead of expecting users to
know Click's own `_MESHCORECTL_COMPLETE=bash_source meshcorectl` env-var
convention.
"""

from __future__ import annotations

import click
from click.shell_completion import get_completion_class

SHELLS = ("bash", "zsh", "fish")


@click.command(name="completion")
@click.argument("shell", type=click.Choice(SHELLS))
@click.pass_context
def completion_command(ctx: click.Context, shell: str) -> None:
    """Print a shell completion script for SHELL.

    \b
    Load it for the current session:
      bash:  source <(meshcorectl completion bash)
      zsh:   source <(meshcorectl completion zsh)
      fish:  meshcorectl completion fish | source

    \b
    Or install it permanently, e.g. for bash:
      meshcorectl completion bash > ~/.local/share/bash-completion/completions/meshcorectl
    """
    completion_class = get_completion_class(shell)
    if completion_class is None:  # pragma: no cover - click.Choice already restricts `shell`
        raise click.ClickException(f"unsupported shell {shell!r}")

    root = ctx.find_root()
    prog_name = root.info_name or "meshcorectl"
    complete_var = f"_{prog_name.upper().replace('-', '_')}_COMPLETE"
    complete = completion_class(root.command, {}, prog_name, complete_var)
    click.echo(complete.source())
