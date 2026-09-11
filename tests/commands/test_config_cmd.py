from __future__ import annotations

import json

import yaml

from meshcorectl.cli import cli
from meshcorectl.context_store import ConnectionSpec


def invoke(runner, store, *args):
    return runner.invoke(cli, ["--config", str(store.path), *args])


def test_get_contexts_empty_prints_hint(runner, store):
    result = invoke(runner, store, "config", "get-contexts")
    assert result.exit_code == 0
    assert "No contexts defined" in result.output


def test_get_contexts_lists_with_current_marker(runner, store):
    store.set_context("home", connection=ConnectionSpec(kind="ble", address="AA:BB"))
    store.set_context("lab", connection=ConnectionSpec(kind="tcp", host="h", tcp_port=1))
    result = invoke(runner, store, "config", "get-contexts")
    assert result.exit_code == 0
    header, home_row, lab_row = result.output.splitlines()
    assert header.split() == ["CURRENT", "NAME", "CONNECTION", "TIMEOUT"]
    assert home_row.startswith("*") and "home" in home_row
    assert not lab_row.startswith("*") and "lab" in lab_row


def test_current_context_unset_errors(runner, store):
    result = invoke(runner, store, "config", "current-context")
    assert result.exit_code != 0
    assert "current-context is not set" in result.output


def test_current_context_prints_name(runner, store):
    store.set_context("home", connection=ConnectionSpec(kind="tcp", host="h", tcp_port=1))
    result = invoke(runner, store, "config", "current-context")
    assert result.exit_code == 0
    assert result.output.strip() == "home"


def test_use_context_switches(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context("b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1))
    result = invoke(runner, store, "config", "use-context", "b")
    assert result.exit_code == 0
    assert store.load().current_context == "b"


def test_use_context_unknown_errors(runner, store):
    result = invoke(runner, store, "config", "use-context", "nope")
    assert result.exit_code != 0
    assert 'no context exists with the name "nope"' in result.output


def test_set_context_ble(runner, store):
    result = invoke(runner, store, "config", "set-context", "home", "--ble-address", "AA:BB")
    assert result.exit_code == 0
    ctx = store.get_context("home")
    assert ctx.connection.kind == "ble"
    assert ctx.connection.address == "AA:BB"


def test_set_context_ble_by_name_filter(runner, store):
    result = invoke(runner, store, "config", "set-context", "home", "--ble-name", "t114")
    assert result.exit_code == 0
    assert store.get_context("home").connection.name_filter == "t114"


def test_set_context_serial(runner, store):
    result = invoke(
        runner,
        store,
        "config",
        "set-context",
        "rep",
        "--serial-port",
        "/dev/ttyUSB0",
        "--serial-baudrate",
        "9600",
    )
    assert result.exit_code == 0
    ctx = store.get_context("rep")
    assert ctx.connection.kind == "serial"
    assert ctx.connection.port == "/dev/ttyUSB0"
    assert ctx.connection.baudrate == 9600


def test_set_context_tcp(runner, store):
    result = invoke(
        runner,
        store,
        "config",
        "set-context",
        "lab",
        "--tcp-host",
        "10.0.0.1",
        "--tcp-port",
        "6000",
    )
    assert result.exit_code == 0
    ctx = store.get_context("lab")
    assert ctx.connection.kind == "tcp"
    assert ctx.connection.host == "10.0.0.1"
    assert ctx.connection.tcp_port == 6000


def test_set_context_rejects_conflicting_kinds(runner, store):
    result = invoke(
        runner,
        store,
        "config",
        "set-context",
        "bad",
        "--ble-address",
        "AA:BB",
        "--tcp-host",
        "10.0.0.1",
    )
    assert result.exit_code != 0
    assert "conflicting connection flags" in result.output


def test_set_context_rejects_no_connection_flags(runner, store):
    result = invoke(runner, store, "config", "set-context", "bad")
    assert result.exit_code != 0
    assert "no connection specified" in result.output


def test_set_context_current_flag_switches(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    result = invoke(
        runner,
        store,
        "config",
        "set-context",
        "b",
        "--tcp-host",
        "b",
        "--tcp-port",
        "1",
        "--current",
    )
    assert result.exit_code == 0
    assert store.load().current_context == "b"
    assert "(current)" in result.output


def test_set_context_first_ever_becomes_current_without_flag(runner, store):
    result = invoke(
        runner, store, "config", "set-context", "only", "--tcp-host", "h", "--tcp-port", "1"
    )
    assert result.exit_code == 0
    assert store.load().current_context == "only"
    assert "(current)" in result.output


def test_set_context_second_without_flag_does_not_switch(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    result = invoke(
        runner, store, "config", "set-context", "b", "--tcp-host", "b", "--tcp-port", "1"
    )
    assert result.exit_code == 0
    assert store.load().current_context == "a"
    assert "(current)" not in result.output


def test_delete_context(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    result = invoke(runner, store, "config", "delete-context", "a")
    assert result.exit_code == 0
    assert store.load().contexts == {}


def test_delete_context_warns_when_it_was_current(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    result = invoke(runner, store, "config", "delete-context", "a")
    assert result.exit_code == 0
    assert "that was the current context" in result.output


def test_delete_context_no_warning_when_not_current(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context("b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1))
    result = invoke(runner, store, "config", "delete-context", "b")
    assert result.exit_code == 0
    assert "that was the current context" not in result.output


def test_delete_context_unknown_errors(runner, store):
    result = invoke(runner, store, "config", "delete-context", "nope")
    assert result.exit_code != 0


def test_view_defaults_to_yaml(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    result = invoke(runner, store, "config", "view")
    assert result.exit_code == 0
    parsed = yaml.safe_load(result.output)
    assert parsed["current-context"] == "a"


def test_view_json_output(runner, store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    result = invoke(runner, store, "-o", "json", "config", "view")
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["current-context"] == "a"
