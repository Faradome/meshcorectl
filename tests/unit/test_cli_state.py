from __future__ import annotations

import click
import pytest

from meshcorectl.cli import DEFAULT_TIMEOUT, CliState
from meshcorectl.context_store import ConnectionSpec
from meshcorectl.output import OutputFormat


def make_state(store, *, context_override=None, timeout_override=None, verbosity=0):
    return CliState(
        store=store,
        context_override=context_override,
        output=OutputFormat.TABLE,
        timeout_override=timeout_override,
        verbosity=verbosity,
    )


def test_resolve_context_uses_override_even_if_current_set(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    store.set_context("b", connection=ConnectionSpec(kind="tcp", host="b", tcp_port=1))
    state = make_state(store, context_override="b")
    assert state.resolve_context().name == "b"


def test_resolve_context_falls_back_to_current(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    state = make_state(store)
    assert state.resolve_context().name == "a"


def test_resolve_context_raises_click_exception_when_nothing_configured(store):
    state = make_state(store)
    with pytest.raises(click.ClickException, match="no context specified"):
        state.resolve_context()


def test_resolve_context_raises_click_exception_for_unknown_override(store):
    state = make_state(store, context_override="nope")
    with pytest.raises(click.ClickException, match="no context exists"):
        state.resolve_context()


def test_effective_timeout_prefers_flag_override(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1), timeout=5.0)
    state = make_state(store, context_override="a", timeout_override=99.0)
    assert state.effective_timeout(state.resolve_context()) == 99.0


def test_effective_timeout_falls_back_to_context_timeout(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1), timeout=5.0)
    state = make_state(store, context_override="a")
    assert state.effective_timeout(state.resolve_context()) == 5.0


def test_effective_timeout_falls_back_to_config_defaults(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    cfg = store.load()
    cfg.defaults["timeout"] = 33.0
    store.save(cfg)
    state = make_state(store, context_override="a")
    assert state.effective_timeout(state.resolve_context()) == 33.0


def test_effective_timeout_falls_back_to_hardcoded_default(store):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    state = make_state(store, context_override="a")
    assert state.effective_timeout(state.resolve_context()) == DEFAULT_TIMEOUT


async def test_connect_resolves_context_and_delegates_to_connect_module(store, monkeypatch):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    captured = {}

    async def fake_connect(connection, *, timeout, debug):
        captured.update(connection=connection, timeout=timeout, debug=debug)
        return "the-connection"

    monkeypatch.setattr("meshcorectl.cli.connect", fake_connect)
    state = make_state(store, context_override="a")
    result = await state.connect()
    assert result == "the-connection"
    assert captured["connection"].host == "a"
    assert captured["timeout"] == DEFAULT_TIMEOUT
    assert captured["debug"] is False


async def test_connect_passes_debug_true_at_high_verbosity(store, monkeypatch):
    store.set_context("a", connection=ConnectionSpec(kind="tcp", host="a", tcp_port=1))
    captured = {}

    async def fake_connect(connection, *, timeout, debug):
        captured["debug"] = debug
        return "conn"

    monkeypatch.setattr("meshcorectl.cli.connect", fake_connect)
    state = make_state(store, context_override="a", verbosity=2)
    await state.connect()
    assert captured["debug"] is True


def test_run_async_runs_a_coroutine(store):
    state = make_state(store)

    async def coro():
        return 42

    assert state.run_async(coro()) == 42
