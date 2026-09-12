from __future__ import annotations

import pytest
from click.testing import CliRunner

from meshcorectl.context_store import ConnectionSpec, ContextStore
from tests.fakes.meshcore_double import FakeMeshCore


@pytest.fixture
def store(tmp_path):
    """A ContextStore backed by a throwaway file, never the user's real config."""
    return ContextStore(tmp_path / "config.yaml")


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def configured_store(store):
    """A `store` with one ("test") context already set as current -- for
    every command test that needs `resolve_context()` to succeed."""
    store.set_context("test", connection=ConnectionSpec(kind="tcp", host="h", tcp_port=1))
    return store


@pytest.fixture
def fake_connection(monkeypatch):
    """Monkeypatches `meshcorectl.cli.connect` so `CliState.connect()`
    (and everything built on it: `.connected()`, `.call()`) hands back this
    `FakeMeshCore` instead of ever touching real BLE/serial/TCP -- the same
    seam Phase 1's `tests/unit/test_cli_state.py` exercises directly.

    `connect_call_count` tracks how many times a command actually opened a
    connection: live hardware testing found `top contact` opening two
    (contact resolution + the telemetry fetch, as two separate `state.call()`s
    instead of one) -- which this fixture, always handing back the *same*
    fake regardless of call count, couldn't have caught on its own. Commands
    that only need one connection should assert `== 1`.
    """
    fake = FakeMeshCore()
    fake.connect_call_count = 0

    async def fake_connect(connection_spec, *, timeout, debug):
        fake.connect_call_count += 1
        return fake

    monkeypatch.setattr("meshcorectl.cli.connect", fake_connect)
    return fake


def invoke(runner, store, *args):
    """Shared CliRunner invocation helper: point --config at a throwaway store."""
    from meshcorectl.cli import cli

    return runner.invoke(cli, ["--config", str(store.path), *args])
