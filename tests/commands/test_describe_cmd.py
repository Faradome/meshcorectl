from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from meshcorectl.commands.describe import _format_epoch
from tests.conftest import invoke


def test_format_epoch_falsy_is_a_dash():
    assert _format_epoch(0) == "-"
    assert _format_epoch(None) == "-"


def test_format_epoch_nonzero_is_formatted():
    assert _format_epoch(1000) != "-"


def test_describe_device(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "send_device_query",
        Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114", "ver": "v1.10.0"}),
    )
    result = invoke(runner, configured_store, "describe", "device")
    assert result.exit_code == 0, result.output
    assert "Model:" in result.output
    assert "T114" in result.output


def test_describe_device_ignores_output_flag(runner, configured_store, fake_connection):
    """`describe` has no -o support, matching real `kubectl describe` --
    passing -o json is simply ignored, never an error."""
    fake_connection.commands.script(
        "send_device_query", Event(EventType.DEVICE_INFO, {"fw ver": 14, "model": "T114"})
    )
    result = invoke(runner, configured_store, "-o", "json", "describe", "device")
    assert result.exit_code == 0, result.output
    assert "Model:" in result.output  # still the labeled text form, not JSON


def test_describe_contact(runner, configured_store, fake_connection):
    fake_connection.commands.script(
        "get_contacts",
        Event(
            EventType.CONTACTS,
            {
                "AA": {
                    "adv_name": "alice",
                    "public_key": "AA",
                    "type": 1,
                    "out_path_len": -1,
                    "last_advert": 1000,
                    "lastmod": 2000,
                }
            },
        ),
    )
    result = invoke(runner, configured_store, "describe", "contact", "alice")
    assert result.exit_code == 0, result.output
    assert "Name:" in result.output
    assert "Path:" in result.output
    assert "flood" in result.output
    last_advert_line = next(line for line in result.output.splitlines() if "Last Advert" in line)
    assert last_advert_line.strip() != "Last Advert:  -"  # epoch 1000 -> formatted, not the dash


def test_describe_contact_unknown_errors(runner, configured_store, fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, {}))
    result = invoke(runner, configured_store, "describe", "contact", "nope")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_describe_contact_ambiguous_name_errors(runner, configured_store, fake_connection):
    dup_payload = {
        "AA": {"adv_name": "dup", "public_key": "AA11"},
        "BB": {"adv_name": "dup", "public_key": "BB22"},
    }
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, dup_payload))
    result = invoke(runner, configured_store, "describe", "contact", "dup")
    assert result.exit_code != 0
    assert "matches 2 contacts" in result.output
