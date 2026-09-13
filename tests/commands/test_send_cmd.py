from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke

CONTACTS_PAYLOAD = {
    "AA": {"adv_name": "alice", "public_key": "AA", "type": 1, "out_path_len": -1, "lastmod": 1},
}


def script_contacts(fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, CONTACTS_PAYLOAD))


def test_send_message_by_name(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_msg", Event(EventType.MSG_SENT, {}))
    result = invoke(runner, configured_store, "send", "message", "alice", "hi")
    assert result.exit_code == 0, result.output
    assert "sent" in result.output and "alice" in result.output


def test_send_message_unknown_contact_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "send", "message", "nope", "hi")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_send_message_ambiguous_name_errors(runner, configured_store, fake_connection):
    dup_payload = {
        "AA": {"adv_name": "dup", "public_key": "AA11", "type": 1, "out_path_len": -1},
        "BB": {"adv_name": "dup", "public_key": "BB22", "type": 1, "out_path_len": -1},
    }
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, dup_payload))
    result = invoke(runner, configured_store, "send", "message", "dup", "hi")
    assert result.exit_code != 0
    assert "matches 2 contacts" in result.output


def test_send_message_requires_contact_or_selector(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "send", "message", "hi")
    assert result.exit_code != 0
    assert "pass CONTACT and TEXT" in result.output


def test_send_message_unquoted_multi_word_text_is_joined(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_msg", Event(EventType.MSG_SENT, {}))
    result = invoke(runner, configured_store, "send", "message", "alice", "hello", "there")
    assert result.exit_code == 0, result.output
    send_call = next(c for c in fake_connection.commands.calls if c[0] == "send_msg")
    assert send_call[1][1] == "hello there"


def test_send_message_wait_ack(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_msg_with_retry", Event(EventType.ACK, {"code": "x"}))
    result = invoke(runner, configured_store, "send", "message", "alice", "hi", "--wait-ack")
    assert result.exit_code == 0, result.output
    assert "acked" in result.output


def test_send_message_wait_ack_timeout_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_msg_with_retry", None)
    result = invoke(runner, configured_store, "send", "message", "alice", "hi", "--wait-ack")
    assert result.exit_code != 0
    assert "no ack received" in result.output


def test_send_message_by_selector(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_msg", Event(EventType.MSG_SENT, {}))
    result = invoke(runner, configured_store, "send", "message", "-l", "t=1", "hi")
    assert result.exit_code == 0, result.output
    assert "alice" in result.output


def test_send_message_selector_matches_none(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "send", "message", "-l", "t=4", "hi")
    assert result.exit_code == 0
    assert "No contacts matched" in result.output


def test_send_message_selector_with_no_text_errors(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "send", "message", "-l", "t=1")
    assert result.exit_code != 0
    assert "pass CONTACT and TEXT" in result.output


def test_send_message_bad_selector_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "send", "message", "-l", "bogus", "hi")
    assert result.exit_code != 0


def test_send_message_dry_run(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "send", "message", "alice", "hi", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would send" in result.output
    assert fake_connection.commands.call_count("send_msg") == 0


def test_send_channel(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, {
            "channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00",
        }),
        Event(EventType.ERROR, {"reason": "none"}),
    )
    fake_connection.commands.script("send_chan_msg", Event(EventType.MSG_SENT, {}))
    result = invoke(runner, configured_store, "send", "channel", "0", "hi")
    assert result.exit_code == 0, result.output
    assert "public" in result.output


def test_send_channel_unknown_errors(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_channel", Event(EventType.ERROR, {"reason": "none"}))
    result = invoke(runner, configured_store, "send", "channel", "5", "hi")
    assert result.exit_code != 0
    assert "no channel matching" in result.output


def test_send_channel_dry_run(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, {
            "channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00",
        }),
        Event(EventType.ERROR, {"reason": "none"}),
    )
    result = invoke(runner, configured_store, "send", "channel", "0", "hi", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would send" in result.output
    assert fake_connection.commands.call_count("send_chan_msg") == 0


def test_send_channel_with_scope(runner, configured_store, fake_connection):
    # Channels don't store a scope, so --scope has to go through the
    # device-wide flood-scope commands around the send.
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, {
            "channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00",
        }),
        Event(EventType.ERROR, {"reason": "none"}),
    )
    fake_connection.commands.script("set_flood_scope", Event(EventType.OK, {}))
    fake_connection.commands.script("send_chan_msg", Event(EventType.MSG_SENT, {}))
    fake_connection.commands.script("reset_flood_scope", Event(EventType.OK, {}))
    result = invoke(
        runner, configured_store, "send", "channel", "0", "hi", "--scope", "rescue"
    )
    assert result.exit_code == 0, result.output
    assert "public" in result.output
    assert fake_connection.commands.calls == [
        ("get_channel", (0,), {}),
        ("get_channel", (1,), {}),  # fetch_channels probes one past the last channel
        ("set_flood_scope", ("rescue",), {}),
        ("send_chan_msg", (0, "hi"), {}),
        ("reset_flood_scope", (), {}),
    ]


def test_send_channel_dry_run_with_scope_shows_scope(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, {
            "channel_idx": 0, "channel_name": "public", "channel_secret": b"\x00",
        }),
        Event(EventType.ERROR, {"reason": "none"}),
    )
    result = invoke(
        runner, configured_store, "send", "channel", "0", "hi", "--scope", "rescue", "--dry-run"
    )
    assert result.exit_code == 0, result.output
    assert "would send" in result.output
    assert "rescue" in result.output
    assert fake_connection.commands.call_count("set_flood_scope") == 0
    assert fake_connection.commands.call_count("send_chan_msg") == 0
