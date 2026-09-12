"""Resolves a stored `ConnectionSpec` into a live MeshCore client.

This is the one seam PLAN.md (Decision 1) reserves for the future
`meshcored`-backed client: every command module talks only to the
`MeshCoreConnection` protocol below, never to `meshcore.MeshCore` directly,
so a daemon-backed implementation can be swapped in later (see `cli.py`'s
`CliState.connect`) without touching a single command module.

`meshcore.MeshCore.create_ble/create_serial/create_tcp` are imported lazily
inside `connect()` rather than at module scope so that unit tests can
monkeypatch them without importing real transport backends (bleak,
pyserial) any earlier than `meshcore` itself already does.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .context_store import ConnectionSpec


class ConnectError(Exception):
    """Raised when a connection to a device cannot be established."""


@runtime_checkable
class MeshCoreConnection(Protocol):
    """The subset of `meshcore.MeshCore` a command module is allowed to use."""

    self_info: dict[str, Any]
    commands: Any

    def subscribe(self, event_type: Any, handler: Any) -> None: ...  # pragma: no cover

    async def disconnect(self) -> None: ...  # pragma: no cover

    async def wait_for_event(
        self,
        event_type: Any,
        attribute_filters: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any: ...  # pragma: no cover


async def connect(
    spec: ConnectionSpec, *, timeout: float, debug: bool = False
) -> MeshCoreConnection:
    """Open a direct (v1) connection described by `spec`.

    Raises `ConnectError` wrapping whatever the underlying transport raised
    (BleakError, ConnectionError, TimeoutError, ...), so callers only need
    to handle one exception type.
    """
    from meshcore import MeshCore

    try:
        if spec.kind == "ble":
            client = await MeshCore.create_ble(
                address=spec.address, debug=debug, default_timeout=timeout
            )
        elif spec.kind == "serial":
            client = await MeshCore.create_serial(
                port=spec.port, baudrate=spec.baudrate, debug=debug, default_timeout=timeout
            )
        else:  # tcp — ConnectionSpec.__post_init__ guarantees kind is one of the three
            client = await MeshCore.create_tcp(
                host=spec.host, port=spec.tcp_port, debug=debug, default_timeout=timeout
            )
    except Exception as exc:
        raise ConnectError(f"failed to connect ({spec.summary()}): {exc}") from exc

    return client
