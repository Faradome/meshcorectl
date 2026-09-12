# Migrating from meshcore-cli (`meshcli`)

meshcorectl is a ground-up rewrite of
[meshcore-dev/meshcore-cli](https://github.com/meshcore-dev/meshcore-cli), not a drop-in
replacement: the command grammar is deliberately modeled on `kubectl` instead of `meshcli`'s own
positional-argument-chain style, and the interactive REPL is gone entirely (see
[PLAN.md](../PLAN.md) for the full design rationale). Every `meshcli`/`meshcore-cli` script or
muscle-memory alias will need updating. This guide is the map from old to new.

## Connecting: named contexts instead of a cached address

`meshcli` remembered one last-used BLE address in `$HOME/.config/meshcore/`. meshcorectl
replaces that with named, switchable connection profiles — kubectl's `~/.kube/config` applied to
a mesh radio:

```bash
# was: meshcli -a C2:2B:A1:D5:3E:B6 <command>   (or just relying on the cached address)
meshcorectl config set-context home --ble-address C2:2B:A1:D5:3E:B6
meshcorectl config set-context repeater-usb --serial-port /dev/ttyUSB0
meshcorectl config set-context lab --tcp-host 192.168.1.50 --tcp-port 5000

meshcorectl config use-context home     # make one the default
meshcorectl --context lab get device    # or override per-invocation
```

`meshcli -S`'s interactive device picker is gone too (PLAN.md §6) — `meshcorectl scan` lists
candidates as a plain table; copy an address from it into `config set-context` instead of
selecting it from a live menu.

## Output: one flag, not a prefix and a mode

`meshcli` toggled JSON output per-command with a `.` prefix, or globally with `-j`. meshcorectl
has one global flag, valid on every read command and every mutating command's confirmation:

```bash
# was: meshcli .clock            or          meshcli -j clock
meshcorectl -o json get time
meshcorectl -o yaml get contacts
meshcorectl -o wide get contacts        # extra columns, like `kubectl get -o wide`
meshcorectl -o name get contacts        # just names, for scripting
```

## Command mapping

Old commands in *italics* have no meshcorectl equivalent yet — see
[Not yet in meshcorectl](#not-yet-in-meshcorectl) below.

### General

| `meshcli` | meshcorectl |
|---|---|
| `infos` / `i` | `get device` (or `describe device` for a labeled human view) |
| `ver` / `v` / `query` / `q` | `version` |
| `reboot` | `reboot --yes` |
| *`self_telemetry` / `t`* | not yet ported |
| *`card` / `e`* | not yet ported |
| `sleep <secs>` / `s` | your shell's own `sleep` |
| `apply_to <filter> <cmd>` / `at` | `-l/--selector` on `get`/`delete`/`send`/`exec`/`login` — see below |
| `script <file>` | a shell script calling `meshcorectl` per line |
| `alias`/`aliases`/`aliases_load`, `wait_key`/`wk`, `handler_attach`/`handler_detach` | dropped — interactive-only (PLAN.md §6) |

### Messaging

| `meshcli` | meshcorectl |
|---|---|
| `msg <name> <msg>` / `m` | `send message NAME TEXT` |
| `msg ...` then `wait_ack` / `wa` | `send message NAME TEXT --wait-ack` (one command, not two) |
| `chan <nb> <msg>` / `ch` | `send channel N TEXT` |
| `public <msg>` / `dch` | `send channel 0 TEXT` (channel 0 is the public channel) |
| `sync_msgs` / `sm` | `logs` |
| `msgs_subscribe` / `ms` | `logs --follow` |
| `recv` / `r`, `wait_msg` / `wm` | `logs` / `logs --follow` (no single-next-message read) |
| `get_channels` | `get channels` |
| `get_channel <n>` | `get channel N` |
| `set_channel n nm k` | `create channel N NAME [KEY]` |
| `remove_channel <n>` | `delete channel N` |
| *`scope <s>`* | not yet ported (flood scope) |

### Management

| `meshcli` | meshcorectl |
|---|---|
| `advert` / `a` | `advert` |
| `floodadv` | `advert --flood` |
| `set <param> <value>` | `set device PARAM VALUE` (a curated subset — run `meshcorectl set device --help` for the list) |
| `clock` | `get time` |
| *`clock sync` / `st`, `time <epoch>`* | not yet ported (setting the device clock) |
| *`get <param>`, `node_discover`, `cli <cmd>`, `send_raw <pkt>`* | not yet ported |

### Contacts

| `meshcli` | meshcorectl |
|---|---|
| `contacts` / `list` / `lc` | `get contacts` |
| `contact_info <ct>` / `ci` | `get contact NAME` / `describe contact NAME` |
| `import_contact <URI>` / `ic` | `create contact --uri URI` |
| `remove_contact <ct>` | `delete contact NAME` (or `-l selector` for many at once) |
| `path <ct>` | `get path NAME` |
| `req_telemetry <ct>` / `rt` | `top contact NAME` |
| `req_mma <ct>` / `rm` | `top contact NAME --history` |
| `pending_contacts` | `get pending-contacts` — redesigned: watches for one timeout window instead of reading a session-long cache, see below |
| `reload_contacts` / `rc` | nothing to do — every invocation fetches fresh (no cache to reload) |
| `flush_pending` | **dropped**, not just unported — see below |
| *`add_pending`, `share_contact`/`sc`, `export_contact`/`ec`, `disc_path`/`dp`, `reset_path`/`rp`, `change_path`/`cp`, `change_flags`/`cf`, `req_acl`, `contact_timeout`* | not yet ported |

### Repeaters

| `meshcli` | meshcorectl |
|---|---|
| `login <name> <pwd>` / `l` | `login NAME --password ...` (or `--password-stdin`, or the secure prompt) |
| `logout <name>` | `logout NAME` |
| `cmd <name> <cmd>` / `c` then `wmt8` / `]` | `exec NAME -- CMD` (sends and waits for the reply automatically, in one step) |
| `trace <path>` | `trace PATH` |
| *`req_status`/`rs`, `req_neighbours`/`rn`* | not yet ported |

## Batch operations: `-l/--selector` instead of `apply_to`

`apply_to <filter> <cmd>` ran one command against every contact matching a filter. meshcorectl
folds the same filter grammar into a `-l/--selector` flag on the commands that target a contact,
instead of a separate batch-apply command:

```bash
# was: apply_to u>2d,t=1 remove_contact
meshcorectl delete contact -l 't=1,u>2d'

# was: apply_to t=2,d trace     (not a literal equivalent -- trace takes a path, not a contact --
#                                 this shows the filter syntax carrying over to a batch-capable verb)
meshcorectl login -l 't=2,d' --password-stdin < password.txt
```

Filter fields are unchanged: `t` (type — `t=repeater` or the original's numeric `t=2`, both
work), `h` (hop count), `u` (last-updated, `u<2d`/`u>1h`/an absolute epoch), `d` (direct), `f`
(flood). See `meshcorectl delete contact --help` for the full grammar.

## `pending_contacts`/`flush_pending`: why one moved and one disappeared

`meshcli` built its pending-contacts list from adverts received over however long its process
happened to stay running, then let you `flush_pending` to clear that in-memory list. meshcorectl
connects once per invocation (see PLAN.md's Decision 1) — there is no long-running process to
accumulate adverts in between commands. `get pending-contacts` adapts by *actively listening* for
one `--timeout` window and reporting whatever arrives in it, which is why it's a `get`, not a
cached read. `flush_pending` has no equivalent because there's nothing persisted to flush: each
`get pending-contacts` invocation starts from nothing, every time.

## Dropped entirely (interactive-only)

The whole REPL — `to` navigation, `/`-prefixed slash commands, the `>`/`>>`/`|`/`<|`
line-redirection DSL, the `alias`/`@name` engine, `handler_attach`/`handler_detach`,
`wait_key`, the interactive BLE device picker, channel-echo ANSI art, and the serial
"repeater mode" raw console (`-r`) — is gone, on purpose. See PLAN.md §6 for the full table and
the reasoning behind each one; the short version is that a real shell already does everything
the redirection DSL did, and `meshcorectl scan` replaces the interactive picker with a plain list.

## Not yet in meshcorectl

Everything marked *not yet ported* above is a genuine gap against the original tool's full
surface, not a design decision to drop it — the underlying `meshcore` library already exposes
the commands needed for nearly all of them (`change_contact_path`, `share_contact`,
`export_contact`, `reset_path`, `req_status_sync`, `req_acl_sync`, `req_neighbours_sync`,
`send_node_discover_req`, `run_cli_command`, `send_raw_packet`, `set_time`, and more). Adding one
means following the same shape every existing command already does: a small pure function in
`mesh_data.py` (tested against the fake in `tests/fakes/meshcore_double.py`, no hardware needed),
a thin Click command wired into `cli.py`, and a `tests/commands/` suite — see any existing
command for the pattern.

## Worked examples

The original tool's `scripts/` directory has been ported to
[`scripts/examples/`](../scripts/examples/README.md), with the actual data-processing logic
unchanged in every case — only how a script's output reaches meshcorectl changed, since the
interactive redirection DSL those scripts targeted no longer exists (a plain shell pipeline
replaces it directly).
