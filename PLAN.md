# meshcore-cli rewrite — design plan

Ground-up Python rewrite of [meshcore-dev/meshcore-cli](https://github.com/meshcore-dev/meshcore-cli),
dropping the interactive REPL and modeling command/argument structure on `kubectl`.

Working name for the new binary: **`meshcorectl`** (see [Decision 5](#decision-5-binary-name)).

## 0. Scope & assumptions

- **Reuse, don't reimplement, the wire protocol.** The `meshcore` PyPI package
  ([fdlamotte/meshcore_py](https://github.com/fdlamotte/meshcore_py)) already implements the
  BLE/serial/TCP transports, frame parsing, and an async `MeshCore` client with a
  `commands.*` API (`commands.get_contacts`, `commands.send_msg`, `commands.send_device_query`,
  etc.) plus an `EventType` pub/sub model. This plan rewrites **only the CLI layer** on top of
  that library — same as the original tool did. Re-implementing the mesh protocol itself is a
  separate, much larger project and is out of scope unless you want that too.
- **Interactive features are dropped, not ported.** No REPL, no `to`/chat navigation, no
  `>`/`>>`/`|`/`<|` line-redirection DSL, no `alias`/`{}` placeholder engine, no
  `handler_attach` shell-piping, no interactive BLE device picker, no serial "repeater mode"
  raw console (`-r` + sxmo scripts). Every one of these is enumerated in
  [§6](#6-explicitly-dropped-features-and-their-replacement) with its non-interactive
  replacement (usually: shell already does this better).
- **Python stays.** Target Python 3.10+ (matches the current `meshcore` dependency's floor).

## 1. What the current tool actually does (audit)

Read the original source (`src/meshcore_cli/meshcore_cli.py`, 5,322 lines) to ground this
plan in reality rather than the README alone:

| Concern | Current implementation | Problem for a "first-class CLI" |
|---|---|---|
| Argument parsing | Hand-rolled `getopt.getopt("a:d:s:ht:p:b:fjDhvSlT:Pc:Crqi")` | Single-letter flags only, no subcommands, no `--help` per command, no shell completion |
| Command dispatch | One `next_cmd()` function, a 2,000-line `match cmd:` block (`meshcore_cli.py:2212`–`4153`) | No separation of concerns, untestable in isolation, adding a command means editing a monolith |
| Command shape | Positional tokens (`msg <name> <msg>`, `set <param> <value>`), commands chainable in one invocation (`meshcli clock clock sync clock`) | No resource/verb consistency; `.` prefix or `-j` flag toggles JSON per-invocation rather than a clean `-o` flag |
| Connection | Re-established fresh on every process invocation (BLE/serial/TCP); last BLE address cached in a single flat file `$HOME/.config/meshcore/<addr>` | No named multi-device profiles; reconnect cost paid every invocation |
| Interactive mode | `prompt_toolkit` REPL, default when no args given; chat navigation (`to`), slash commands, redirection operators, alias engine, handler_attach | This is the whole piece we're told to drop |
| State/config | Global mutable module-level variables (`ARROW_HEAD`, `HAS_CLI_CMD`, function-attribute "statics" like `msg_ack.max_attempts=`) | Not thread/test-friendly, surprising |
| Output | Ad hoc per-command string building, sometimes JSON sometimes not, mixed into the same function as the logic | No consistent machine-readable path |

## 2. Kubectl idioms we're borrowing

kubectl's structure is `kubectl VERB [TYPE] [NAME] [flags]` plus a handful of standalone
imperative verbs, backed by a client/server split and a `~/.kube/config` context file. Mapping
each idiom over:

| kubectl idiom | meshcorectl equivalent |
|---|---|
| `kubectl get pods`, `kubectl get pod foo -o yaml` | `meshcorectl get contacts`, `meshcorectl get contact foo -o yaml` |
| `kubectl describe pod foo` (verbose, human, includes derived/event info) | `meshcorectl describe contact foo` (telemetry, path, flags, last-seen, all in one human view) |
| Resource short names (`po`, `svc`, `deploy`, `ns`) | `ct` (contact), `ch` (channel), `dev` (device) |
| `-o json\|yaml\|wide\|name` | Same flag, same values, on every read command |
| `-l/--selector key=value` batch targeting (`kubectl delete pods -l app=foo`) | Same flag reusing the original `apply_to` filter grammar (`-l t=2,u<24h`) on `get`, `delete`, `send`, `exec`, `login` — replaces the bespoke `apply_to` command |
| `kubectl exec pod -- cmd` | `meshcorectl exec repeater-name -- <raw cli command>` (repeater console command) |
| `kubectl logs [-f] [--since]` | `meshcorectl logs [-f] [--since]` (unread-message drain / live tail — see [§4.2](#42-logs-the-hard-one)) |
| `kubectl top node/pod` | `meshcorectl top contact NAME [--history]` (telemetry / min-max-avg) |
| `kubectl config get-contexts/use-context/current-context/view` | `meshcorectl config …` over named connection profiles (BLE address, serial port, TCP host) replacing the single cached-address file |
| `kubectl version` (prints Client + Server version) | `meshcorectl version` (prints CLI version + connected device firmware version) |
| `kubectl completion bash/zsh/fish` | `meshcorectl completion bash/zsh/fish` |
| `--dry-run` | Same, on every mutating command |
| `-v` verbosity levels | Same, replaces `-D` debug flag |
| Non-CRUD standalone verbs (`cordon`, `drain`, `taint`) | `advert`, `reboot`, `trace`, `login`, `logout` stay top-level verbs, not shoehorned into `get/create/delete` |

## 3. Command tree

```
meshcorectl
├── get           device | contacts | contact NAME | channels | channel N |
│                 pending-contacts | path CONTACT | time
├── describe      device | contact NAME
├── create        contact --uri URI   (import)
│                 channel N NAME [KEY]
├── delete        contact NAME [-l selector]
│                 channel N
│                 pending-contacts               (flush)
├── send          message CONTACT TEXT [--wait-ack]
│                 channel N TEXT
├── exec          REPEATER -- CLI_CMD            (raw repeater console cmd)
├── login         REPEATER [--password]
├── logout        REPEATER
├── top           contact NAME [--history]        (telemetry / mma)
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

Every noun gets singular + plural + short form where kubectl would (`contact`/`contacts`/`ct`,
`channel`/`channels`/`ch`). Every command gets real `--help` text and a man-page-quality
description generated from the same source (see [§7](#7-documentation)).

## 4. Design decisions (locked)

### Decision 1: one-shot connections now, background agent later — **decided**

The original tool tolerated slow BLE/serial connect time by letting you chain many commands in
a single invocation (`meshcli clock clock sync clock`). A strict "one verb per invocation"
kubectl-style CLI loses that unless something holds the connection open.

- **v1 (building this): direct-connect, one connection per invocation.** Simplest, matches the
  original's process model, fine for interactive terminal use and for scripts that don't call
  `meshcorectl` in a tight loop. BLE connect is the slow case (~1–3s); TCP/serial are fast.
- **v2 (confirmed future work): `meshcored` background agent.** A small daemon owns the
  persistent BLE/serial/TCP connection and exposes a local Unix-socket API; `meshcorectl`
  becomes a thin stateless client — literally the kubectl/kube-apiserver split applied to a mesh
  radio. This unlocks `meshcorectl get contacts -w` (watch), instant repeated invocations, and
  event subscriptions that outlive any single command.

Because v2 is confirmed (not just a maybe), `connect.py` in §5 is designed as the single seam
where a v2 client swaps in for the v1 direct-connect client without touching command modules —
every command talks to a small internal protocol (`open() -> ConnectedClient`), never to
`meshcore.MeshCore` directly. That seam is also what makes command modules testable against a
fake in §8.

### Decision 2: CLI framework — Click — **decided**

kubectl (Cobra, in Go) is a tree of commands each with local + persistent (inherited) flags,
sharing a context object. **Click** is the closest Python equivalent: nested `Group`s map
directly onto the verb tree in §3, a `click.Context` carries the resolved connection + output
formatter down through subcommands (Cobra's `PersistentPreRun` equivalent), and it has built-in
shell completion generation for free (→ `completion` command is nearly zero extra code). Click
also ships `click.testing.CliRunner`, which is what makes the "maximum test coverage" goal in
§8 tractable — every command is invocable in-process with captured stdout/stderr/exit code.

### Decision 3: table rendering — plain aligned text, zero color in v1 — **decided**

No ANSI color anywhere in this initial build — not even TTY-detected/opt-in. Readability comes
entirely from alignment and text formatting: fixed-width columns computed per-invocation from
content, consistent left/right justification (text left, numeric right, like kubectl's own
tabwriter), blank-line and header separation in `describe` views, and `-`/`<none>` placeholders
for empty fields instead of blank cells. A small internal tab-writer (~50 lines, no dependency)
covers this — no `rich`, no `colorama`. JSON via stdlib `json`; YAML via `pyyaml` (one
lightweight, ubiquitous dependency). Color is explicitly deferred to a later phase, not built
now and disabled — there is no color code to gate in v1, which also means one less thing to test.

### Decision 4: selectors replace `apply_to` — **decided**

Port the original's contact-filter grammar (`u`=updated-time, `t`=type, `h`=hops, `d`=direct,
`f`=flood) verbatim into a `-l/--selector` flag, but make it a flag on existing verbs instead of
its own command:

```
meshcorectl delete contact -l 't=1,u>2d'          # was: apply_to u>2d,t=1 remove_contact
meshcorectl exec -l 't=2,d' -- trace              # was: apply_to t=2,d trace
```

This is exactly `kubectl delete pods -l app=foo` — one flag, reused everywhere, instead of a
bespoke batch-apply verb.

### Decision 5: binary name — **decided: `meshcorectl`**

New console-script name, deliberately in the `kubectl`/`systemctl`/`<subject>ctl` family this
whole rewrite is modeled against — rather than silently reusing `meshcli`/`meshcore-cli` for a
tool with an incompatible command grammar and a removed REPL. Ship it as a new PyPI distribution
(or a clearly-major-version bump of the existing one) with the migration guide (§7) front and
center in the README, since every existing script and muscle-memory alias breaks on purpose.

## 5. Package layout

```
meshcorectl/
├── pyproject.toml
├── src/meshcorectl/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py            # root Click group: global --context/-o/--timeout/-v (no --no-color: no color exists yet, §4/D3)
│   ├── context_store.py  # ~/.config/meshcorectl/config.yaml — named connection contexts
│   ├── connect.py        # resolve context -> meshcore.MeshCore via create_ble/serial/tcp
│   ├── selectors.py       # -l filter grammar (parse + match against a contact dict)
│   ├── output/
│   │   ├── __init__.py    # dispatch on -o table|json|yaml|name
│   │   ├── table.py       # dependency-free column writer
│   │   └── resources.py   # per-resource column defs + describe-view layouts
│   └── commands/
│       ├── get.py  describe.py  create.py  delete.py  send.py  exec_.py
│       ├── login.py  top.py  logs.py  trace.py  advert.py  reboot.py
│       ├── set_.py  scan.py  config_cmd.py  version.py  completion.py
├── tests/
│   ├── fakes/
│   │   └── meshcore_double.py  # fake MeshCore/CommandHandler: scripted Event responses + error injection
│   ├── unit/              # selectors, table/output formatting, context_store — no hardware
│   └── commands/          # one test module per commands/*.py, via Click CliRunner + the fake
├── docs/
│   ├── command-reference.md     # generated from --help
│   └── migration-from-meshcli.md
├── pytest.ini             # or [tool.pytest.ini_options] in pyproject.toml; --cov + fail-under gate
└── .github/workflows/ci.yml     # pytest + coverage gate + ruff + mypy on 3.10–3.13
```

`connect.py` is the only module that imports `meshcore`'s transport classes; every command
module receives an already-connected client through the Click context, which is what makes
`tests/commands/` fast and hardware-free (inject a fake client with canned `commands.*`
responses, the same trick kubectl's own tests use with a fake clientset). See §8 for how that
double is used to hit high coverage from the first commit rather than as a Phase-4 afterthought.

## 6. Explicitly dropped features and their replacement

| Dropped | Why it was interactive-only | Non-interactive replacement |
|---|---|---|
| REPL / chat mode, `to` navigation | Whole point of the ask | none — use one-shot commands |
| `/`-prefixed slash commands | REPL-only addressing shortcut | full noun/verb command each time |
| `>`, `>>`, `\|`, `<\|` line redirection | Reimplements shell redirection inside the tool | your shell already does this: `meshcorectl get contacts -o json > f.json` |
| Alias engine (`alias`, `@name`, `{}`/`{c}` placeholders) | Built to shorten REPL lines | shell aliases/functions, or a `Makefile`/script |
| `handler_attach`/`handler_detach` (pipe rxlog/msgs to a shell process) | REPL-session-scoped subprocess plumbing | `meshcorectl logs -f --rx \| your-command` |
| Interactive BLE device picker (`-S`, `radiolist_dialog`) | Literal interactive dialog | `meshcorectl scan` prints a table; pick one and pass `--address`/`meshcorectl config set-context` |
| Serial "repeater mode" raw console (`-r`) + sxmo scripts | Bespoke raw-serial line-editing console | out of scope for v1; candidate for a `meshcorectl exec` variant later if there's demand |
| Channel-echo ANSI art, classic-prompt toggle, `wait_key` | Prompt/terminal cosmetics | n/a |
| `script <file>` (run a list of commands from a file) | Mostly a REPL/chaining convenience | shell script that calls `meshcorectl` per line; revisit as `apply -f` (declarative) only if real demand shows up |

## 7. Documentation

- `docs/command-reference.md` generated straight from each command's `--help` (Click makes this
  mechanical) — keeps reference docs from rotting relative to the actual flags.
- `docs/migration-from-meshcli.md`: one row per old command → new command, since this is a
  deliberate breaking rewrite (§0). Also update the example scripts shipped in the original repo
  (`scripts/contact_markers.sh`, `scripts/neighbour_map.sh`, `scripts/getpos.py`,
  `scripts/ask_mepo_coords`) to the new grammar as worked examples.

## 8. Testing strategy

"Maximum coverage from the beginning" means test infrastructure is part of Phase 1, not
something added once features exist, and no command module is considered done until it has
tests — not a backlog item for Phase 4.

- **The fake is the foundation.** `tests/fakes/meshcore_double.py` implements the same surface
  every command module calls (`commands.get_contacts`, `commands.send_msg`,
  `commands.send_device_query`, `subscribe`, …) and returns scripted `Event`/`EventType` values,
  including `EventType.ERROR` payloads, timeouts, and disconnects. It's built in Phase 1
  alongside `connect.py`, before any read/write commands exist, so every command from Phase 2
  onward is written test-first against it. Because §4/Decision 1 already isolates connection
  behind `connect.py`, no command module ever touches real BLE/serial/TCP in a test.
- **Every command gets a table-driven CliRunner test**, minimum: happy path, the device
  returning `EventType.ERROR`, a not-found argument (e.g. unknown contact name), and — for
  mutating commands — `--dry-run` performing no `commands.*` call. Selector-aware commands
  (`get`/`delete`/`send`/`exec`/`login` with `-l`) get selector-matrix cases (matches
  none/one/many).
- **Pure-logic modules get unit tests with no Click/CLI involvement at all**: `selectors.py`
  (the `t=`/`h=`/`u=`/`d`/`f` grammar — parser edge cases, comparison operators, relative-time
  suffixes `d`/`h`/`m`), `output/table.py` (column widths, empty-value placeholders, unicode
  name widths), `context_store.py` (read/write/round-trip the YAML, missing file, corrupt file,
  unknown `use-context` target).
- **Golden/snapshot tests for `-o json`/`-o yaml`/`-o table`/`-o name` output** on a couple of
  representative resources (a contact, a channel, the device), so accidental output-shape
  regressions are caught even though there's no schema contract with real consumers yet.
- **Coverage gate in CI**, enforced from the first PR: `pytest --cov=meshcorectl
  --cov-report=term-missing --cov-fail-under=90` (number to tune once the codebase exists, but
  the gate itself ships in Phase 1's CI workflow, not added later). `connect.py`'s thin
  transport-selection glue (the few lines that literally call `meshcore.create_ble/serial/tcp`)
  is the one module allowed a `# pragma: no cover` carve-out, since exercising it means real
  hardware — everything above that seam is covered by the fake.
- **Out of scope for v1:** hardware-in-the-loop tests against a real device. Worth revisiting
  once the Phase 5 `meshcored` daemon exists, since a long-lived daemon process is a much better
  fit for an opt-in nightly hardware CI job than a one-shot CLI is.

## 9. Delivery phases

1. **Scaffolding** — package skeleton, `context_store.py` + `config` command group, `connect.py`,
   root Click group with global flags, output layer (table/json/yaml), the `meshcore_double`
   test fake, and CI wired with the coverage gate from §8 — all before the first real command.
2. **Read path** — `get`, `describe`, `top`, `logs`, `scan`, `version`, each landing with its
   CliRunner test suite per §8. This alone is already a useful, testable tool and the
   highest-value/lowest-risk slice to ship first.
3. **Write path** — `create`, `delete`, `send`, `exec`, `login`/`logout`, `advert`, `reboot`,
   `set device`, `trace`, plus `-l` selectors wired into all of them — same test-first bar,
   including the `--dry-run` no-op case on every mutating command.
4. **Polish** — `completion`, full docs (§7), migration guide, package/publish as `meshcorectl`.
5. **(Confirmed follow-up, later)** `meshcored` background agent per Decision 1.
