from __future__ import annotations

import json
from types import SimpleNamespace

from bleak.exc import BleakError

import meshcorectl.commands.scan as scan_module
from tests.conftest import invoke


def fake_ble_device(address, name):
    return SimpleNamespace(address=address, name=name)


def fake_serial_port(device, description):
    return SimpleNamespace(device=device, description=description)


def test_scan_lists_ble_and_serial(runner, store, monkeypatch):
    async def fake_discover(timeout):
        return [
            fake_ble_device("AA:BB", "MeshCore-t114"),
            fake_ble_device("CC:DD", "SomeOtherDevice"),  # filtered out
        ]

    monkeypatch.setattr(scan_module.BleakScanner, "discover", fake_discover)
    monkeypatch.setattr(
        scan_module.serial.tools.list_ports,
        "comports",
        lambda: [fake_serial_port("/dev/ttyUSB0", "USB Serial")],
    )

    result = invoke(runner, store, "scan")
    assert result.exit_code == 0, result.output
    assert "MeshCore-t114" in result.output
    assert "SomeOtherDevice" not in result.output
    assert "/dev/ttyUSB0" in result.output


def test_scan_ble_only(runner, store, monkeypatch):
    async def fake_discover(timeout):
        return [fake_ble_device("AA:BB", "MeshCore-t114")]

    monkeypatch.setattr(scan_module.BleakScanner, "discover", fake_discover)
    monkeypatch.setattr(scan_module.serial.tools.list_ports, "comports", lambda: [])

    result = invoke(runner, store, "scan", "--no-serial")
    assert result.exit_code == 0, result.output
    assert "MeshCore-t114" in result.output


def test_scan_serial_only_skips_ble_scan(runner, store, monkeypatch):
    async def should_not_be_called(timeout):
        raise AssertionError("BLE scan should not run with --no-ble")

    monkeypatch.setattr(scan_module.BleakScanner, "discover", should_not_be_called)
    monkeypatch.setattr(
        scan_module.serial.tools.list_ports,
        "comports",
        lambda: [fake_serial_port("/dev/ttyUSB0", "USB Serial")],
    )
    result = invoke(runner, store, "scan", "--no-ble")
    assert result.exit_code == 0, result.output
    assert "/dev/ttyUSB0" in result.output


def test_scan_no_candidates_prints_hint(runner, store, monkeypatch):
    async def fake_discover(timeout):
        return []

    monkeypatch.setattr(scan_module.BleakScanner, "discover", fake_discover)
    monkeypatch.setattr(scan_module.serial.tools.list_ports, "comports", lambda: [])
    result = invoke(runner, store, "scan")
    assert result.exit_code == 0
    assert "No candidates found" in result.output


def test_scan_ble_unavailable_degrades_gracefully(runner, store, monkeypatch):
    async def raises(timeout):
        raise BleakError("no BLE adapter")

    monkeypatch.setattr(scan_module.BleakScanner, "discover", raises)
    monkeypatch.setattr(
        scan_module.serial.tools.list_ports,
        "comports",
        lambda: [fake_serial_port("/dev/ttyUSB0", "USB Serial")],
    )
    result = invoke(runner, store, "scan")
    assert result.exit_code == 0, result.output
    assert "BLE scan unavailable" in result.output
    assert "/dev/ttyUSB0" in result.output


def test_scan_json_output(runner, store, monkeypatch):
    async def fake_discover(timeout):
        return [fake_ble_device("AA:BB", "MeshCore-t114")]

    monkeypatch.setattr(scan_module.BleakScanner, "discover", fake_discover)
    monkeypatch.setattr(scan_module.serial.tools.list_ports, "comports", lambda: [])
    result = invoke(runner, store, "-o", "json", "scan")
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed == [{"kind": "ble", "address": "AA:BB", "name": "MeshCore-t114"}]
