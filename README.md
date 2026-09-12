# meshcorectl

> **This is an AI-generated application.** The design, code, tests, and documentation in this
> repository were produced by an AI coding agent (Claude), directed and reviewed by a human
> maintainer.

A non-interactive, kubectl-style CLI for MeshCore companion radios:
`meshcorectl VERB [TYPE] [NAME] [flags]`, named connection contexts (BLE/serial/TCP), and
`-o table|json|yaml|wide|name` output on every read command.

## Install

```bash
pip install meshcorectl
```

For a development checkout instead, see [Development](#development) below.

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

Every command has real `--help` text;
[docs/command-reference.md](https://github.com/Faradome/meshcorectl/blob/main/docs/command-reference.md)
is the same text generated into one file. Nothing here is interactive — no REPL, no prompts on the
happy path (an exception: `login` without `--password`/`--password-stdin` prompts securely for
one, the same as `ssh` or `git`) — every command is a single invocation that connects, does one
thing, and exits, which is what makes it scriptable.

## Status

Every command in this README is implemented and tested. A background-agent daemon for
low-latency repeated invocations (`meshcored`) is planned but not yet built.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest                # 100% line+branch coverage enforced
ruff check .
mypy
```

After adding or changing a command, regenerate the reference doc:

```bash
python3 scripts/generate_command_reference.py
```

A test (`tests/unit/test_command_reference.py`) fails if it's out of date.

## License

[MIT](https://github.com/Faradome/meshcorectl/blob/main/LICENSE)
