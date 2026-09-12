"""Translates meshcore Events/payloads into the plain dict shapes
`get`/`describe`/`top` commands hand to `output.render()`.

No Click here: every function takes a `MeshCoreConnection` and is unit
tested directly, independent of any command wiring.

Field names below (contact/channel/device-info/telemetry keys) come from
the `meshcore` library's wire-format parser and command modules; there is
no protocol spec to cite.
"""

from __future__ import annotations

import datetime
import secrets
from collections.abc import Callable
from typing import Any

from meshcore import EventType

from .connect import MeshCoreConnection

CONTACT_TYPE_NAMES = {0: "none", 1: "client", 2: "repeater", 3: "room", 4: "sensor"}


class MeshDataError(Exception):
    """A device command returned `EventType.ERROR`, or timed out (returned None)."""


class AmbiguousMatchError(ValueError):
    """More than one contact matches a name or public-key-prefix lookup."""


def contact_type_name(type_id: int) -> str:
    return CONTACT_TYPE_NAMES.get(type_id, f"unknown({type_id})")


def format_path(contact: dict[str, Any]) -> str:
    """"flood", "direct", or a comma-separated list of path hop hashes."""
    path_len = contact.get("out_path_len")
    if path_len is None or path_len < 0:
        return "flood"
    if path_len == 0:
        return "direct"
    hash_size = contact.get("out_path_hash_mode", 0) + 1
    raw = contact.get("out_path") or ""
    hop_chars = hash_size * 2
    hops = [raw[i * hop_chars : (i + 1) * hop_chars] for i in range(path_len)]
    return ",".join(hops)


def _check(event: Any, action: str) -> Any:
    """Raise `MeshDataError` for a None (timeout) or `EventType.ERROR` result;
    otherwise return the event unchanged, for a one-line call-site idiom."""
    if event is None:
        raise MeshDataError(f"timed out {action}")
    if event.type == EventType.ERROR:
        payload = event.payload
        reason = payload.get("reason", payload) if isinstance(payload, dict) else payload
        raise MeshDataError(f"error {action}: {reason}")
    return event


def normalize_contact(raw: dict[str, Any]) -> dict[str, Any]:
    """`public_key` is kept (not just a display field): the `meshcore`
    library accepts any dict with a `public_key` as a send destination, so
    this same normalized dict can be passed straight back into
    `commands.req_telemetry_sync()`, `commands.send_msg()`, etc. -- no
    separate "raw contact" shape needed. `hops` is `path` (the human
    string) restated as the raw signed int (-1 flood, 0 direct, N hops),
    for `selectors.py`'s `h`/`d`/`f` clauses."""
    return {
        "name": raw.get("adv_name", ""),
        "type": contact_type_name(raw.get("type", 0)),
        "public_key": raw.get("public_key", ""),
        "path": format_path(raw),
        "hops": raw.get("out_path_len", -1),
        "last_advert": raw.get("last_advert"),
        "lastmod": raw.get("lastmod"),
        "flags": raw.get("flags", 0),
        "adv_lat": raw.get("adv_lat"),
        "adv_lon": raw.get("adv_lon"),
    }


async def fetch_contacts(connection: MeshCoreConnection) -> list[dict[str, Any]]:
    event = _check(await connection.commands.get_contacts(), "fetching contacts")
    contacts = [normalize_contact(c) for c in event.payload.values()]
    contacts.sort(key=lambda c: c["name"].lower())
    return contacts


def find_contact(contacts: list[dict[str, Any]], name_or_prefix: str) -> dict[str, Any] | None:
    """Case-insensitive match on name first, then public-key prefix --
    the same precedence as the `meshcore` library's own
    get_contact_by_name/get_contact_by_key_prefix helpers.

    Raises `AmbiguousMatchError` if more than one contact matches at
    whichever stage (name or prefix) produces a match, rather than
    silently acting on whichever one happened to come first in the list --
    the same "unambiguous or refuse" rule git applies to abbreviated commit
    hashes.
    """
    needle = name_or_prefix.lower()
    by_name = [c for c in contacts if c["name"].lower() == needle]
    if len(by_name) > 1:
        matches = ", ".join(f"{c['name']!r} ({c['public_key'][:8]})" for c in by_name)
        raise AmbiguousMatchError(
            f"{name_or_prefix!r} matches {len(by_name)} contacts by name: {matches} -- "
            "use a public-key prefix instead"
        )
    if by_name:
        return by_name[0]

    by_prefix = [c for c in contacts if c["public_key"].lower().startswith(needle)]
    if len(by_prefix) > 1:
        matches = ", ".join(f"{c['name']!r} ({c['public_key'][:8]})" for c in by_prefix)
        raise AmbiguousMatchError(
            f"{name_or_prefix!r} matches {len(by_prefix)} contacts by public-key prefix: "
            f"{matches} -- use a longer prefix"
        )
    if by_prefix:
        return by_prefix[0]
    return None


def normalize_channel(raw: dict[str, Any]) -> dict[str, Any]:
    secret = raw.get("channel_secret", b"")
    return {
        "index": raw.get("channel_idx"),
        "name": raw.get("channel_name", ""),
        "secret": secret.hex() if isinstance(secret, (bytes, bytearray)) else secret,
    }


def find_channel(channels: list[dict[str, Any]], index_or_name: str) -> dict[str, Any] | None:
    """Numeric argument -> match by index; otherwise a case-insensitive
    name match, same precedence `get`/`send`/`delete` all want."""
    if index_or_name.isdigit():
        index = int(index_or_name)
        return next((c for c in channels if c["index"] == index), None)
    needle = index_or_name.lower()
    return next((c for c in channels if c["name"].lower() == needle), None)


async def fetch_channels(connection: MeshCoreConnection) -> list[dict[str, Any]]:
    """Probe channel slots 0, 1, 2, ... until the device returns an error --
    there's no "how many channels are set" query."""
    channels: list[dict[str, Any]] = []
    index = 0
    while True:
        event = await connection.commands.get_channel(index)
        if event.type == EventType.ERROR:
            break
        channels.append(normalize_channel(event.payload))
        index += 1
    return channels


async def fetch_device(connection: MeshCoreConnection) -> dict[str, Any]:
    """Merge the advertised self-info (already known at connect time) with
    the firmware/protocol query into one dict."""
    query = _check(await connection.commands.send_device_query(), "querying the device")
    info: dict[str, Any] = dict(connection.self_info)
    info.update(query.payload)
    info.setdefault("name", "")
    return info


def _isoformat(epoch: int) -> str:
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


async def fetch_time(connection: MeshCoreConnection) -> dict[str, Any]:
    event = _check(await connection.commands.get_time(), "getting the device time")
    epoch = event.payload["time"]
    return {"epoch": epoch, "time": _isoformat(epoch)}


async def fetch_telemetry(
    connection: MeshCoreConnection, contact: dict[str, Any]
) -> list[dict[str, Any]]:
    """Each reading is `{"channel": int, "type": str, "value": ...}` -- the
    shape `meshcore`'s Cayenne-LPP JSON encoder produces."""
    lpp = await connection.commands.req_telemetry_sync(contact)
    if lpp is None:
        raise MeshDataError(f"timed out requesting telemetry from {contact['name']}")
    return lpp


async def fetch_telemetry_history(
    connection: MeshCoreConnection, contact: dict[str, Any], *, start: int, end: int
) -> list[dict[str, Any]]:
    """Each reading is `{"channel", "type", "min", "max", "avg"}`."""
    mma = await connection.commands.req_mma_sync(contact, start, end)
    if mma is None:
        raise MeshDataError(f"timed out requesting telemetry history from {contact['name']}")
    return mma


def normalize_message(
    raw: dict[str, Any],
    *,
    contacts: list[dict[str, Any]] | None = None,
    channels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a raw CONTACT_MSG_RECV/CHANNEL_MSG_RECV payload's sender to a
    display name, given the contact/channel lists already fetched this
    invocation -- there's no cache to consult otherwise."""
    if raw.get("type") == "CHAN":
        index = raw.get("channel_idx")
        channel = next((c for c in (channels or []) if c.get("index") == index), None)
        if channel and channel.get("name"):
            sender = channel["name"]
        elif index == 0:
            sender = "public"
        else:
            sender = f"ch{index}"
    else:
        prefix = raw.get("pubkey_prefix", "")
        contact = find_contact(contacts or [], str(prefix))
        sender = contact["name"] if contact else str(prefix)

    return {
        "name": sender,
        "from": sender,
        "text": raw.get("text", ""),
        "path_len": raw.get("path_len"),
        "SNR": raw.get("SNR"),
    }


async def drain_messages(connection: MeshCoreConnection) -> list[dict[str, Any]]:
    """Fetch every currently-queued message, oldest first, stopping at
    NO_MORE_MSGS."""
    messages: list[dict[str, Any]] = []
    while True:
        event = await connection.commands.get_msg()
        if event.type in (EventType.NO_MORE_MSGS, EventType.ERROR):
            break
        messages.append(event.payload)
    return messages


async def import_contact(connection: MeshCoreConnection, uri: str) -> None:
    """`uri` must be a `meshcore://<hex>` contact-card URI."""
    prefix = "meshcore://"
    if not uri.startswith(prefix):
        raise MeshDataError(f"not a meshcore contact URI (expected {prefix}...): {uri!r}")
    try:
        payload = bytes.fromhex(uri[len(prefix) :])
    except ValueError as exc:
        raise MeshDataError(f"invalid hex in contact URI: {exc}") from exc
    _check(await connection.commands.import_contact(payload), "importing contact")


async def remove_contact(connection: MeshCoreConnection, contact: dict[str, Any]) -> None:
    _check(await connection.commands.remove_contact(contact), "removing contact")


async def create_channel(
    connection: MeshCoreConnection, index: int, name: str, secret_hex: str | None
) -> dict[str, Any]:
    """`secret_hex`, if given, must be 32 hex chars (16 bytes).

    When omitted, what happens depends on `name`:
    - A `#`-prefixed name is the public-channel convention: `commands.set_channel`
      derives the secret deterministically from the name itself, so anyone who
      knows the name can compute the same key and join. Left as `None` here so
      the library does exactly that (not reimplemented).
    - Any other name is meant to be a private channel, so meshcorectl generates
      a random 16-byte secret itself here -- letting `set_channel` fall back to
      its own name-derived secret in that case would silently make the "private"
      channel just as guessable as a public one.
    """
    secret: bytes | None
    if secret_hex is not None:
        if len(secret_hex) != 32:
            raise MeshDataError("channel secret must be exactly 32 hex characters (16 bytes)")
        try:
            secret = bytes.fromhex(secret_hex)
        except ValueError as exc:
            raise MeshDataError(f"invalid hex in channel secret: {exc}") from exc
    elif name.startswith("#"):
        secret = None
    else:
        secret = secrets.token_bytes(16)
    _check(await connection.commands.set_channel(index, name, secret), "setting channel")
    confirmed = _check(await connection.commands.get_channel(index), "reading back the channel")
    return normalize_channel(confirmed.payload)


async def delete_channel(connection: MeshCoreConnection, index: int) -> None:
    """There's no dedicated "delete channel" wire command: clearing the
    name and zeroing the secret is the convention used instead."""
    _check(await connection.commands.set_channel(index, "", bytes(16)), "clearing channel")


async def send_message(
    connection: MeshCoreConnection, contact: dict[str, Any], text: str, *, wait_ack: bool
) -> dict[str, Any]:
    if not wait_ack:
        _check(await connection.commands.send_msg(contact, text), "sending message")
        return {"sent": True}

    result = await connection.commands.send_msg_with_retry(contact, text)
    if result is None:
        raise MeshDataError(f"no ack received from {contact['name']}")
    _check(result, "sending message")
    return {"sent": True, "acked": True}


async def send_channel_message(
    connection: MeshCoreConnection, channel: dict[str, Any], text: str
) -> dict[str, Any]:
    result = await connection.commands.send_chan_msg(channel["index"], text)
    _check(result, "sending channel message")
    return {"sent": True}


async def run_repeater_command(
    connection: MeshCoreConnection, contact: dict[str, Any], command: str, *, timeout: float
) -> str | None:
    """Send a raw console command to a repeater/room and wait for its reply
    in one round-trip (`kubectl exec`'s synchronous "run this, show me the
    output" shape). Returns the reply text, or None if nothing came back
    within `timeout`.
    """
    _check(await connection.commands.send_cmd(contact, command), "sending repeater command")
    notified = await connection.wait_for_event(EventType.MESSAGES_WAITING, timeout=timeout)
    if notified is None:
        return None
    reply = _check(await connection.commands.get_msg(), "reading the repeater's reply")
    return reply.payload.get("text")


async def login(
    connection: MeshCoreConnection, contact: dict[str, Any], password: str, *, timeout: float
) -> bool:
    result = await connection.commands.send_login_sync(contact, password, timeout=timeout)
    if result is None:
        raise MeshDataError(f"login to {contact['name']} timed out")
    return bool(result.type == EventType.LOGIN_SUCCESS)


async def logout(connection: MeshCoreConnection, contact: dict[str, Any]) -> None:
    _check(await connection.commands.send_logout(contact), "logging out")


async def send_advert(connection: MeshCoreConnection, *, flood: bool) -> None:
    _check(await connection.commands.send_advert(flood=flood), "sending advert")


async def reboot_device(connection: MeshCoreConnection) -> None:
    """No response is expected -- the device reboots immediately."""
    await connection.commands.reboot()


async def run_trace(
    connection: MeshCoreConnection, path_spec: str, *, timeout: float | None = None
) -> list[dict[str, Any]]:
    """`path_spec` is a comma-separated hex list of repeater pubkey
    prefixes (e.g. "23,5f,3a") -- `commands.send_trace` parses that string
    itself, so it's forwarded as-is rather than re-parsed here."""
    sent = _check(await connection.commands.send_trace(path=path_spec), "sending trace")
    tag = int.from_bytes(sent.payload["expected_ack"], byteorder="little")
    if timeout is None:
        timeout = sent.payload["suggested_timeout"] / 1000 * 1.2
    event = await connection.wait_for_event(
        EventType.TRACE_DATA, attribute_filters={"tag": tag}, timeout=timeout
    )
    if event is None:
        raise MeshDataError(f"timed out waiting for a trace reply on path {path_spec!r}")
    _check(event, "waiting for trace")
    return list(event.payload["path"])


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("on", "true", "1", "yes"):
        return True
    if normalized in ("off", "false", "0", "no"):
        return False
    raise ValueError(f"expected on/off, got {value!r}")


def _parse_coords(value: str) -> tuple[float, float]:
    parts = value.split(",")
    if len(parts) != 2:
        raise ValueError("expected 'LAT,LON'")
    return float(parts[0]), float(parts[1])


_DEVICE_PARAM_SETTERS: dict[str, Callable[[MeshCoreConnection, str], Any]] = {
    "name": lambda conn, value: conn.commands.set_name(value),
    "tx-power": lambda conn, value: conn.commands.set_tx_power(int(value)),
    "coords": lambda conn, value: conn.commands.set_coords(*_parse_coords(value)),
    "telemetry-mode-base": lambda conn, value: conn.commands.set_telemetry_mode_base(int(value)),
    "telemetry-mode-loc": lambda conn, value: conn.commands.set_telemetry_mode_loc(int(value)),
    "telemetry-mode-env": lambda conn, value: conn.commands.set_telemetry_mode_env(int(value)),
    "manual-add-contacts": (
        lambda conn, value: conn.commands.set_manual_add_contacts(_parse_bool(value))
    ),
    "multi-acks": lambda conn, value: conn.commands.set_multi_acks(int(value)),
    "advert-loc-policy": lambda conn, value: conn.commands.set_advert_loc_policy(int(value)),
    "pin": lambda conn, value: conn.commands.set_devicepin(int(value)),
}

DEVICE_PARAMS = tuple(sorted(_DEVICE_PARAM_SETTERS))


async def set_device_param(connection: MeshCoreConnection, param: str, value: str) -> None:
    """A curated subset of device parameters; see `DEVICE_PARAMS` for
    exactly which ones."""
    setter = _DEVICE_PARAM_SETTERS.get(param)
    if setter is None:
        raise MeshDataError(
            f"unknown device parameter {param!r} (expected one of: {', '.join(DEVICE_PARAMS)})"
        )
    try:
        result = await setter(connection, value)
    except ValueError as exc:
        raise MeshDataError(f"invalid value {value!r} for {param}: {exc}") from exc
    _check(result, f"setting {param}")


async def collect_events(
    connection: MeshCoreConnection,
    event_type: EventType,
    duration: float,
    *,
    sleep: Callable[[float], Any],
) -> list[dict[str, Any]]:
    """Subscribe to `event_type` for `duration` seconds and return every
    payload received in that window -- for events a one-shot connection has
    to actively wait for (e.g. pending contacts) rather than read from an
    already-accumulated cache. `sleep` is injected so tests can pass a
    zero-delay stand-in instead of really waiting.
    """
    collected: list[dict[str, Any]] = []
    connection.subscribe(event_type, lambda event: collected.append(event.payload))
    await sleep(duration)
    return collected
