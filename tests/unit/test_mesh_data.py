from __future__ import annotations

import logging

import pytest
from meshcore import EventType
from meshcore.events import Event

from meshcorectl.mesh_data import (
    DEVICE_PARAMS,
    AmbiguousMatchError,
    MeshDataError,
    collect_events,
    contact_type_name,
    create_channel,
    delete_channel,
    drain_messages,
    fetch_channels,
    fetch_contacts,
    fetch_device,
    fetch_telemetry,
    fetch_telemetry_history,
    fetch_time,
    find_channel,
    find_contact,
    format_path,
    import_contact,
    login,
    logout,
    normalize_channel,
    normalize_contact,
    normalize_message,
    reboot_device,
    remove_contact,
    run_repeater_command,
    run_trace,
    send_advert,
    send_channel_message,
    send_message,
    set_device_param,
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
        "hops": -1,
        "last_advert": 100,
        "lastmod": 200,
        "flags": 3,
        "adv_lat": 1.0,
        "adv_lon": 2.0,
    }


def test_normalize_contact_hops_defaults_to_flood():
    assert normalize_contact({"adv_name": "a", "public_key": "AA"})["hops"] == -1


def test_normalize_contact_hops_direct():
    raw = {"adv_name": "a", "public_key": "AA", "out_path_len": 0}
    assert normalize_contact(raw)["hops"] == 0


def test_find_contact_by_name_case_insensitive():
    contacts = [normalize_contact({"adv_name": "Alice", "public_key": "AA11"})]
    assert find_contact(contacts, "alice") is contacts[0]


def test_find_contact_by_public_key_prefix():
    contacts = [normalize_contact({"adv_name": "Alice", "public_key": "AA11BB"})]
    assert find_contact(contacts, "aa11") is contacts[0]


def test_find_contact_not_found():
    contacts = [normalize_contact({"adv_name": "Alice", "public_key": "AA11"})]
    assert find_contact(contacts, "bob") is None


def test_find_contact_ambiguous_name_raises():
    contacts = [
        normalize_contact({"adv_name": "dup", "public_key": "AA11"}),
        normalize_contact({"adv_name": "dup", "public_key": "BB22"}),
    ]
    with pytest.raises(AmbiguousMatchError, match="matches 2 contacts by name"):
        find_contact(contacts, "dup")


def test_find_contact_ambiguous_public_key_prefix_raises():
    contacts = [
        normalize_contact({"adv_name": "alice", "public_key": "AABBCC"}),
        normalize_contact({"adv_name": "bob", "public_key": "AABBDD"}),
    ]
    with pytest.raises(AmbiguousMatchError, match="matches 2 contacts by public-key prefix"):
        find_contact(contacts, "aabb")


def test_find_contact_unambiguous_prefix_still_works_alongside_others():
    """A prefix that narrows to exactly one contact must not be treated as
    ambiguous just because other, non-matching contacts also exist."""
    contacts = [
        normalize_contact({"adv_name": "alice", "public_key": "AABBCC"}),
        normalize_contact({"adv_name": "bob", "public_key": "112233"}),
    ]
    assert find_contact(contacts, "aabb") is contacts[0]


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


# --- find_channel --------------------------------------------------------------


def test_find_channel_by_index():
    channels = [{"index": 0, "name": "public"}, {"index": 1, "name": "#fdl"}]
    assert find_channel(channels, "1") == {"index": 1, "name": "#fdl"}


def test_find_channel_by_name_case_insensitive():
    channels = [{"index": 0, "name": "Public"}]
    assert find_channel(channels, "public") == {"index": 0, "name": "Public"}


def test_find_channel_not_found():
    assert find_channel([{"index": 0, "name": "public"}], "nope") is None


# --- import_contact / remove_contact --------------------------------------------


async def test_import_contact_sends_decoded_hex():
    fake = FakeMeshCore()
    fake.commands.script("import_contact", Event(EventType.OK, {}))
    await import_contact(fake, "meshcore://aabbcc")
    assert fake.commands.calls == [("import_contact", (b"\xaa\xbb\xcc",), {})]


async def test_import_contact_rejects_wrong_scheme():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="not a meshcore contact URI"):
        await import_contact(fake, "http://example.com")


async def test_import_contact_rejects_bad_hex():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="invalid hex"):
        await import_contact(fake, "meshcore://zzzz")


async def test_import_contact_raises_on_device_error():
    fake = FakeMeshCore()
    fake.commands.script("import_contact", Event(EventType.ERROR, {"reason": "full"}))
    with pytest.raises(MeshDataError, match="full"):
        await import_contact(fake, "meshcore://aabb")


async def test_remove_contact_calls_through():
    fake = FakeMeshCore()
    fake.commands.script("remove_contact", Event(EventType.OK, {}))
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    await remove_contact(fake, contact)
    assert fake.commands.calls == [("remove_contact", (contact,), {})]


async def test_remove_contact_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("remove_contact", Event(EventType.ERROR, {"reason": "nope"}))
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="nope"):
        await remove_contact(fake, contact)


# --- create_channel / delete_channel -----------------------------------------------


async def test_create_channel_with_explicit_secret():
    fake = FakeMeshCore()
    fake.commands.script("set_channel", Event(EventType.OK, {}))
    confirmed = {"channel_idx": 3, "channel_name": "#fdl", "channel_secret": b"\x01" * 16}
    fake.commands.script("get_channel", Event(EventType.CHANNEL_INFO, confirmed))
    result = await create_channel(fake, 3, "#fdl", "01" * 16)
    assert result == {"index": 3, "name": "#fdl", "secret": "01" * 16}
    assert fake.commands.calls[0] == ("set_channel", (3, "#fdl", b"\x01" * 16), {})


async def test_create_channel_without_secret_lets_device_derive_it():
    fake = FakeMeshCore()
    fake.commands.script("set_channel", Event(EventType.OK, {}))
    confirmed = {"channel_idx": 3, "channel_name": "#fdl", "channel_secret": b"\x00"}
    fake.commands.script("get_channel", Event(EventType.CHANNEL_INFO, confirmed))
    await create_channel(fake, 3, "#fdl", None)
    assert fake.commands.calls[0] == ("set_channel", (3, "#fdl", None), {})


async def test_create_channel_rejects_wrong_length_secret():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="32 hex characters"):
        await create_channel(fake, 3, "#fdl", "abcd")


async def test_create_channel_rejects_bad_hex_secret():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="invalid hex"):
        await create_channel(fake, 3, "#fdl", "zz" * 16)


async def test_create_channel_without_secret_generates_random_key_for_non_hash_name():
    """Only a '#'-prefixed name is the public/derived-key convention -- any
    other name is meant to be private, so letting set_channel's own
    name-derived fallback run (as for '#fdl' above) would make it just as
    guessable as a public channel. meshcorectl must generate a real random
    secret itself instead of passing secret=None through."""
    fake = FakeMeshCore()
    fake.commands.script("set_channel", Event(EventType.OK, {}))
    confirmed = {"channel_idx": 3, "channel_name": "private", "channel_secret": b"\xaa" * 16}
    fake.commands.script("get_channel", Event(EventType.CHANNEL_INFO, confirmed))
    await create_channel(fake, 3, "private", None)
    method, args, kwargs = fake.commands.calls[0]
    assert method == "set_channel"
    _, name, secret = args
    assert name == "private"
    assert isinstance(secret, bytes)
    assert len(secret) == 16
    assert secret != bytes(16)  # a real random draw, not an all-zero placeholder


async def test_create_channel_without_secret_generates_a_different_key_each_call():
    fake = FakeMeshCore()
    confirmed = {"channel_idx": 3, "channel_name": "private", "channel_secret": b"\x00"}
    generated = []
    for _ in range(2):
        fake.commands.script("set_channel", Event(EventType.OK, {}))
        fake.commands.script("get_channel", Event(EventType.CHANNEL_INFO, confirmed))
        await create_channel(fake, 3, "private", None)
        # calls == [..., ("set_channel", (3, "private", secret), {}), ("get_channel", (3,), {})]
        generated.append(fake.commands.calls[-2][1][2])
    assert generated[0] != generated[1]


async def test_create_channel_raises_on_set_error():
    fake = FakeMeshCore()
    fake.commands.script("set_channel", Event(EventType.ERROR, {"reason": "full"}))
    with pytest.raises(MeshDataError, match="full"):
        await create_channel(fake, 3, "#fdl", None)


async def test_delete_channel_clears_name_and_zeroes_secret():
    fake = FakeMeshCore()
    fake.commands.script("set_channel", Event(EventType.OK, {}))
    await delete_channel(fake, 3)
    assert fake.commands.calls == [("set_channel", (3, "", bytes(16)), {})]


async def test_delete_channel_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("set_channel", Event(EventType.ERROR, {"reason": "nope"}))
    with pytest.raises(MeshDataError, match="nope"):
        await delete_channel(fake, 3)


# --- send_message / send_channel_message -----------------------------------------


async def test_send_message_without_wait_ack():
    fake = FakeMeshCore()
    fake.commands.script("send_msg", Event(EventType.MSG_SENT, {}))
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    result = await send_message(fake, contact, "hi", wait_ack=False)
    assert result == {"sent": True}
    assert fake.commands.call_count("send_msg_with_retry") == 0


async def test_send_message_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("send_msg", Event(EventType.ERROR, {"reason": "nope"}))
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="nope"):
        await send_message(fake, contact, "hi", wait_ack=False)


async def test_send_message_with_wait_ack_success():
    fake = FakeMeshCore()
    fake.commands.script("send_msg_with_retry", Event(EventType.ACK, {"code": "abcd"}))
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    result = await send_message(fake, contact, "hi", wait_ack=True)
    assert result == {"sent": True, "acked": True}


async def test_send_message_with_wait_ack_timeout_raises():
    fake = FakeMeshCore()
    fake.commands.script("send_msg_with_retry", None)
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="no ack received"):
        await send_message(fake, contact, "hi", wait_ack=True)


async def test_send_channel_message():
    fake = FakeMeshCore()
    fake.commands.script("send_chan_msg", Event(EventType.MSG_SENT, {}))
    channel = {"index": 2, "name": "#fdl"}
    result = await send_channel_message(fake, channel, "hi")
    assert result == {"sent": True}
    assert fake.commands.calls == [("send_chan_msg", (2, "hi"), {})]


async def test_send_channel_message_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("send_chan_msg", Event(EventType.ERROR, {"reason": "nope"}))
    with pytest.raises(MeshDataError, match="nope"):
        await send_channel_message(fake, {"index": 0, "name": "public"}, "hi")


async def test_send_channel_message_with_scope_sets_and_resets_flood_scope():
    # Channels carry no scope of their own (CHANNEL_INFO has no such field),
    # so a scope is a device-wide setting applied around this one send.
    fake = FakeMeshCore()
    fake.commands.script("set_flood_scope", Event(EventType.OK, {}))
    fake.commands.script("send_chan_msg", Event(EventType.MSG_SENT, {}))
    fake.commands.script("reset_flood_scope", Event(EventType.OK, {}))
    channel = {"index": 2, "name": "#fdl"}
    result = await send_channel_message(fake, channel, "hi", scope="rescue")
    assert result == {"sent": True}
    assert fake.commands.calls == [
        ("set_flood_scope", ("rescue",), {}),
        ("send_chan_msg", (2, "hi"), {}),
        ("reset_flood_scope", (), {}),
    ]


async def test_send_channel_message_without_scope_does_not_touch_flood_scope():
    fake = FakeMeshCore()
    fake.commands.script("send_chan_msg", Event(EventType.MSG_SENT, {}))
    channel = {"index": 2, "name": "#fdl"}
    await send_channel_message(fake, channel, "hi")
    assert fake.commands.call_count("set_flood_scope") == 0
    assert fake.commands.call_count("reset_flood_scope") == 0


async def test_send_channel_message_resets_flood_scope_even_on_send_error():
    fake = FakeMeshCore()
    fake.commands.script("set_flood_scope", Event(EventType.OK, {}))
    fake.commands.script("send_chan_msg", Event(EventType.ERROR, {"reason": "nope"}))
    fake.commands.script("reset_flood_scope", Event(EventType.OK, {}))
    with pytest.raises(MeshDataError, match="nope"):
        await send_channel_message(fake, {"index": 0, "name": "public"}, "hi", scope="rescue")
    assert fake.commands.call_count("reset_flood_scope") == 1


async def test_send_channel_message_raises_if_setting_scope_fails():
    fake = FakeMeshCore()
    fake.commands.script("set_flood_scope", Event(EventType.ERROR, {"reason": "bad scope"}))
    with pytest.raises(MeshDataError, match="bad scope"):
        await send_channel_message(fake, {"index": 0, "name": "public"}, "hi", scope="rescue")
    assert fake.commands.call_count("send_chan_msg") == 0


async def test_send_message_redacts_meshcore_logger_during_the_send(meshcore_logger_at_debug):
    # M1 fix: the `meshcore` library debug-logs message text -- confirm
    # `-vv` (a DEBUG-level "meshcore" logger) doesn't see it.
    fake = FakeMeshCore()
    observed_levels: list[int] = []

    async def spy_send_msg(contact, text):
        observed_levels.append(meshcore_logger_at_debug.level)
        return Event(EventType.MSG_SENT, {})

    fake.commands.send_msg = spy_send_msg
    contact = normalize_contact({"adv_name": "alice", "public_key": "AA"})

    result = await send_message(fake, contact, "hi", wait_ack=False)

    assert result == {"sent": True}
    assert observed_levels == [logging.INFO]
    assert meshcore_logger_at_debug.level == logging.DEBUG  # restored after the call


async def test_send_channel_message_redacts_meshcore_logger_during_the_send(
    meshcore_logger_at_debug,
):
    fake = FakeMeshCore()
    observed_levels: list[int] = []

    async def spy_send_chan_msg(index, text):
        observed_levels.append(meshcore_logger_at_debug.level)
        return Event(EventType.MSG_SENT, {})

    fake.commands.send_chan_msg = spy_send_chan_msg

    result = await send_channel_message(fake, {"index": 0, "name": "public"}, "hi")

    assert result == {"sent": True}
    assert observed_levels == [logging.INFO]
    assert meshcore_logger_at_debug.level == logging.DEBUG


# --- run_repeater_command (exec) -------------------------------------------------


async def test_run_repeater_command_returns_reply_text():
    fake = FakeMeshCore()
    fake.commands.script("send_cmd", Event(EventType.MSG_SENT, {}))
    fake.script_wait_for_event(Event(EventType.MESSAGES_WAITING, {}))
    fake.commands.script("get_msg", Event(EventType.CONTACT_MSG_RECV, {"text": "ok"}))
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    reply = await run_repeater_command(fake, contact, "ver", timeout=5)
    assert reply == "ok"


async def test_run_repeater_command_returns_none_on_no_reply():
    fake = FakeMeshCore()
    fake.commands.script("send_cmd", Event(EventType.MSG_SENT, {}))
    fake.script_wait_for_event(None)
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    reply = await run_repeater_command(fake, contact, "ver", timeout=5)
    assert reply is None


async def test_run_repeater_command_raises_on_send_error():
    fake = FakeMeshCore()
    fake.commands.script("send_cmd", Event(EventType.ERROR, {"reason": "nope"}))
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="nope"):
        await run_repeater_command(fake, contact, "ver", timeout=5)


# --- login / logout -----------------------------------------------------------------


async def test_login_success():
    fake = FakeMeshCore()
    fake.commands.script("send_login_sync", Event(EventType.LOGIN_SUCCESS, {}))
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    assert await login(fake, contact, "secret", timeout=5) is True


async def test_login_failure():
    fake = FakeMeshCore()
    fake.commands.script("send_login_sync", Event(EventType.LOGIN_FAILED, {}))
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    assert await login(fake, contact, "wrong", timeout=5) is False


async def test_login_timeout_raises():
    fake = FakeMeshCore()
    fake.commands.script("send_login_sync", None)
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="timed out"):
        await login(fake, contact, "secret", timeout=5)


async def test_login_redacts_meshcore_logger_during_the_send(meshcore_logger_at_debug):
    # M1 fix: the `meshcore` library debug-logs the password itself (both
    # the login request and the raw outbound frame) -- confirm `-vv` (a
    # DEBUG-level "meshcore" logger) doesn't see it.
    fake = FakeMeshCore()
    observed_levels: list[int] = []

    async def spy_send_login_sync(contact, password, timeout):
        observed_levels.append(meshcore_logger_at_debug.level)
        return Event(EventType.LOGIN_SUCCESS, {})

    fake.commands.send_login_sync = spy_send_login_sync
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})

    assert await login(fake, contact, "hunter2", timeout=5) is True
    assert observed_levels == [logging.INFO]
    assert meshcore_logger_at_debug.level == logging.DEBUG  # restored after the call


async def test_logout_calls_through():
    fake = FakeMeshCore()
    fake.commands.script("send_logout", Event(EventType.OK, {}))
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    await logout(fake, contact)
    assert fake.commands.calls == [("send_logout", (contact,), {})]


async def test_logout_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("send_logout", Event(EventType.ERROR, {"reason": "nope"}))
    contact = normalize_contact({"adv_name": "rep1", "public_key": "AA"})
    with pytest.raises(MeshDataError, match="nope"):
        await logout(fake, contact)


# --- send_advert / reboot_device ------------------------------------------------------


async def test_send_advert_default_not_flood():
    fake = FakeMeshCore()
    fake.commands.script("send_advert", Event(EventType.OK, {}))
    await send_advert(fake, flood=False)
    assert fake.commands.calls == [("send_advert", (), {"flood": False})]


async def test_send_advert_flood():
    fake = FakeMeshCore()
    fake.commands.script("send_advert", Event(EventType.OK, {}))
    await send_advert(fake, flood=True)
    assert fake.commands.calls == [("send_advert", (), {"flood": True})]


async def test_send_advert_raises_on_error():
    fake = FakeMeshCore()
    fake.commands.script("send_advert", Event(EventType.ERROR, {"reason": "nope"}))
    with pytest.raises(MeshDataError, match="nope"):
        await send_advert(fake, flood=False)


async def test_reboot_device_calls_through_without_checking_result():
    fake = FakeMeshCore()
    fake.commands.script("reboot", Event(EventType.ERROR, {"reason": "connection dropped"}))
    await reboot_device(fake)  # must not raise, even on an ERROR-shaped result
    assert fake.commands.calls == [("reboot", (), {})]


# --- run_trace ------------------------------------------------------------------------


async def test_run_trace_returns_path_on_reply():
    fake = FakeMeshCore()
    sent_payload = {"expected_ack": (5).to_bytes(4, "little"), "suggested_timeout": 1000}
    fake.commands.script("send_trace", Event(EventType.MSG_SENT, sent_payload))
    fake.script_wait_for_event(
        Event(EventType.TRACE_DATA, {"path": [{"snr": 8.0}, {"snr": -2.0}]})
    )
    result = await run_trace(fake, "23,5f")
    assert result == [{"snr": 8.0}, {"snr": -2.0}]
    # the tag used to wait for the reply matches the sent packet's expected_ack
    assert fake.wait_for_event_calls[0][1] == {"tag": 5}


async def test_run_trace_uses_explicit_timeout_when_given():
    fake = FakeMeshCore()
    sent_payload = {"expected_ack": (1).to_bytes(4, "little"), "suggested_timeout": 1000}
    fake.commands.script("send_trace", Event(EventType.MSG_SENT, sent_payload))
    fake.script_wait_for_event(Event(EventType.TRACE_DATA, {"path": []}))
    await run_trace(fake, "23", timeout=9.0)
    assert fake.wait_for_event_calls[0][2] == 9.0


async def test_run_trace_raises_on_send_error():
    fake = FakeMeshCore()
    fake.commands.script("send_trace", Event(EventType.ERROR, {"reason": "bad path"}))
    with pytest.raises(MeshDataError, match="bad path"):
        await run_trace(fake, "zz")


async def test_run_trace_raises_on_timeout():
    fake = FakeMeshCore()
    sent_payload = {"expected_ack": (1).to_bytes(4, "little"), "suggested_timeout": 1000}
    fake.commands.script("send_trace", Event(EventType.MSG_SENT, sent_payload))
    fake.script_wait_for_event(None)
    with pytest.raises(MeshDataError, match="timed out waiting for a trace reply"):
        await run_trace(fake, "23")


async def test_run_trace_raises_on_error_event():
    fake = FakeMeshCore()
    sent_payload = {"expected_ack": (1).to_bytes(4, "little"), "suggested_timeout": 1000}
    fake.commands.script("send_trace", Event(EventType.MSG_SENT, sent_payload))
    fake.script_wait_for_event(Event(EventType.ERROR, {"reason": "no route"}))
    with pytest.raises(MeshDataError, match="no route"):
        await run_trace(fake, "23")


# --- set_device_param ------------------------------------------------------------------


async def test_set_device_param_name():
    fake = FakeMeshCore()
    fake.commands.script("set_name", Event(EventType.OK, {}))
    await set_device_param(fake, "name", "new-name")
    assert fake.commands.calls == [("set_name", ("new-name",), {})]


async def test_set_device_param_tx_power_parses_int():
    fake = FakeMeshCore()
    fake.commands.script("set_tx_power", Event(EventType.OK, {}))
    await set_device_param(fake, "tx-power", "22")
    assert fake.commands.calls == [("set_tx_power", (22,), {})]


async def test_set_device_param_coords_parses_pair():
    fake = FakeMeshCore()
    fake.commands.script("set_coords", Event(EventType.OK, {}))
    await set_device_param(fake, "coords", "47.5,-3.4")
    assert fake.commands.calls == [("set_coords", (47.5, -3.4), {})]


async def test_set_device_param_coords_rejects_bad_format():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="invalid value"):
        await set_device_param(fake, "coords", "not-coords")


@pytest.mark.parametrize(
    ("text", "expected"), [("on", True), ("off", False), ("yes", True), ("no", False)]
)
async def test_set_device_param_manual_add_contacts_bool(text, expected):
    fake = FakeMeshCore()
    fake.commands.script("set_manual_add_contacts", Event(EventType.OK, {}))
    await set_device_param(fake, "manual-add-contacts", text)
    assert fake.commands.calls == [("set_manual_add_contacts", (expected,), {})]


async def test_set_device_param_bool_rejects_garbage():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="invalid value"):
        await set_device_param(fake, "manual-add-contacts", "maybe")


async def test_set_device_param_unknown_param_raises():
    fake = FakeMeshCore()
    with pytest.raises(MeshDataError, match="unknown device parameter"):
        await set_device_param(fake, "bogus", "1")


async def test_set_device_param_raises_on_device_error():
    fake = FakeMeshCore()
    fake.commands.script("set_tx_power", Event(EventType.ERROR, {"reason": "out of range"}))
    with pytest.raises(MeshDataError, match="out of range"):
        await set_device_param(fake, "tx-power", "99")


async def test_set_device_param_pin_parses_int():
    fake = FakeMeshCore()
    fake.commands.script("set_devicepin", Event(EventType.OK, {}))
    await set_device_param(fake, "pin", "1234")
    assert fake.commands.calls == [("set_devicepin", (1234,), {})]


async def test_set_device_param_pin_redacts_meshcore_logger_during_the_send(
    meshcore_logger_at_debug,
):
    # M1 fix: the `meshcore` library debug-logs "Setting device PIN to:
    # <pin>" -- confirm `-vv` (a DEBUG-level "meshcore" logger) doesn't see it.
    fake = FakeMeshCore()
    observed_levels: list[int] = []

    async def spy_set_devicepin(pin):
        observed_levels.append(meshcore_logger_at_debug.level)
        return Event(EventType.OK, {})

    fake.commands.set_devicepin = spy_set_devicepin

    await set_device_param(fake, "pin", "1234")

    assert observed_levels == [logging.INFO]
    assert meshcore_logger_at_debug.level == logging.DEBUG


def test_device_params_lists_every_known_setter():
    assert "name" in DEVICE_PARAMS
    assert "coords" in DEVICE_PARAMS
    assert list(DEVICE_PARAMS) == sorted(DEVICE_PARAMS)
