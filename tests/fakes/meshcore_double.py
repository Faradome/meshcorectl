"""A hardware-free double for `meshcore.MeshCore`, used by every command test.

Command modules only ever see the `connect.MeshCoreConnection` protocol
(`.commands`, `.self_info`, `.subscribe`, `.disconnect`) — see
`meshcorectl/connect.py` and PLAN.md Decision 1 — so `FakeMeshCore` below
satisfies that shape without touching BLE, serial, or TCP. Built in Phase 1
(PLAN.md §8) so every read/write command from Phase 2 onward is written
test-first against it.

Real `meshcore.events.Event`/`EventType` objects are used for scripted
results (they're plain dataclasses/enums with no I/O), so assertions in
command tests match exactly what real command code checks
(`result.is_error()`, `result.type`, `result.payload`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from meshcore import EventType


class FakeCommandHandler:
    """Stands in for `meshcore`'s `CommandHandler` (the `.commands` object).

    Script a response for a method before calling it:

        fake.script("get_contacts", Event(EventType.CONTACTS, {...}))
        result = await fake.get_contacts()   # returns that Event
        assert fake.calls == [("get_contacts", (), {})]

    Any attribute access returns an async callable (`__getattr__`), so the
    double never falls behind as new `commands.*` methods are wired up in
    later phases — only the methods a given test actually scripts need to
    be mentioned.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._scripts: dict[str, dict[str, Any]] = {}
        self.default_timeout: float | None = None

    def script(self, method: str, *results: Any, repeat: bool = False) -> None:
        """Queue one or more results for `method`.

        Each result is either an `Event` to return or an `Exception`
        instance to raise. By default each call consumes the next result
        in order and calling past the end of the queue fails the test
        loudly (an `AssertionError`, not a silent None). Pass `repeat=True`
        to have a single scripted result reused for every call instead.
        """
        self._scripts[method] = {"queue": list(results), "repeat": repeat}

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name.startswith("_"):
            raise AttributeError(name)

        async def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            spec = self._scripts.get(name)
            if spec is None or not spec["queue"]:
                raise AssertionError(
                    f"FakeCommandHandler.{name}() called with no scripted result; "
                    f"call fake.commands.script({name!r}, Event(...)) in the test first"
                )
            result = spec["queue"][0] if spec["repeat"] else spec["queue"].pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        return _call

    def call_count(self, method: str) -> int:
        return sum(1 for called, _, _ in self.calls if called == method)


@dataclass
class FakeMeshCore:
    """A hardware-free stand-in for a connected `meshcore.MeshCore` client."""

    self_info: dict[str, Any] = field(
        default_factory=lambda: {"name": "test-node", "fw ver": 14, "ver": "v1.10.0-test"}
    )
    commands: FakeCommandHandler = field(default_factory=FakeCommandHandler)
    subscriptions: list[tuple[EventType, Callable[..., Any]]] = field(default_factory=list)
    disconnected: bool = False

    def subscribe(self, event_type: EventType, handler: Callable[..., Any]) -> None:
        self.subscriptions.append((event_type, handler))

    async def disconnect(self) -> None:
        self.disconnected = True
