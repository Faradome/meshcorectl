from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke


def test_reboot_requires_yes(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "reboot")
    assert result.exit_code != 0
    assert "pass --yes" in result.output
    assert fake_connection.commands.call_count("reboot") == 0


def test_reboot_with_yes(runner, configured_store, fake_connection):
    fake_connection.commands.script("reboot", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "reboot", "--yes")
    assert result.exit_code == 0, result.output
    assert "reboot requested" in result.output
    assert fake_connection.commands.call_count("reboot") == 1


def test_reboot_dry_run_does_not_require_yes(runner, store):
    result = invoke(runner, store, "reboot", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would reboot" in result.output
