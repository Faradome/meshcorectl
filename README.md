# meshcorectl

A ground-up, non-interactive rewrite of
[meshcore-cli](https://github.com/meshcore-dev/meshcore-cli), modeled on `kubectl`'s
command/argument structure: `meshcorectl VERB [TYPE] [NAME] [flags]`, named connection
contexts instead of a single cached device address, and `-o table|json|yaml|name` output on
every read command.

See [PLAN.md](PLAN.md) for the full design plan and rationale. This is currently **Phase 1**
(scaffolding): connection contexts (`meshcorectl config ...`) and the output layer exist;
resource commands (`get`, `describe`, `send`, ...) land in later phases.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
