from __future__ import annotations

import json

import yaml
from meshcore import EventType
from meshcore.events import Event

from meshcorectl import __version__
from tests.conftest import invoke


def test_version_client_only_does_not_connect(runner, store):
    """No --config context is even set up here -- if this tried to connect
    it would blow up in resolve_context(), proving --client skips it."""
    result = invoke(runner, store, "version", "--client")
    assert result.exit_code == 0, result.output
    assert __version__ in result.output
    assert "Device" not in result.output


def test_version_with_device(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query",
        Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114", "ver": "v1.10.0"}),
    )
    result = invoke(runner, configured_store, "version")
    assert result.exit_code == 0, result.output
    assert __version__ in result.output
    assert "T114" in result.output
    assert "v1.10.0" in result.output


def test_version_json(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query", Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114"})
    )
    result = invoke(runner, configured_store, "-o", "json", "version")
    parsed = json.loads(result.output)
    assert parsed["client_version"] == __version__
    assert parsed["device"]["model"] == "T114"


def test_version_yaml(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query", Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114"})
    )
    result = invoke(runner, configured_store, "-o", "yaml", "version")
    assert result.exit_code == 0, result.output
    parsed = yaml.safe_load(result.output)
    assert parsed["client_version"] == __version__
    assert parsed["device"]["model"] == "T114"


def test_version_without_client_requires_a_context(runner, store):
    result = invoke(runner, store, "version")
    assert result.exit_code != 0
    assert "no context specified" in result.output
