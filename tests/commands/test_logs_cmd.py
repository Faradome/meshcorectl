from __future__ import annotations

import asyncio
import json
import time

import pytest
import yaml
from meshcore import EventType
from meshcore.events import Event

from meshcorectl.commands.logs import wait_until_interrupted
from tests.conftest import invoke


def script_no_contacts_or_channels(fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, {}))
    fake_connection.commands.script("get_channel", Event(EventType.ERROR, {"reason": "none"}))


def test_logs_drains_queued_messages(runner, configured_store, fake_connection):
    script_no_contacts_or_channels(fake_connection)
    fake_connection.commands.script(
        "get_msg",
        Event(EventType.CHANNEL_MSG_RECV, {"type": "CHAN", "channel_idx": 0, "text": "hello"}),
        Event(EventType.NO_MORE_MSGS, {}),
    )
    result = invoke(runner, configured_store, "logs")
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "public: hello"


def test_logs_no_messages_prints_nothing(runner, configured_store, fake_connection):
    script_no_contacts_or_channels(fake_connection)
    fake_connection.commands.script("get_msg", Event(EventType.NO_MORE_MSGS, {}))
    result = invoke(runner, configured_store, "logs")
    assert result.exit_code == 0
    assert result.output == ""


async def test_wait_until_interrupted_really_blocks():
    """Exercises the real (un-monkeypatched) function: proves it never
    resolves on its own, without hanging the test suite forever."""
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(wait_until_interrupted(), timeout=0.01)


def test_logs_yaml_output(runner, configured_store, fake_connection):
    script_no_contacts_or_channels(fake_connection)
    fake_connection.commands.script(
        "get_msg",
        Event(EventType.CHANNEL_MSG_RECV, {"type": "CHAN", "channel_idx": 0, "text": "hi"}),
        Event(EventType.NO_MORE_MSGS, {}),
    )
    result = invoke(runner, configured_store, "-o", "yaml", "logs")
    assert result.exit_code == 0, result.output
    parsed = yaml.safe_load(result.output)
    assert parsed["text"] == "hi"
    assert parsed["name"] == "public"


def test_logs_json_output(runner, configured_store, fake_connection):
    script_no_contacts_or_channels(fake_connection)
    fake_connection.commands.script(
        "get_msg",
        Event(EventType.CHANNEL_MSG_RECV, {"type": "CHAN", "channel_idx": 0, "text": "hi"}),
        Event(EventType.NO_MORE_MSGS, {}),
    )
    result = invoke(runner, configured_store, "-o", "json", "logs")
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["text"] == "hi"
    assert parsed["name"] == "public"


def test_logs_since_filters_out_old_messages(runner, configured_store, fake_connection):
    script_no_contacts_or_channels(fake_connection)
    old_msg = {
        "type": "CHAN",
        "channel_idx": 0,
        "text": "old",
        "sender_timestamp": time.time() - 7200,
    }
    new_msg = {"type": "CHAN", "channel_idx": 0, "text": "new", "sender_timestamp": time.time()}
    fake_connection.commands.script(
        "get_msg",
        Event(EventType.CHANNEL_MSG_RECV, old_msg),
        Event(EventType.CHANNEL_MSG_RECV, new_msg),
        Event(EventType.NO_MORE_MSGS, {}),
    )
    result = invoke(runner, configured_store, "logs", "--since", "1h")
    assert result.exit_code == 0, result.output
    assert "old" not in result.output
    assert "new" in result.output


def test_logs_since_rejects_bad_duration(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "logs", "--since", "nonsense")
    assert result.exit_code != 0
    assert "invalid duration" in result.output


def test_logs_rx_without_follow_is_rejected(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "logs", "--rx")
    assert result.exit_code != 0
    assert "--rx has no effect without --follow" in result.output


def test_logs_follow_subscribes_and_prints_live_messages(
    runner, configured_store, fake_connection, monkeypatch
):
    script_no_contacts_or_channels(fake_connection)
    fake_connection.commands.script("get_msg", Event(EventType.NO_MORE_MSGS, {}))

    async def fake_wait():
        # Simulate a message arriving while "following", by directly
        # invoking whichever handler(s) got subscribed.
        for event_type, handler in fake_connection.subscriptions:
            if event_type == EventType.CONTACT_MSG_RECV:
                handler(
                    Event(
                        EventType.CONTACT_MSG_RECV,
                        {"type": "PRIV", "pubkey_prefix": "deadbeef", "text": "live"},
                    )
                )

    monkeypatch.setattr("meshcorectl.commands.logs.wait_until_interrupted", fake_wait)
    result = invoke(runner, configured_store, "logs", "--follow")
    assert result.exit_code == 0, result.output
    assert "deadbeef: live" in result.output


def test_logs_rx_follow_prints_raw_payloads(runner, configured_store, fake_connection, monkeypatch):
    async def fake_wait():
        for event_type, handler in fake_connection.subscriptions:
            if event_type == EventType.RX_LOG_DATA:
                handler(Event(EventType.RX_LOG_DATA, {"snr": -4.5, "raw": "aabb"}))

    monkeypatch.setattr("meshcorectl.commands.logs.wait_until_interrupted", fake_wait)
    result = invoke(runner, configured_store, "logs", "--follow", "--rx")
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output.strip())
    assert parsed == {"snr": -4.5, "raw": "aabb"}
    # --rx never touches contacts/channels (no lookup needed for raw packets)
    assert fake_connection.commands.call_count("get_contacts") == 0
