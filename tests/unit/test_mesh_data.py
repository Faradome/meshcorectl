from __future__ import annotations

import pytest
from meshcore import EventType
from meshcore.events import Event

from meshcorectl.mesh_data import (
    MeshDataError,
    collect_events,
    contact_type_name,
    drain_messages,
    fetch_channels,
    fetch_contacts,
    fetch_device,
    fetch_telemetry,
    fetch_telemetry_history,
    fetch_time,
    find_contact,
    format_path,
    normalize_channel,
    normalize_contact,
    normalize_message,
)
from tests.fakes.meshcore_double import FakeMeshCore

# --- contact_type_name / format_path (pure) --------------------------------


def test_contact_type_name_known():
    assert contact_type_name(1) == "client"
    assert contact_type_name(2) == "repeater"
    assert contact_type_name(3) == "room"
    assert contact_type_name(4) == "sensor"


def test_contact_type_name_unknown():
    assert contact_type_name(99) == "unknown(99)"


def test_format_path_flood_when_negative():
    assert format_path({"out_path_len": -1}) == "flood"


def test_format_path_flood_when_missing():
    assert format_path({}) == "flood"


def test_format_path_direct_when_zero():
    assert format_path({"out_path_len": 0}) == "direct"


def test_format_path_hop_list():
    contact = {"out_path_len": 2, "out_path_hash_mode": 0, "out_path": "aabbccdd"}
    assert format_path(contact) == "aa,bb"


def test_format_path_hop_list_wider_hash():
    contact = {"out_path_len": 2, "out_path_hash_mode": 1, "out_path": "aabbccdd"}
    assert format_path(contact) == "aabb,ccdd"


# --- normalize_contact / find_contact ---------------------------------------


def test_normalize_contact_maps_fields():
    raw = {
        "adv_name": "alice",
        "type": 1,
        "public_key": "AABB",
        "out_path_len": -1,
        "last_advert": 100,
        "lastmod": 200,
        "flags": 3,
        "adv_lat": 1.0,
        "adv_lon": 2.0,
    }
    normalized = normalize_contact(raw)
    assert normalized == {
        "name": "alice",
        "type": "client",
        "public_key": "AABB",
        "path": "flood",
        "last_advert": 100,
        "lastmod": 200,
        "flags": 3,
        "adv_lat": 1.0,
        "adv_lon": 2.0,
    }


def test_find_contact_by_name_case_insensitive():
    contacts = [normalize_contact({"adv_name": "Alice", "public_key": "AA11"})]
    assert find_contact(contacts, "alice") is contacts[0]


def test_find_contact_by_public_key_prefix():
    contacts = [normalize_contact({"adv_name": "Alice", "public_key": "AA11BB"})]
    assert find_contact(contacts, "aa11") is contacts[0]


def test_find_contact_not_found():
    contacts = [normalize_contact({"adv_name": "Alice", "public_key": "AA11"})]
    assert find_contact(contacts, "bob") is None


# --- fetch_contacts ----------------------------------------------------------


async def test_fetch_contacts_normalizes_and_sorts():
    fake = FakeMeshCore()
    fake.commands.script(
        "get_contacts",
        Event(
            EventType.CONTACTS,
            {
                "k2": {"adv_name": "zeta", "public_key": "k2", "type": 1},
                "k1": {"adv_name": "alpha", "public_key": "k1", "type": 2},
            },
        ),
    )
    contacts = await fetch_contacts(fake)
    assert [c["name"] for c in contacts] == ["alpha", "zeta"]


async def test_fetch_contacts_raises_on_error_event():
    fake = FakeMeshCore()
    fake.commands.script("get_contacts", Event(EventType.ERROR, {"reason": "nope"}))
    with pytest.raises(MeshDataError, match="nope"):
        await fetch_contacts(fake)


async def test_fetch_contacts_raises_on_timeout():
    fake = FakeMeshCore()
    fake.commands.script("get_contacts", None)
    with pytest.raises(MeshDataError, match="timed out"):
        await fetch_contacts(fake)


# --- normalize_channel / fetch_channels --------------------------------------


def test_normalize_channel_hex_encodes_bytes_secret():
    raw = {"channel_idx": 0, "channel_name": "public", "channel_secret": b"\xaa\xbb"}
    assert normalize_channel(raw) == {"index": 0, "name": "public", "secret": "aabb"}


def test_normalize_channel_passes_through_non_bytes_secret():
    raw = {"channel_idx": 0, "channel_name": "public", "channel_secret": "already-hex"}
    assert normalize_channel(raw)["secret"] == "already-hex"


async def test_fetch_channels_stops_at_first_error():
    fake = FakeMeshCore()
    public = {"channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00"}
    fdl = {"channel_idx": 1, "channel_name": "#fdl", "channel_secret": b"\x01"}
    fake.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, public),
        Event(EventType.CHANNEL_INFO, fdl),
        Event(EventType.ERROR, {"reason": "no such channel"}),
    )
    channels = await fetch_channels(fake)
    assert [c["name"] for c in channels] == ["public", "#fdl"]
    assert fake.commands.call_count("get_channel") == 3


async def test_fetch_channels_empty_when_first_call_errors():
    fake = FakeMeshCore()
    fake.commands.script("get_channel", Event(EventType.ERROR, {"reason": "none set"}))
    assert await fetch_channels(fake) == []


# --- fetch_device -------------------------------------------------------------


async def test_fetch_device_merges_self_info_and_query():
    fake = FakeMeshCore(self_info={"name": "t114", "radio_freq": 869.525})
    query_payload = {"fw ver": 14, "model": "T114", "ver": "v1.10.0"}
    fake.commands.script("send_device_query", Event(EventType.DEVICE_INFO, query_payload))
    device = await fetch_device(fake)
    assert device["name"] == "t114"
    assert device["radio_freq"] == 869.525
    assert device["model"] == "T114"
    assert device["fw ver"] == 14


async def test_fetch_device_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("send_device_query", Event(EventType.ERROR, {"reason": "boom"}))
    with pytest.raises(MeshDataError, match="boom"):
        await fetch_device(fake)


# --- fetch_time ----------------------------------------------------------------


async def test_fetch_time_formats_epoch():
    fake = FakeMeshCore()
    fake.commands.script("get_time", Event(EventType.CURRENT_TIME, {"time": 0}))
    result = await fetch_time(fake)
    assert result["epoch"] == 0
    assert result["time"]  # some formatted string, exact tz-dependent value not asserted


async def test_fetch_time_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("get_time", Event(EventType.ERROR, {"reason": "no clock"}))
    with pytest.raises(MeshDataError, match="no clock"):
        await fetch_time(fake)


# --- telemetry / telemetry history --------------------------------------------


async def test_fetch_telemetry_returns_lpp_list():
    fake = FakeMeshCore()
    reading = [{"channel": 1, "type": "temperature", "value": 21.5}]
    fake.commands.script("req_telemetry_sync", reading)
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    result = await fetch_telemetry(fake, contact)
    assert result == reading


async def test_fetch_telemetry_raises_on_none():
    fake = FakeMeshCore()
    fake.commands.script("req_telemetry_sync", None)
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="timed out requesting telemetry from alice"):
        await fetch_telemetry(fake, contact)


async def test_fetch_telemetry_history_returns_mma_list():
    fake = FakeMeshCore()
    fake.commands.script(
        "req_mma_sync", [{"channel": 1, "type": "temperature", "min": 10, "max": 20, "avg": 15}]
    )
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    result = await fetch_telemetry_history(fake, contact, start=0, end=100)
    assert result[0]["avg"] == 15


async def test_fetch_telemetry_history_raises_on_none():
    fake = FakeMeshCore()
    fake.commands.script("req_mma_sync", None)
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="timed out requesting telemetry history"):
        await fetch_telemetry_history(fake, contact, start=0, end=100)


# --- normalize_message ---------------------------------------------------------


def test_normalize_message_channel_known_name():
    channels = [{"index": 3, "name": "#fdl"}]
    raw = {"type": "CHAN", "channel_idx": 3, "text": "hi"}
    result = normalize_message(raw, channels=channels)
    assert result["name"] == "#fdl"
    assert result["text"] == "hi"


def test_normalize_message_channel_zero_is_public():
    raw = {"type": "CHAN", "channel_idx": 0, "text": "hi"}
    assert normalize_message(raw)["name"] == "public"


def test_normalize_message_channel_unknown_index():
    raw = {"type": "CHAN", "channel_idx": 5, "text": "hi"}
    assert normalize_message(raw)["name"] == "ch5"


def test_normalize_message_private_known_contact():
    contacts = [normalize_contact({"adv_name": "alice", "public_key": "AABBCC"})]
    raw = {"type": "PRIV", "pubkey_prefix": "aabb", "text": "hello"}
    result = normalize_message(raw, contacts=contacts)
    assert result["name"] == "alice"
    assert result["from"] == "alice"


def test_normalize_message_private_unknown_contact_shows_prefix():
    raw = {"type": "PRIV", "pubkey_prefix": "deadbeef", "text": "hello"}
    assert normalize_message(raw)["name"] == "deadbeef"


def test_normalize_message_carries_path_len_and_snr():
    raw = {"type": "CHAN", "channel_idx": 0, "text": "hi", "path_len": 2, "SNR": -4.5}
    result = normalize_message(raw)
    assert result["path_len"] == 2
    assert result["SNR"] == -4.5


# --- drain_messages -------------------------------------------------------------


async def test_drain_messages_stops_at_no_more_msgs():
    fake = FakeMeshCore()
    fake.commands.script(
        "get_msg",
        Event(EventType.CONTACT_MSG_RECV, {"text": "one"}),
        Event(EventType.CONTACT_MSG_RECV, {"text": "two"}),
        Event(EventType.NO_MORE_MSGS, {}),
    )
    messages = await drain_messages(fake)
    assert [m["text"] for m in messages] == ["one", "two"]


async def test_drain_messages_stops_at_error():
    fake = FakeMeshCore()
    fake.commands.script(
        "get_msg",
        Event(EventType.CONTACT_MSG_RECV, {"text": "one"}),
        Event(EventType.ERROR, {"reason": "disconnected"}),
    )
    messages = await drain_messages(fake)
    assert [m["text"] for m in messages] == ["one"]


async def test_drain_messages_empty_when_none_queued():
    fake = FakeMeshCore()
    fake.commands.script("get_msg", Event(EventType.NO_MORE_MSGS, {}))
    assert await drain_messages(fake) == []


# --- collect_events ---------------------------------------------------------------


async def test_collect_events_gathers_payloads_over_the_window():
    fake = FakeMeshCore()
    sleep_calls = []

    async def fake_sleep(duration):
        sleep_calls.append(duration)
        # Simulate an event arriving during the window by invoking the
        # handler the real dispatcher would have called.
        for event_type, handler in fake.subscriptions:
            if event_type == EventType.NEW_CONTACT:
                handler(Event(EventType.NEW_CONTACT, {"adv_name": "bob"}))

    collected = await collect_events(fake, EventType.NEW_CONTACT, 5.0, sleep=fake_sleep)
    assert collected == [{"adv_name": "bob"}]
    assert sleep_calls == [5.0]


async def test_collect_events_empty_when_nothing_arrives():
    fake = FakeMeshCore()

    async def fake_sleep(duration):
        return None

    collected = await collect_events(fake, EventType.NEW_CONTACT, 1.0, sleep=fake_sleep)
    assert collected == []
