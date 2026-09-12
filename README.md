# meshcorectl

A ground-up, non-interactive rewrite of
[meshcore-cli](https://github.com/meshcore-dev/meshcore-cli), modeled on `kubectl`'s
command/argument structure instead of that tool's REPL-and-argument-chain style:
`meshcorectl VERB [TYPE] [NAME] [flags]`, named connection contexts instead of a single cached
device address, and `-o table|json|yaml|wide|name` output on every read command.

Coming from `meshcli`/`meshcore-cli`? See [docs/migration-from-meshcli.md](docs/migration-from-meshcli.md).
For the full design rationale behind every choice below, see [PLAN.md](PLAN.md).

## Install

```bash
pip install -e ".[dev]"    # from a checkout, until this is published
```

## Quickstart

```bash
# Point a named context at your device (BLE, serial, or TCP)
meshcorectl config set-context home --ble-address AA:BB:CC:DD:EE:FF
meshcorectl config use-context home

# Read
meshcorectl get contacts
meshcorectl get contact alice -o yaml
meshcorectl describe device
meshcorectl logs -f

# Write
meshcorectl send message alice "hello"
meshcorectl create channel 1 "#general"
meshcorectl delete contact -l 't=client,u>30d'   # -l selectors batch across matches

# Shell completion
source <(meshcorectl completion bash)   # or zsh / fish
```

Every command has real `--help` text; [docs/command-reference.md](docs/command-reference.md) is
the same text generated into one file. Nothing here is interactive — no REPL, no prompts on the
happy path (an exception: `login` without `--password`/`--password-stdin` prompts securely for
one, the same as `ssh` or `git`) — every command is a single invocation that connects, does one
thing, and exits, which is what makes it scriptable.

## Status

Phases 1–4 of [PLAN.md](PLAN.md) are done: connection contexts, the full read path (`get`,
`describe`, `top`, `logs`, `scan`, `version`), the full write path (`create`, `delete`, `send`,
`exec`, `login`/`logout`, `trace`, `advert`, `reboot`, `set device`) with `-l` selectors and
`--dry-run` throughout, shell completion, and this documentation. A background-agent daemon for
low-latency repeated invocations (`meshcored`) is tracked as future work, not required for normal
use — see PLAN.md's Decision 1.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest                # 100% line+branch coverage enforced (see PLAN.md §8)
ruff check .
mypy
```

After adding or changing a command, regenerate the reference doc:

```bash
python3 scripts/generate_command_reference.py
```

A test (`tests/unit/test_command_reference.py`) fails if it's out of date.
