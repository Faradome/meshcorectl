from __future__ import annotations

import json

from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke


def test_create_contact_imports_uri(runner, configured_store, fake_connection):
    fake_connection.commands.script("import_contact", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "create", "contact", "--uri", "meshcore://aabb")
    assert result.exit_code == 0, result.output
    assert "meshcore://aabb" in result.output
    assert fake_connection.commands.calls == [("import_contact", (b"\xaa\xbb",), {})]


def test_create_contact_json_output(runner, configured_store, fake_connection):
    fake_connection.commands.script("import_contact", Event(EventType.OK, {}))
    result = invoke(
        runner, configured_store, "-o", "json", "create", "contact", "--uri", "meshcore://aabb"
    )
    parsed = json.loads(result.output)
    assert parsed == {"imported": True, "uri": "meshcore://aabb"}


def test_create_contact_dry_run_does_not_connect(runner, store):
    # No configured_store/fake_connection: if this tried to connect it
    # would fail resolve_context() since no context exists at all.
    result = invoke(runner, store, "create", "contact", "--uri", "meshcore://aabb", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would import" in result.output


def test_create_contact_rejects_bad_uri(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "create", "contact", "--uri", "http://nope")
    assert result.exit_code != 0
    assert "not a meshcore contact URI" in result.output


def test_create_channel(runner, configured_store, fake_connection):
    fake_connection.commands.script("set_channel", Event(EventType.OK, {}))
    confirmed = {"channel_idx": 3, "channel_name": "#fdl", "channel_secret": b"\x01" * 16}
    fake_connection.commands.script("get_channel", Event(EventType.CHANNEL_INFO, confirmed))
    result = invoke(runner, configured_store, "create", "channel", "3", "#fdl", "01" * 16)
    assert result.exit_code == 0, result.output
    assert "#fdl" in result.output


def test_create_channel_without_key(runner, configured_store, fake_connection):
    fake_connection.commands.script("set_channel", Event(EventType.OK, {}))
    confirmed = {"channel_idx": 3, "channel_name": "#fdl", "channel_secret": b"\x00"}
    fake_connection.commands.script("get_channel", Event(EventType.CHANNEL_INFO, confirmed))
    result = invoke(runner, configured_store, "create", "channel", "3", "#fdl")
    assert result.exit_code == 0, result.output
    assert fake_connection.commands.calls[0] == ("set_channel", (3, "#fdl", None), {})


def test_create_channel_dry_run(runner, store):
    result = invoke(runner, store, "create", "channel", "3", "#fdl", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would create channel 3" in result.output


def test_create_channel_error(runner, configured_store, fake_connection):
    fake_connection.commands.script("set_channel", Event(EventType.ERROR, {"reason": "full"}))
    result = invoke(runner, configured_store, "create", "channel", "3", "#fdl")
    assert result.exit_code != 0
    assert "full" in result.output
