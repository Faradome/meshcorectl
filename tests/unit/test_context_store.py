from __future__ import annotations

from pathlib import Path

import pytest

from meshcorectl.context_store import (
    ConfigFileCorruptError,
    ConnectionSpec,
    Context,
    ContextNotFoundError,
    ContextStore,
    ContextStoreError,
    default_config_path,
)

# --- ConnectionSpec -----------------------------------------------------


def test_connection_spec_ble_summary_with_address():
    spec = ConnectionSpec(kind="ble", address="AA:BB:CC:DD:EE:FF")
    assert spec.summary() == "ble:AA:BB:CC:DD:EE:FF"


def test_connection_spec_ble_summary_with_name_filter():
    spec = ConnectionSpec(kind="ble", name_filter="t114")
    assert spec.summary() == "ble:name~t114"


def test_connection_spec_ble_summary_bare():
    spec = ConnectionSpec(kind="ble")
    assert spec.summary() == "ble:<first found>"


def test_connection_spec_serial_summary():
    spec = ConnectionSpec(kind="serial", port="/dev/ttyUSB0", baudrate=9600)
    assert spec.summary() == "serial:/dev/ttyUSB0@9600"


def test_connection_spec_tcp_summary():
    spec = ConnectionSpec(kind="tcp", host="10.0.0.5", tcp_port=5000)
    assert spec.summary() == "tcp:10.0.0.5:5000"


def test_connection_spec_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown connection kind"):
        ConnectionSpec(kind="carrier-pigeon")


def test_connection_spec_serial_requires_port():
    with pytest.raises(ValueError, match="requires 'port'"):
        ConnectionSpec(kind="serial")


def test_connection_spec_tcp_requires_host():
    with pytest.raises(ValueError, match="requires 'host'"):
        ConnectionSpec(kind="tcp")


def test_connection_spec_ble_round_trips_through_dict():
    spec = ConnectionSpec(kind="ble", address="AA:BB", name_filter="foo")
    assert ConnectionSpec.from_dict(spec.to_dict()) == spec


def test_connection_spec_serial_round_trips_through_dict():
    spec = ConnectionSpec(kind="serial", port="/dev/ttyUSB0", baudrate=57600)
    assert ConnectionSpec.from_dict(spec.to_dict()) == spec


def test_connection_spec_tcp_round_trips_through_dict():
    spec = ConnectionSpec(kind="tcp", host="host", tcp_port=1234)
    assert ConnectionSpec.from_dict(spec.to_dict()) == spec


def test_connection_spec_from_dict_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown connection kind"):
        ConnectionSpec.from_dict({"kind": "carrier-pigeon"})


def test_connection_spec_from_dict_serial_missing_port():
    with pytest.raises(ValueError, match="missing 'port'"):
        ConnectionSpec.from_dict({"kind": "serial"})


def test_connection_spec_from_dict_tcp_missing_host():
    with pytest.raises(ValueError, match="missing 'host'"):
        ConnectionSpec.from_dict({"kind": "tcp"})


# --- default_config_path -------------------------------------------------


def test_default_config_path_uses_xdg_config_home(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg-base")
    assert default_config_path() == Path("/xdg-base/meshcorectl/config.yaml")


def test_default_config_path_falls_back_to_home_dot_config(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("meshcorectl.context_store.Path.home", lambda: tmp_path)
    assert default_config_path() == tmp_path / ".config" / "meshcorectl" / "config.yaml"


# --- ContextStore: load() -------------------------------------------------


def test_load_missing_file_returns_empty_config(store):
    cfg = store.load()
    assert cfg.current_context is None
    assert cfg.contexts == {}


def test_load_empty_file_returns_empty_config(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("")
    cfg = store.load()
    assert cfg.contexts == {}


def test_load_rejects_invalid_yaml(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("contexts: [this, is, not, a, mapping\n")
    with pytest.raises(ConfigFileCorruptError):
        store.load()


def test_load_rejects_non_mapping_top_level(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigFileCorruptError):
        store.load()


def test_load_rejects_context_missing_connection(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("contexts:\n  home: {}\n")
    with pytest.raises(ConfigFileCorruptError, match="missing 'connection'"):
        store.load()


def test_load_rejects_contexts_not_a_mapping(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("contexts: nope\n")
    with pytest.raises(ConfigFileCorruptError):
        store.load()


def test_load_rejects_defaults_not_a_mapping(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("defaults: nope\n")
    with pytest.raises(ConfigFileCorruptError, match="'defaults' must be a mapping"):
        store.load()


# --- ContextStore: set_context / save / load round trip -------------------


def test_set_context_creates_and_first_context_becomes_current(store):
    store.set_context("home", connection=ConnectionSpec(kind="tcp", host="h", tcp_port=1))
    cfg = store.load()
    assert cfg.current_context == "home"
    assert cfg.contexts["home"].connection.host == "h"


def test_set_context_second_context_does_not_steal_current(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context("b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1))
    assert store.load().current_context == "a"


def test_set_context_with_set_current_switches(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context(
        "b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1), set_current=True
    )
    assert store.load().current_context == "b"


def test_set_context_overwrites_existing(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="old", tcp_port=1))
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="new", tcp_port=1))
    assert store.load().contexts["a"].connection.host == "new"


def test_set_context_persists_timeout(store):
    store.set_context(
        "a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1), timeout=42.0
    )
    assert store.load().contexts["a"].timeout == 42.0


def test_full_round_trip_all_three_kinds(store):
    store.set_context("ble-ctx", connection=ConnectionSpec(kind="ble", address="AA:BB"))
    store.set_context(
        "serial-ctx", connection=ConnectionSpec(kind="serial", port="/dev/ttyUSB0")
    )
    store.set_context("tcp-ctx", connection=ConnectionSpec(kind="tcp", host="h", tcp_port=9))

    reloaded = ContextStore(store.path).load()
    assert set(reloaded.contexts) == {"ble-ctx", "serial-ctx", "tcp-ctx"}
    assert reloaded.contexts["ble-ctx"].connection.kind == "ble"
    assert reloaded.contexts["serial-ctx"].connection.kind == "serial"
    assert reloaded.contexts["tcp-ctx"].connection.kind == "tcp"


# --- ContextStore: get_context / current_context ---------------------------


def test_get_context_missing_raises(store):
    with pytest.raises(ContextNotFoundError):
        store.get_context("nope")


def test_current_context_unset_raises(store):
    with pytest.raises(ContextStoreError, match="current-context is not set"):
        store.current_context()


def test_current_context_returns_context_object(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    assert store.current_context() == Context(
        name="a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1)
    )


def test_list_contexts_sorted_by_name(store):
    store.set_context("zeta", connection=ConnectionSpec(kind="tcp", host="z", tcp_port=1))
    store.set_context("alpha", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    assert [c.name for c in store.list_contexts()] == ["alpha", "zeta"]


# --- ContextStore: use_context ---------------------------------------------


def test_use_context_switches_current(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context("b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1))
    store.use_context("b")
    assert store.load().current_context == "b"


def test_use_context_unknown_raises_and_does_not_change_file(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    with pytest.raises(ContextNotFoundError):
        store.use_context("nope")
    assert store.load().current_context == "a"


# --- ContextStore: delete_context -------------------------------------------


def test_delete_context_removes_it(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.delete_context("a")
    assert store.load().contexts == {}


def test_delete_context_returns_true_and_clears_current_if_it_was_current(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    was_current = store.delete_context("a")
    assert was_current is True
    assert store.load().current_context is None


def test_delete_context_returns_false_when_not_current(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context("b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1))
    was_current = store.delete_context("b")
    assert was_current is False
    assert store.load().current_context == "a"


def test_delete_context_unknown_raises(store):
    with pytest.raises(ContextNotFoundError):
        store.delete_context("nope")
