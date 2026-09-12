from __future__ import annotations

import json

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke

CONTACTS_PAYLOAD = {
    "AABB": {"adv_name": "alice", "public_key": "AABB", "type": 1, "out_path_len": -1},
    "CCDD": {"adv_name": "bob", "public_key": "CCDD", "type": 2, "out_path_len": 0},
}


def script_contacts(fake_connection, payload=None):
    if payload is None:
        payload = CONTACTS_PAYLOAD
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, payload))


# --- get device --------------------------------------------------------------


def test_get_device(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query",
        Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114", "ver": "v1.10.0"}),
    )
    result = invoke(runner, configured_store, "get", "device")
    assert result.exit_code == 0, result.output
    assert "T114" in result.output
    assert fake_connection.disconnected is True


def test_get_device_json(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query", Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114"})
    )
    result = invoke(runner, configured_store, "-o", "json", "get", "device")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["model"] == "T114"


def test_get_device_json_output_flag_after_subcommand(runner, configured_store, fake_connection):
    """-o after the subcommand (kubectl's usual `get pods -o json` order),
    found broken (had to precede the subcommand) during live hardware testing."""
    fake_connection.commands.script(
        "send_device_query", Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114"})
    )
    result = invoke(runner, configured_store, "get", "device", "-o", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["model"] == "T114"


def test_get_device_local_output_overrides_global(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query", Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114"})
    )
    result = invoke(runner, configured_store, "-o", "yaml", "get", "device", "-o", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["model"] == "T114"


def test_get_device_error_becomes_click_exception(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_device_query", Event(EventType.ERROR, {"reason": "nope"}))
    result = invoke(runner, configured_store, "get", "device")
    assert result.exit_code != 0
    assert "nope" in result.output


# --- get contacts / contact ---------------------------------------------------


def test_get_contacts_lists_all(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contacts")
    assert result.exit_code == 0, result.output
    header, alice_row, bob_row = result.output.splitlines()
    assert header.split()[:2] == ["NAME", "TYPE"]
    assert "alice" in alice_row and "client" in alice_row
    assert "bob" in bob_row and "repeater" in bob_row


def test_get_contacts_empty_prints_hint(runner, configured_store, fake_connection):
    script_contacts(fake_connection, payload={})
    result = invoke(runner, configured_store, "get", "contacts")
    assert result.exit_code == 0
    assert "No contacts" in result.output


def test_get_contacts_selector_filters(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contacts", "-l", "t=repeater")
    assert result.exit_code == 0, result.output
    assert "bob" in result.output
    assert "alice" not in result.output


def test_get_contacts_selector_matches_none(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contacts", "-l", "t=sensor")
    assert result.exit_code == 0
    assert "No contacts" in result.output


def test_get_contacts_bad_selector_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contacts", "-l", "bogus")
    assert result.exit_code != 0


def test_get_contact_by_name(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contact", "alice")
    assert result.exit_code == 0, result.output
    assert "alice" in result.output


def test_get_contact_by_key_prefix(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contact", "ccdd")
    assert result.exit_code == 0, result.output
    assert "bob" in result.output


def test_get_contact_unknown_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "contact", "nope")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


# --- get channels / channel ----------------------------------------------------


def script_channels(fake_connection):
    public = {"channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00"}
    fdl = {"channel_idx": 1, "channel_name": "#fdl", "channel_secret": b"\x01"}
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, public),
        Event(EventType.CHANNEL_INFO, fdl),
        Event(EventType.ERROR, {"reason": "no such channel"}),
    )


def test_get_channels(runner, configured_store, fake_connection):
    script_channels(fake_connection)
    result = invoke(runner, configured_store, "get", "channels")
    assert result.exit_code == 0, result.output
    assert "public" in result.output
    assert "#fdl" in result.output


def test_get_channels_empty_prints_hint(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_channel", Event(EventType.ERROR, {"reason": "none"}))
    result = invoke(runner, configured_store, "get", "channels")
    assert result.exit_code == 0
    assert "No channels" in result.output


def script_channels_with_empty_slot(fake_connection):
    public = {"channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00"}
    empty = {"channel_idx": 1, "channel_name": "", "channel_secret": b"\x00"}
    fdl = {"channel_idx": 2, "channel_name": "#fdl", "channel_secret": b"\x01"}
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, public),
        Event(EventType.CHANNEL_INFO, empty),
        Event(EventType.CHANNEL_INFO, fdl),
        Event(EventType.ERROR, {"reason": "no such channel"}),
    )


def test_get_channels_hides_empty_slots_by_default(runner, configured_store, fake_connection):
    script_channels_with_empty_slot(fake_connection)
    result = invoke(runner, configured_store, "get", "channels")
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    assert len(lines) == 3  # header + public + #fdl, empty slot 1 excluded
    assert "public" in result.output
    assert "#fdl" in result.output


def test_get_channels_all_includes_empty_slots(runner, configured_store, fake_connection):
    script_channels_with_empty_slot(fake_connection)
    result = invoke(runner, configured_store, "get", "channels", "--all")
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    assert len(lines) == 4  # header + all 3 slots, including the empty one


def test_get_channels_json_hides_empty_slots_by_default(runner, configured_store, fake_connection):
    script_channels_with_empty_slot(fake_connection)
    result = invoke(runner, configured_store, "-o", "json", "get", "channels")
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert all(c["name"] for c in parsed)


def test_get_channels_json_all_includes_empty_slots(runner, configured_store, fake_connection):
    script_channels_with_empty_slot(fake_connection)
    result = invoke(runner, configured_store, "-o", "json", "get", "channels", "--all")
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert len(parsed) == 3
    assert any(c["name"] == "" for c in parsed)


def test_get_channels_all_empty_still_prints_hint(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_channel", Event(EventType.ERROR, {"reason": "none"}))
    result = invoke(runner, configured_store, "get", "channels", "--all")
    assert result.exit_code == 0
    assert "No channels" in result.output
    # --all was already given, so the "pass --all" hint would be redundant/wrong
    assert "pass --all" not in result.output


def test_get_channel_by_index(runner, configured_store, fake_connection):
    script_channels(fake_connection)
    result = invoke(runner, configured_store, "get", "channel", "1")
    assert result.exit_code == 0, result.output
    assert "#fdl" in result.output


def test_get_channel_by_name(runner, configured_store, fake_connection):
    script_channels(fake_connection)
    result = invoke(runner, configured_store, "get", "channel", "public")
    assert result.exit_code == 0, result.output
    assert "public" in result.output


def test_get_channel_unknown_errors(runner, configured_store, fake_connection):
    script_channels(fake_connection)
    result = invoke(runner, configured_store, "get", "channel", "99")
    assert result.exit_code != 0
    assert "no channel matching" in result.output


# --- get path ------------------------------------------------------------------


def test_get_path_flood(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "path", "alice")
    assert result.exit_code == 0, result.output
    assert "flood" in result.output


def test_get_path_direct(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "path", "bob")
    assert result.exit_code == 0, result.output
    assert "direct" in result.output


def test_get_path_unknown_contact_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "get", "path", "nope")
    assert result.exit_code != 0


# --- get time -------------------------------------------------------------------


def test_get_time(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_time", Event(EventType.CURRENT_TIME, {"time": 0}))
    result = invoke(runner, configured_store, "get", "time")
    assert result.exit_code == 0, result.output
    assert "0" in result.output


# --- get pending-contacts ---------------------------------------------------------


async def _immediate_sleep(_duration):
    return None


def test_get_pending_contacts_none_seen(runner, configured_store, fake_connection, monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _immediate_sleep)
    result = invoke(runner, configured_store, "get", "pending-contacts")
    assert result.exit_code == 0
    assert "No pending contacts" in result.output


def test_get_pending_contacts_reports_arrivals(
    runner, configured_store, fake_connection, monkeypatch
):
    async def sleep_and_arrive(_duration):
        carol = {"adv_name": "carol", "public_key": "EE", "type": 1}
        for event_type, handler in fake_connection.subscriptions:
            if event_type == EventType.NEW_CONTACT:
                handler(Event(EventType.NEW_CONTACT, carol))

    monkeypatch.setattr("asyncio.sleep", sleep_and_arrive)
    result = invoke(runner, configured_store, "get", "pending-contacts")
    assert result.exit_code == 0, result.output
    assert "carol" in result.output
