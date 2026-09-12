from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke

CONTACTS_PAYLOAD = {
    "AA": {"adv_name": "alice", "public_key": "AA", "type": 1, "out_path_len": -1, "lastmod": 1},
    "BB": {"adv_name": "bob", "public_key": "BB", "type": 2, "out_path_len": 0, "lastmod": 2},
}


def script_contacts(fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, CONTACTS_PAYLOAD))


def test_delete_contact_by_name(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("remove_contact", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "delete", "contact", "alice")
    assert result.exit_code == 0, result.output
    assert "alice" in result.output and "deleted" in result.output
    assert fake_connection.commands.call_count("remove_contact") == 1


def test_delete_contact_unknown_name_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "delete", "contact", "nope")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_delete_contact_requires_name_or_selector(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "delete", "contact")
    assert result.exit_code != 0
    assert "pass exactly one of" in result.output


def test_delete_contact_rejects_both_name_and_selector(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "delete", "contact", "alice", "-l", "t=1")
    assert result.exit_code != 0
    assert "pass exactly one of" in result.output


def test_delete_contact_by_selector_batches_over_matches(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("remove_contact", Event(EventType.OK, {}), repeat=True)
    result = invoke(runner, configured_store, "delete", "contact", "-l", "t=1")
    assert result.exit_code == 0, result.output
    assert "alice" in result.output
    assert "bob" not in result.output
    assert fake_connection.commands.call_count("remove_contact") == 1


def test_delete_contact_selector_matches_none(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "delete", "contact", "-l", "t=4")
    assert result.exit_code == 0
    assert "No contacts matched" in result.output


def test_delete_contact_bad_selector_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "delete", "contact", "-l", "bogus")
    assert result.exit_code != 0


def test_delete_contact_dry_run_does_not_call_remove(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "delete", "contact", "alice", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would be deleted" in result.output
    assert fake_connection.commands.call_count("remove_contact") == 0


def test_delete_channel(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, {
            "channel_idx": 1, "channel_name": "#fdl", "channel_secret": b"\x00",
        }),
        Event(EventType.ERROR, {"reason": "none"}),
    )
    fake_connection.commands.script("set_channel", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "delete", "channel", "1")
    assert result.exit_code == 0, result.output
    assert "cleared" in result.output


def test_delete_channel_unknown_errors(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_channel", Event(EventType.ERROR, {"reason": "none"}))
    result = invoke(runner, configured_store, "delete", "channel", "9")
    assert result.exit_code != 0
    assert "no channel matching" in result.output


def test_delete_channel_dry_run(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "get_channel",
        Event(EventType.CHANNEL_INFO, {
            "channel_idx": 1, "channel_name": "#fdl", "channel_secret": b"\x00",
        }),
        Event(EventType.ERROR, {"reason": "none"}),
    )
    result = invoke(runner, configured_store, "delete", "channel", "1", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would be cleared" in result.output
    assert fake_connection.commands.call_count("set_channel") == 0
