"""Unit tests for connect.py's transport-dispatch logic.

`meshcore.MeshCore.create_ble/create_serial/create_tcp` are monkeypatched
with fake async functions (success and failure) so this fully exercises
`connect()` -- including its error-wrapping -- without touching real BLE,
serial, or TCP hardware.
"""

from __future__ import annotations

import pytest
from meshcore import MeshCore

from meshcorectl.connect import ConnectError, connect
from meshcorectl.context_store import ConnectionSpec


async def _fake_ok(*args, **kwargs):
    return "connected-client"


async def _fake_fails(*args, **kwargs):
    raise RuntimeError("no hardware here")


async def test_connect_ble_success(monkeypatch):
    monkeypatch.setattr(MeshCore, "create_ble", _fake_ok)
    spec = ConnectionSpec(kind="ble", address="AA:BB")
    result = await connect(spec, timeout=5)
    assert result == "connected-client"


async def test_connect_serial_success(monkeypatch):
    monkeypatch.setattr(MeshCore, "create_serial", _fake_ok)
    spec = ConnectionSpec(kind="serial", port="/dev/ttyUSB0")
    result = await connect(spec, timeout=5)
    assert result == "connected-client"


async def test_connect_tcp_success(monkeypatch):
    monkeypatch.setattr(MeshCore, "create_tcp", _fake_ok)
    spec = ConnectionSpec(kind="tcp", host="10.0.0.1", tcp_port=5000)
    result = await connect(spec, timeout=5)
    assert result == "connected-client"


async def test_connect_ble_failure_wrapped_in_connect_error(monkeypatch):
    monkeypatch.setattr(MeshCore, "create_ble", _fake_fails)
    spec = ConnectionSpec(kind="ble", address="AA:BB")
    with pytest.raises(ConnectError, match="failed to connect \\(ble:AA:BB\\)"):
        await connect(spec, timeout=5)


async def test_connect_serial_failure_wrapped_in_connect_error(monkeypatch):
    monkeypatch.setattr(MeshCore, "create_serial", _fake_fails)
    spec = ConnectionSpec(kind="serial", port="/dev/ttyUSB0")
    with pytest.raises(ConnectError, match="no hardware here"):
        await connect(spec, timeout=5)


async def test_connect_tcp_failure_wrapped_in_connect_error(monkeypatch):
    monkeypatch.setattr(MeshCore, "create_tcp", _fake_fails)
    spec = ConnectionSpec(kind="tcp", host="10.0.0.1", tcp_port=5000)
    with pytest.raises(ConnectError, match="no hardware here"):
        await connect(spec, timeout=5)


async def test_connect_passes_debug_and_timeout_through(monkeypatch):
    captured = {}

    async def fake_create_ble(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(MeshCore, "create_ble", fake_create_ble)
    spec = ConnectionSpec(kind="ble", address="AA:BB")
    await connect(spec, timeout=7.5, debug=True)
    assert captured == {"address": "AA:BB", "debug": True, "default_timeout": 7.5}
