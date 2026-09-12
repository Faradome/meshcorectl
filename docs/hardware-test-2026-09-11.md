# Live hardware test report — 2026-09-11

First full end-to-end test of `meshcorectl` against real MeshCore hardware, using two
companion radios and one repeater in a lab environment.

## Environment

| | |
|---|---|
| **dev1** | `/dev/cu.usbmodem101`, name `AD6D4061`, pubkey `ad6d4061c3...`, fw `v1.17.1-d929643` (protocol 13) |
| **dev2** | `/dev/cu.usbmodem2101`, name `3356E06D`, pubkey `3356e06d04...`, fw `v1.17.1-d929643` (protocol 13) |
| **Repeater** | "Repeater 1d4e", pubkey `1d4e2a7059...`, direct (0-hop) neighbor of both devices |
| Radio | 910.525MHz, BW 62.5kHz, SF7, CR5 |
| Repeater password | supplied out-of-band for this test; not recorded here |
| meshcorectl | this checkout, Phase 1–4 complete, connected via `--serial-port` contexts |

Both devices were logged into the repeater at the start, per the brief. Channels `Public`
(0) and `TestChannel` (1) were pre-configured on both; the other 38 channel slots were
empty. Neither device had the other as a contact yet (both `manual_add_contacts=true`).

## Methodology

Real radio traffic was deliberately paced (several seconds between transmitting commands,
no loops/repeats beyond what was needed to confirm a result) per the request to not overrun
the mesh. Read-only local queries (`get device`, `get contacts`, `get channels`, `get time`,
`version`, `config *`) are pure USB-serial round trips to the attached node's own state —
they generate no LoRa airtime, so those were run freely. Mutating tests used two safety
patterns throughout:
- **Same-value round trips** for `set device` — read the current value, "set" it back to
  itself, confirm no error and no change — validates the write path with zero behavioral risk.
- **Create-then-clean-up** for anything net-new (a test channel, an auto-added test contact)
  — created, verified, then removed, restoring the device to its prior state.

`reboot` and the manual-add-contacts toggle are the two tests that couldn't be made fully
risk-free; see [Known state left behind](#known-state-left-behind-please-check).

## Results by command

### Read path — all confirmed working
`get device`, `get contacts`, `get contact NAME`, `get channels`, `get channel N` (by index
and by name), `get path`, `get time`, `get pending-contacts`, `describe device`,
`describe contact`, `version`, `scan --no-ble`, `completion bash`, all `config *`
subcommands, `logs` (drain mode), `top contact` (real telemetry: voltage 3.92V,
temperature 21.5°C from the repeater) — all correct in both `table` and `-o json`/`-o yaml`.

### Write path — confirmed working
- `send message` (direct, to a known contact), with and without `--wait-ack` — real ACK
  confirmed (554ms round trip)
- `send channel` by index and by name — real end-to-end delivery confirmed in both
  directions (dev1→dev2 and dev2→dev1), SNR/path populated correctly
- `advert` and `advert --flood`
- `login` (`--password` and `--password-stdin`) and `logout` against the real repeater —
  until the post-reboot issue below
- `exec` — command sent, reply received and printed correctly (the repeater didn't
  recognize `ver`/`clock` as commands, replying "Unknown command"; `help` returned its
  version string — that's the repeater's own command vocabulary, not a meshcorectl issue)
- `create channel` / `delete channel` — round-tripped on an unused slot
- `set device` — round-tripped for all 9 supported params (`name`, `tx-power`, `coords`,
  `multi-acks`, `advert-loc-policy`, `telemetry-mode-base/loc/env`, `manual-add-contacts`,
  `pin`), zero side effects confirmed by re-reading device state after
- `set device manual-add-contacts off` + `advert --flood` + `get contacts` on the other
  device — full auto-add-on-advert flow confirmed end-to-end
- `delete contact` — real deletion (of a contact created during this test), confirmed
  removed, state fully restored after
- `-l/--selector` — confirmed correct matching against real device data and a correct
  dry-run short-circuit (`delete contact -l 't=repeater,d' --dry-run`)
- `reboot --yes` — device rebooted and reconnected successfully over serial

## Issues found

### 1. Bug — `logs --follow` never shows live-arriving messages
Confirmed with three separate attempts (12s/20s windows, unbuffered output to rule out a
buffering artifact). A message sent by the other device while `--follow` is running never
appears — but it *is* sitting queued on the device and drains normally on the very next
plain `logs` call, so it genuinely arrived; the live display just never fires.

**Root cause, confirmed**: `logs --follow --rx` (the raw rx_log tap) *does* show live events
correctly and immediately — proving `CONTACT_MSG_RECV`/`CHANNEL_MSG_RECV` are not passively
pushed events the way `RX_LOG_DATA` is. They only fire as a side effect of an explicit
`commands.get_msg()` call, normally triggered by a `MESSAGES_WAITING` notification. Plain
`--follow` subscribes directly to the result event types and never calls `get_msg()`, so it
never sees anything. Fix: subscribe to `MESSAGES_WAITING` and call `get_msg()` in response
(the `meshcore` library's own `start_auto_message_fetching()` does exactly this).
**Impact: `logs -f`'s main purpose — live tailing — is currently non-functional.**

### 2. Bug — global `-o`/`--output` must precede the subcommand
`meshcorectl get device -o json` fails ("Error: No such option '-o'"); only
`meshcorectl -o json get device` works, because `-o` is defined only on the root Click
group. Real kubectl accepts `-o` after the verb (`kubectl get pods -o json`) — this is a
usability gap against the model this tool is supposed to follow, and the kind of thing a
user will hit immediately and repeatedly.

### 3. Bug — `get contacts`/`get contact` have no `-l/--selector`
PLAN.md and the Phase 3 completion summary both state selectors are wired into
`get`/`delete`/`send`/`exec`/`login`. Confirmed on hardware: `delete`, `send`, `exec`,
`login` all correctly accept `-l`; `get contacts -l t=repeater` errors with "No such option
'-l'". `get.py` never actually received the selector flag — a real gap between the design
doc/summary and the shipped code.

### 4. Efficiency — `top contact` opens two separate connections
Visible directly in the logs as two "Serial Connection started" lines for one invocation:
contact resolution and the telemetry fetch are two separate `state.call()`s, unlike
`send`/`delete`/`exec`/`login`, which correctly do both within a single connection. Not
incorrect, just doubles connection overhead (worse on BLE than serial) for no reason.

### 5. Inconclusive — `trace` against the repeater always times out
Verified this is *not* a client-side timeout-handling bug: wall-clock wait matched the
requested `--timeout` exactly (e.g., `time` showed ~5.1s for `--timeout 5`), and the debug
log shows `send_trace` went out correctly (sane tag/expected_ack/suggested_timeout). No
`TRACE_DATA` reply ever came back. Could be this repeater firmware not responding to trace
requests, or a real path/flags mismatch — not disambiguated further to avoid burning airtime
on repeated attempts. Worth another look with a wired protocol analyzer or a second repeater.

### 6. Environment, not a code bug — direct flood message dev2→dev1 got no ack
Right after dev1 auto-added dev2 (well, dev1's contact got auto-added to dev2 — see below)
with an unknown/flood path, `send message --wait-ack` timed out, and the message never
reached the other side even without `--wait-ack`. Channel messages between the same two
devices worked perfectly throughout. The CLI plumbing and `send_msg_with_retry` logic both
look correct in the debug log — this looks like a real mesh/RF topology limit (dev1 and dev2
may only be in range of the repeater, not of each other directly), not a meshcorectl defect.

### 7. Unresolved — login to the repeater times out after dev1's reboot
After the `reboot --yes` test, `login` to the repeater timed out three times running
(including one attempt with `--timeout 25`), while a plain `send message --wait-ack` to the
very same repeater succeeded normally in between attempts (554ms round trip, verified via
debug log) — so it isn't a general post-reboot connectivity problem. Stopped retrying to
avoid hammering the repeater's auth handling. Not disambiguated between a repeater-side rate
limit on login attempts (plausible — this session did attempt login several times total) and
a real client-side issue specific to `send_login_sync`.

## Known state left behind (please check)

- **dev1 is very likely logged out of "Repeater 1d4e"** — the pre-test brief said both
  devices start logged in; dev1 was rebooted as part of testing `reboot`, and the login
  retry afterward did not succeed (see Issue 7). dev2 was not rebooted and should still be
  logged in (confirmed responsive via `exec ... -- help` afterward, though that alone isn't
  a airtight login proof either way).
- Both devices' contact lists, channel tables, and every `set device` parameter were
  verified back to their pre-test values.
- No content was pushed to the mesh beyond test messages/adverts clearly tagged
  `hwtest-...`; nothing else on the mesh should have been affected.

## Suggested next steps

1. Fix Issue 1 (`logs --follow`) — it's the highest-impact bug (a shipped feature that
   doesn't do its one job) and the root cause is already confirmed.
2. Decide on Issue 2 (`-o` position) — either accept the kubectl-idiom gap and document it
   clearly, or restructure so read commands can take `-o` themselves (bigger change).
3. Add the missing `-l/--selector` to `get contacts`/`get contact` (Issue 3) to match the
   design doc, or correct the design doc if it's intentionally `get`-exempt.
4. Fold `top contact`'s two connections into one (Issue 4), matching the pattern already
   used everywhere else.
5. Re-attempt login on dev1 once you're ready (Issue 7), ideally with a short cool-off
   period first in case it's a repeater-side rate limit.

## Fixes applied and re-verified on real hardware (same day)

All four confirmed bugs (Issues 1–4) were fixed and re-tested against dev1/dev2 the same way
they were found, not just in the unit test suite:

- **Issue 1** (`logs --follow`): `MESSAGES_WAITING` is now subscribed and triggers a
  `drain_messages()` call (reusing the same helper the initial batch already used), instead of
  passively subscribing to `CONTACT_MSG_RECV`/`CHANNEL_MSG_RECV`, which — per the root cause
  found during testing — never fire on their own. Re-verified live: a channel message sent by
  dev2 now appears in dev1's `logs --follow` output in real time.
- **Issue 2** (`-o` position): every command that renders output now also accepts its own
  local `-o/--output`, which wins over the global one when both are given
  (`output.output_option`/`resolve_output`). Re-verified live: `get device -o json` (flag
  *after* the subcommand) now works.
- **Issue 3** (missing selector): `get contacts` now accepts `-l/--selector`, matching
  `delete`/`send`/`exec`/`login`. Re-verified live: `get contacts -l t=repeater` /
  `-l t=client` correctly filter the real contact list.
- **Issue 4** (`top` double connection): contact resolution and the telemetry fetch now share
  one connection. Re-verified live: exactly one "Serial Connection started" log line for one
  `top contact` invocation (was two). A regression test (`connect_call_count == 1`) was also
  added to the fixture used by every command test, since the existing test suite structurally
  could not have caught this class of bug (the fake connection fixture hands back the same
  object regardless of how many times "connect" is called).

Issue 7 (post-reboot login timeout) was not code-fixed — you confirmed manually that login to
the repeater works fine now, consistent with the report's own hypothesis that it was a
transient/rate-limit condition rather than a client bug. Issues 5 (`trace`) and 6 (flood
messaging between the two devices) remain open/unexplained, as noted above.
