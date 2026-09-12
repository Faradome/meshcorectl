# meshcorectl — design & architecture

A non-interactive, kubectl-style CLI for MeshCore companion radios. The `meshcore` PyPI package
provides the BLE/serial/TCP transports, frame parsing, an async client with a `commands.*` API,
and an `EventType` pub/sub model; this project implements only the CLI layer on top of it.

## Command tree

```
meshcorectl
├── get           device | contacts [-l] [-A] | contact NAME | channels [-A] | channel N |
│                 pending-contacts | path CONTACT | time
├── describe      device | contact NAME
├── create        contact --uri URI   (import)
│                 channel N NAME [KEY]
├── delete        contact NAME | -l selector
│                 channel N
├── send          message [CONTACT | -l selector] TEXT [--wait-ack]
│                 channel N TEXT
├── exec          [REPEATER | -l selector] -- CLI_CMD  (raw repeater console command)
├── login         [REPEATER | -l selector] [--password | --password-stdin]
├── logout        REPEATER
├── top           contact NAME [--history]        (telemetry / min-max-avg)
├── logs          [-f] [--since DURATION] [--rx]   (message stream)
├── trace         PATH
├── advert        [--flood]
├── reboot        --yes
├── set           device PARAM VALUE               (radio, tx-power, telemetry-mode, …)
├── scan          [--ble] [--serial] [--timeout]    (non-interactive discovery table)
├── config        get-contexts | use-context NAME | set-context NAME [flags] |
│                 current-context | view | delete-context NAME
├── version
└── completion    bash | zsh | fish
```

Every noun gets singular + plural + short form (`contact`/`contacts`/`ct`, `channel`/`channels`/`ch`).
Every command has real `--help` text, generated into [docs/command-reference.md](docs/command-reference.md).

No `delete pending-contacts`: pending contacts are watched for over one `--timeout` window (see
`get pending-contacts`), never persisted, so there is nothing for a delete to ever clear.

## kubectl idioms this CLI borrows

| kubectl idiom | meshcorectl equivalent |
|---|---|
| `kubectl get pods`, `kubectl get pod foo -o yaml` | `meshcorectl get contacts`, `meshcorectl get contact foo -o yaml` |
| `kubectl describe pod foo` | `meshcorectl describe contact foo` (telemetry, path, flags, last-seen, one human view) |
| Resource short names (`po`, `svc`, `deploy`) | `ct` (contact), `ch` (channel), `dev` (device) |
| `-o json\|yaml\|wide\|name` | Same flag, same values, on every read command |
| `-l/--selector key=value` batch targeting | Same flag on `get`, `delete`, `send`, `exec`, `login` (`-l t=2,u<24h`) |
| `kubectl exec pod -- cmd` | `meshcorectl exec repeater-name -- <raw console command>` |
| `kubectl logs [-f] [--since]` | `meshcorectl logs [-f] [--since]` |
| `kubectl top node/pod` | `meshcorectl top contact NAME [--history]` |
| `kubectl config get-contexts/use-context/current-context/view` | `meshcorectl config …` over named connection profiles |
| `kubectl version` | `meshcorectl version` (CLI version + connected device firmware) |
| `kubectl completion bash/zsh/fish` | `meshcorectl completion bash/zsh/fish` |
| `--dry-run` | Same, on every mutating command |
| Non-CRUD standalone verbs (`cordon`, `drain`) | `advert`, `reboot`, `trace`, `login`, `logout` stay top-level, not shoehorned into `get`/`create`/`delete` |

## Design decisions

### One-shot connections; a background daemon is future work

Each invocation opens a connection, acts, and disconnects. Simplest model; fine for interactive
use and for scripts that don't call `meshcorectl` in a tight loop (BLE connect is the slow case,
~1-3s; TCP/serial are fast).

A future `meshcored` background agent would own a persistent BLE/serial/TCP connection and
expose it over a local socket, making `meshcorectl` a thin client — unlocking `get contacts -w`
(watch), instant repeated invocations, and event subscriptions that outlive one command.
`connect.py` is the one seam such a client would replace: every command talks to a small
`MeshCoreConnection` protocol, never to `meshcore.MeshCore` directly, so swapping the connection
method touches no command module. This is also what makes command modules testable against a
fake connection (see Testing, below).

### Click as the CLI framework

Nested `Group`s map directly onto the command tree; a `click.Context` carries the resolved
connection and output formatter down through subcommands; shell completion is close to free.
`click.testing.CliRunner` runs any command in-process with captured stdout/stderr/exit code,
which is what makes full test coverage practical.

### Plain aligned text, no color

Fixed-width columns computed per invocation, consistent left-justification (text and numeric
columns alike, matching kubectl's own tabwriter), `-` placeholders for empty fields. No ANSI
color, no `rich`/`colorama` dependency — a ~50-line internal table writer covers it. JSON via
stdlib `json`; YAML via `pyyaml`.

### `-l/--selector` filtering

A `t=`/`h=`/`u=`/`d`/`f` contact-filter grammar as a `-l/--selector` flag reused across
`get`/`delete`/`send`/`exec`/`login`, rather than a separate batch-apply command:

```
meshcorectl delete contact -l 't=1,u>2d'
meshcorectl login -l 't=2,d' --password-stdin < password.txt
```

Exactly `kubectl delete pods -l app=foo`'s shape: one flag, reused everywhere.

### Binary name: `meshcorectl`

In the `kubectl`/`systemctl`/`<subject>ctl` family.

## Package layout

```
meshcorectl/
├── pyproject.toml
├── src/meshcorectl/
│   ├── cli.py             # root Click group: global --context/-o/--timeout/-v
│   ├── context_store.py   # ~/.config/meshcorectl/config.yaml — named connection contexts
│   ├── connect.py         # resolve context -> meshcore.MeshCore via create_ble/serial/tcp
│   ├── mesh_data.py        # Event/payload -> plain dict translation, no Click
│   ├── selectors.py        # -l filter grammar (parse + match against a contact dict)
│   ├── output/
│   │   ├── __init__.py    # dispatch on -o table|wide|json|yaml|name
│   │   ├── table.py       # dependency-free column writer
│   │   └── resources.py   # per-resource column definitions
│   └── commands/          # one module per verb: get.py, describe.py, create.py, ...
├── tests/
│   ├── fakes/meshcore_double.py  # fake MeshCore/CommandHandler: scripted Event responses
│   ├── unit/               # selectors, table/output formatting, context_store, mesh_data
│   └── commands/           # one test module per commands/*.py, via Click CliRunner + the fake
└── docs/command-reference.md     # generated from --help
```

`connect.py` is the only module that imports `meshcore`'s transport classes; every command
module receives an already-connected client through the Click context, which is what keeps
`tests/commands/` fast and hardware-free.

## Non-interactive by design

No REPL, chat navigation, line-redirection DSL, alias engine, or interactive device picker. A
shell already covers these better: pipe to `jq`, redirect with `>`, use shell aliases/functions.
`scan` prints a plain table of discoverable devices to pick an address from, instead of an
interactive picker.

## Testing strategy

- **A fake connection is the foundation.** `tests/fakes/meshcore_double.py` implements the same
  surface every command module calls (`commands.get_contacts`, `commands.send_msg`, `subscribe`,
  …) and returns scripted `Event`/`EventType` values, including error payloads, timeouts, and
  disconnects. No command module ever touches real BLE/serial/TCP in a test.
- **Every command gets a table-driven CliRunner test**: happy path, the device returning
  `EventType.ERROR`, a not-found argument, and — for mutating commands — `--dry-run` performing
  no `commands.*` call. Selector-aware commands get matrix cases (matches none/one/many).
  Commands that only need one connection assert `connect_call_count == 1`.
- **Pure-logic modules get unit tests with no Click/CLI involvement**: `selectors.py` (grammar
  parsing, comparison operators, relative-time suffixes), `output/table.py` (column widths, empty
  placeholders), `context_store.py` (YAML round-trip, missing/corrupt file, unknown context),
  `mesh_data.py` (Event-to-dict translation for every resource kind).
- **Coverage gate**: `pytest --cov=meshcorectl --cov-report=term-missing --cov-fail-under=90`.
  `connect.py`'s transport-selection calls are the one piece that would need real hardware to
  exercise directly; everything above that seam is covered by the fake.
- **Out of scope for now**: hardware-in-the-loop tests against a real device in CI. Worth
  revisiting once a `meshcored` daemon exists, since a long-lived process is a better fit for an
  opt-in nightly hardware job than a one-shot CLI is.

## Future work

A `meshcored` background agent (see Design decisions, above): a small daemon owns the persistent
connection and exposes it over a local socket, so `meshcorectl` becomes a thin, instant client.
Not built yet.
