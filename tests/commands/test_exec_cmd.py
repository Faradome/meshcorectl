from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke

CONTACTS_PAYLOAD = {
    "AA": {"adv_name": "rep1", "public_key": "AA", "type": 2, "out_path_len": 0, "lastmod": 1},
    "BB": {"adv_name": "rep2", "public_key": "BB", "type": 2, "out_path_len": 0, "lastmod": 2},
}


def script_contacts(fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, CONTACTS_PAYLOAD))


def test_exec_by_name_prints_bare_reply(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_cmd", Event(EventType.MSG_SENT, {}))
    fake_connection.script_wait_for_event(Event(EventType.MESSAGES_WAITING, {}))
    fake_connection.commands.script("get_msg", Event(EventType.CONTACT_MSG_RECV, {"text": "v1.10"}))
    result = invoke(runner, configured_store, "exec", "rep1", "--", "ver")
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "v1.10"


def test_exec_no_reply_prints_note_on_stderr(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_cmd", Event(EventType.MSG_SENT, {}))
    fake_connection.script_wait_for_event(None)
    result = invoke(runner, configured_store, "exec", "rep1", "--", "ver")
    assert result.exit_code == 0
    assert "no reply within" in result.output


def test_exec_unknown_contact_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "exec", "nope", "--", "ver")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_exec_ambiguous_name_errors(runner, configured_store, fake_connection):
    dup_payload = {
        "AA": {"adv_name": "dup", "public_key": "AA11", "type": 2, "out_path_len": 0},
        "BB": {"adv_name": "dup", "public_key": "BB22", "type": 2, "out_path_len": 0},
    }
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, dup_payload))
    result = invoke(runner, configured_store, "exec", "dup", "--", "ver")
    assert result.exit_code != 0
    assert "matches 2 contacts" in result.output


def test_exec_requires_a_command(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "exec", "rep1")
    assert result.exit_code != 0
    assert "no command given" in result.output


def test_exec_requires_name_or_selector(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "exec")
    assert result.exit_code != 0
    assert "pass exactly one of" in result.output


def test_exec_by_selector_prefixes_each_reply_with_name(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_cmd", Event(EventType.MSG_SENT, {}), repeat=True)
    fake_connection.script_wait_for_event(
        Event(EventType.MESSAGES_WAITING, {}), Event(EventType.MESSAGES_WAITING, {})
    )
    fake_connection.commands.script(
        "get_msg",
        Event(EventType.CONTACT_MSG_RECV, {"text": "reply1"}),
        Event(EventType.CONTACT_MSG_RECV, {"text": "reply2"}),
    )
    result = invoke(runner, configured_store, "exec", "-l", "t=2", "--", "ver")
    assert result.exit_code == 0, result.output
    assert "rep1: reply1" in result.output
    assert "rep2: reply2" in result.output


def test_exec_bad_selector_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "exec", "-l", "bogus", "--", "ver")
    assert result.exit_code != 0


def test_exec_selector_matches_none(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "exec", "-l", "t=1", "--", "ver")
    assert result.exit_code == 0
    assert "No contacts matched" in result.output


def test_exec_dry_run(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "exec", "rep1", "--dry-run", "--", "ver")
    assert result.exit_code == 0, result.output
    assert "would run" in result.output
    assert fake_connection.commands.call_count("send_cmd") == 0
