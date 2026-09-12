from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from meshcorectl.commands.set_ import _format_params_help
from tests.conftest import invoke


def test_format_params_help_dedents_before_substituting():
    """Python only auto-dedents docstrings at compile time starting in
    3.13; on 3.10-3.12 `Command.help` (== a bare `f.__doc__`) still carries
    its original 4-space source indentation at the point this runs. Feed
    that pre-3.13 shape explicitly so this test doesn't depend on which
    Python version actually runs it."""
    raw = "Set device parameter PARAM to VALUE.\n\n    \x08\n    Known parameters: {params}\n    "
    result = _format_params_help(raw, ("a", "b"))
    assert result == "Set device parameter PARAM to VALUE.\n\n\x08\nKnown parameters: a, b"
    assert all(not line.startswith(" ") for line in result.splitlines())


def test_format_params_help_wraps_long_lists():
    raw = "Set device parameter PARAM to VALUE.\n\n\x08\nKnown parameters: {params}"
    long_params = tuple(f"param-{i}" for i in range(20))
    result = _format_params_help(raw, long_params)
    assert "\n" in result.rsplit("Known parameters:", 1)[1]
    assert all(not line.startswith(" ") for line in result.splitlines())


def test_set_device_name(runner, configured_store, fake_connection):
    fake_connection.commands.script("set_name", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "set", "device", "name", "new-name")
    assert result.exit_code == 0, result.output
    assert "name set to 'new-name'" in result.output
    assert fake_connection.commands.calls == [("set_name", ("new-name",), {})]


def test_set_device_unknown_param_fails_before_connecting(runner, store):
    result = invoke(runner, store, "set", "device", "bogus", "1")
    assert result.exit_code != 0
    assert "unknown device parameter" in result.output


def test_set_device_invalid_value_errors(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "set", "device", "tx-power", "not-a-number")
    assert result.exit_code != 0
    assert "invalid value" in result.output


def test_set_device_error(runner, configured_store, fake_connection):
    error = Event(EventType.ERROR, {"reason": "out of range"})
    fake_connection.commands.script("set_tx_power", error)
    result = invoke(runner, configured_store, "set", "device", "tx-power", "99")
    assert result.exit_code != 0
    assert "out of range" in result.output


def test_set_device_dry_run(runner, store):
    result = invoke(runner, store, "set", "device", "name", "new-name", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would set name to 'new-name'" in result.output
