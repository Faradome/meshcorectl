"""Opens a live connection to a device described by a `ConnectionSpec`.

Command modules depend only on the `MeshCoreConnection` protocol below, not
on `meshcore.MeshCore` directly, so the connection method can change without
touching command code.

`meshcore.MeshCore.create_ble/create_serial/create_tcp` are imported inside
`connect()`, not at module scope, so tests can monkeypatch them without
importing bleak/pyserial.
"""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

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
            assert spec.port is not None  # guaranteed by ConnectionSpec.__post_init__
            client = await MeshCore.create_serial(
                port=spec.port, baudrate=spec.baudrate, debug=debug, default_timeout=timeout
            )
        else:  # tcp
            assert spec.host is not None  # guaranteed by ConnectionSpec.__post_init__
            client = await MeshCore.create_tcp(
                host=spec.host, port=spec.tcp_port, debug=debug, default_timeout=timeout
            )
    except Exception as exc:
        raise ConnectError(f"failed to connect ({spec.summary()}): {exc}") from exc

    # MeshCore satisfies MeshCoreConnection structurally, but self_info is a
    # property and subscribe()'s signature is wider than this protocol
    # exposes -- both read as mismatches to a structural type checker.
    return cast(MeshCoreConnection, client)
