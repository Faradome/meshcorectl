from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke


def script_alice(fake_connection):
    fake_connection.commands.script(
        "get_contacts",
        Event(
            EventType.CONTACTS,
            {"AA": {"adv_name": "alice", "public_key": "AA", "type": 4, "out_path_len": -1}},
        ),
    )


def test_top_contact_instant_reading(runner, configured_store, fake_connection):
    script_alice(fake_connection)
    fake_connection.commands.script(
        "req_telemetry_sync", [{"channel": 1, "type": "temperature", "value": 21.5}]
    )
    result = invoke(runner, configured_store, "top", "contact", "alice")
    assert result.exit_code == 0, result.output
    assert "temperature" in result.output
    assert "21.5" in result.output


def test_top_contact_history(runner, configured_store, fake_connection):
    script_alice(fake_connection)
    fake_connection.commands.script(
        "req_mma_sync", [{"channel": 1, "type": "temperature", "min": 10, "max": 20, "avg": 15}]
    )
    result = invoke(runner, configured_store, "top", "contact", "alice", "--history")
    assert result.exit_code == 0, result.output
    assert "15" in result.output
    call = fake_connection.commands.calls[-1]
    assert call[0] == "req_mma_sync"


def test_top_contact_history_rejects_bad_since(runner, configured_store, fake_connection):
    script_alice(fake_connection)
    result = invoke(
        runner, configured_store, "top", "contact", "alice", "--history", "--since", "nonsense"
    )
    assert result.exit_code != 0
    assert "invalid duration" in result.output


def test_top_contact_unknown_errors(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, {}))
    result = invoke(runner, configured_store, "top", "contact", "nope")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_top_contact_no_readings_prints_hint(runner, configured_store, fake_connection):
    script_alice(fake_connection)
    fake_connection.commands.script("req_telemetry_sync", [])
    result = invoke(runner, configured_store, "top", "contact", "alice")
    assert result.exit_code == 0
    assert "No telemetry readings" in result.output


def test_top_contact_timeout_errors(runner, configured_store, fake_connection):
    script_alice(fake_connection)
    fake_connection.commands.script("req_telemetry_sync", None)
    result = invoke(runner, configured_store, "top", "contact", "alice")
    assert result.exit_code != 0
    assert "timed out" in result.output
