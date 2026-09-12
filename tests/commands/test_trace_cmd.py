from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke


def script_trace(fake_connection, path_payload):
    sent_payload = {"expected_ack": (1).to_bytes(4, "little"), "suggested_timeout": 1000}
    fake_connection.commands.script("send_trace", Event(EventType.MSG_SENT, sent_payload))
    fake_connection.script_wait_for_event(Event(EventType.TRACE_DATA, {"path": path_payload}))


def test_trace_prints_hops(runner, configured_store, fake_connection):
    script_trace(fake_connection, [{"snr": 8.0}, {"snr": -2.0}])
    result = invoke(runner, configured_store, "trace", "23,5f")
    assert result.exit_code == 0, result.output
    assert "8.0" in result.output
    assert "-2.0" in result.output


def test_trace_empty_path_prints_hint(runner, configured_store, fake_connection):
    script_trace(fake_connection, [])
    result = invoke(runner, configured_store, "trace", "23")
    assert result.exit_code == 0
    assert "No hops" in result.output


def test_trace_timeout_errors(runner, configured_store, fake_connection):
    sent_payload = {"expected_ack": (1).to_bytes(4, "little"), "suggested_timeout": 1000}
    fake_connection.commands.script("send_trace", Event(EventType.MSG_SENT, sent_payload))
    fake_connection.script_wait_for_event(None)
    result = invoke(runner, configured_store, "trace", "23")
    assert result.exit_code != 0
    assert "timed out" in result.output


def test_trace_send_error(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_trace", Event(EventType.ERROR, {"reason": "bad path"}))
    result = invoke(runner, configured_store, "trace", "zz")
    assert result.exit_code != 0
    assert "bad path" in result.output


def test_trace_custom_timeout_is_passed_through(runner, configured_store, fake_connection):
    script_trace(fake_connection, [{"snr": 1.0}])
    result = invoke(runner, configured_store, "trace", "23", "--timeout", "3.5")
    assert result.exit_code == 0, result.output
    assert fake_connection.wait_for_event_calls[0][2] == 3.5
