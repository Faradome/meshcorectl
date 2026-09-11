"""Translates meshcore Events/payloads into the plain dict shapes
`get`/`describe`/`top` commands hand to `output.render()`.

No Click here: every function takes a `MeshCoreConnection` and is unit
tested directly against `tests/fakes/meshcore_double.py`
(`tests/unit/test_mesh_data.py`), independent of any command wiring.

Field names below (contact/channel/device-info/telemetry keys) come
straight from reading the `meshcore` library's wire-format parser
(`reader.py`) and command modules, not guesswork — see the Phase 2 session
notes for the exact call sites, since there's no protocol spec to cite.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from meshcore import EventType

from .connect import MeshCoreConnection

CONTACT_TYPE_NAMES = {0: "none", 1: "client", 2: "repeater", 3: "room", 4: "sensor"}


class MeshDataError(Exception):
    """A device command returned `EventType.ERROR`, or timed out (returned None)."""


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
    `commands.req_telemetry_sync()` etc. -- no separate "raw contact" shape
    needed."""
    return {
        "name": raw.get("adv_name", ""),
        "type": contact_type_name(raw.get("type", 0)),
        "public_key": raw.get("public_key", ""),
        "path": format_path(raw),
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
    get_contact_by_name/get_contact_by_key_prefix helpers."""
    needle = name_or_prefix.lower()
    for contact in contacts:
        if contact["name"].lower() == needle:
            return contact
    for contact in contacts:
        if contact["public_key"].lower().startswith(needle):
            return contact
    return None


def normalize_channel(raw: dict[str, Any]) -> dict[str, Any]:
    secret = raw.get("channel_secret", b"")
    return {
        "index": raw.get("channel_idx"),
        "name": raw.get("channel_name", ""),
        "secret": secret.hex() if isinstance(secret, (bytes, bytearray)) else secret,
    }


async def fetch_channels(connection: MeshCoreConnection) -> list[dict[str, Any]]:
    """Probe channel slots 0, 1, 2, ... until the device returns an error --
    there's no "how many channels are set" query, so this mirrors the
    original tool's own approach."""
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
    invocation (there's no on-the-fly lookup -- see PLAN.md Decision 1: no
    persistent cache to consult)."""
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
    NO_MORE_MSGS. Mirrors the original tool's `sync_msgs`."""
    messages: list[dict[str, Any]] = []
    while True:
        event = await connection.commands.get_msg()
        if event.type in (EventType.NO_MORE_MSGS, EventType.ERROR):
            break
        messages.append(event.payload)
    return messages


async def collect_events(
    connection: MeshCoreConnection,
    event_type: EventType,
    duration: float,
    *,
    sleep: Callable[[float], Any],
) -> list[dict[str, Any]]:
    """Subscribe to `event_type` for `duration` seconds and return every
    payload received in that window.

    Used for the things the original tool could rely on a long-lived
    session to accumulate (pending contacts) but a one-shot connection
    (PLAN.md Decision 1) has to actively wait for instead. `sleep` is
    injected (rather than hardcoding `asyncio.sleep`) so tests can pass a
    zero-delay stand-in instead of really waiting.
    """
    collected: list[dict[str, Any]] = []
    connection.subscribe(event_type, lambda event: collected.append(event.payload))
    await sleep(duration)
    return collected
