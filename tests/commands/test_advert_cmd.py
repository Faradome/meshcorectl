from __future__ import annotations

import json

import yaml
from meshcore import EventType
from meshcore.events import Event

from tests.conftest import invoke


def test_advert_default(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_advert", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "advert")
    assert result.exit_code == 0, result.output
    assert "advert sent" in result.output
    assert "flood" not in result.output
    assert fake_connection.commands.calls == [("send_advert", (), {"flood": False})]


def test_advert_flood(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_advert", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "advert", "--flood")
    assert result.exit_code == 0, result.output
    assert "flood" in result.output
    assert fake_connection.commands.calls == [("send_advert", (), {"flood": True})]


def test_advert_json_output(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_advert", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "-o", "json", "advert")
    parsed = json.loads(result.output)
    assert parsed == {"sent": True, "flood": False}


def test_advert_yaml_output(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_advert", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "-o", "yaml", "advert")
    parsed = yaml.safe_load(result.output)
    assert parsed == {"sent": True, "flood": False}


def test_advert_error(runner, configured_store, fake_connection):
    fake_connection.commands.script("send_advert", Event(EventType.ERROR, {"reason": "nope"}))
    result = invoke(runner, configured_store, "advert")
    assert result.exit_code != 0
    assert "nope" in result.output


def test_advert_dry_run(runner, store):
    result = invoke(runner, store, "advert", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would send" in result.output


def test_advert_dry_run_flood(runner, store):
    result = invoke(runner, store, "advert", "--flood", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would send a flood advert" in result.output
