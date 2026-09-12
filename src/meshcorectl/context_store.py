"""Named connection contexts, kubeconfig-style.

A YAML store of named connection profiles at
``~/.config/meshcorectl/config.yaml`` (or ``$XDG_CONFIG_HOME``), plus a
``current-context`` pointer -- the same shape as ``~/.kube/config``.

Every public method here is pure I/O and validation, with no dependency on
Click, asyncio, or the `meshcore` transport library.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_VALID_KINDS = ("ble", "serial", "tcp")


class ContextStoreError(Exception):
    """Base class for context-store problems."""


class ConfigFileCorruptError(ContextStoreError):
    """The config file exists but could not be parsed or validated."""


class ContextNotFoundError(ContextStoreError):
    """Raised when a named context does not exist."""

    def __init__(self, name: str):
        super().__init__(f'no context exists with the name "{name}"')
        self.name = name


def default_config_path() -> Path:
    """Return the default config file location, honoring $XDG_CONFIG_HOME."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "meshcorectl" / "config.yaml"


@dataclass(frozen=True)
class ConnectionSpec:
    """How to reach a device: exactly one of ble/serial/tcp.

    The boundary type ``connect.py`` consumes to open a live connection --
    it carries no live state itself.
    """

    kind: str
    # ble
    address: str | None = None
    name_filter: str | None = None
    # serial
    port: str | None = None
    baudrate: int = 115200
    # tcp
    host: str | None = None
    tcp_port: int = 5000

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"unknown connection kind {self.kind!r} (must be one of {_VALID_KINDS})"
            )
        if self.kind == "serial" and not self.port:
            raise ValueError("a serial connection requires 'port'")
        if self.kind == "tcp" and not self.host:
            raise ValueError("a tcp connection requires 'host'")

    def summary(self) -> str:
        """A one-line human summary, used in `config get-contexts` and error messages."""
        if self.kind == "ble":
            if self.address:
                return f"ble:{self.address}"
            if self.name_filter:
                return f"ble:name~{self.name_filter}"
            return "ble:<first found>"
        if self.kind == "serial":
            return f"serial:{self.port}@{self.baudrate}"
        return f"tcp:{self.host}:{self.tcp_port}"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.kind == "ble":
            if self.address:
                d["address"] = self.address
            if self.name_filter:
                d["name-filter"] = self.name_filter
        elif self.kind == "serial":
            d["port"] = self.port
            d["baudrate"] = self.baudrate
        else:  # tcp
            d["host"] = self.host
            d["port"] = self.tcp_port
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConnectionSpec:
        kind = d.get("kind")
        if kind == "ble":
            return cls(kind="ble", address=d.get("address"), name_filter=d.get("name-filter"))
        if kind == "serial":
            if "port" not in d:
                raise ValueError("serial connection is missing 'port'")
            return cls(kind="serial", port=d["port"], baudrate=int(d.get("baudrate", 115200)))
        if kind == "tcp":
            if "host" not in d:
                raise ValueError("tcp connection is missing 'host'")
            return cls(kind="tcp", host=d["host"], tcp_port=int(d.get("port", 5000)))
        raise ValueError(f"unknown connection kind {kind!r} (must be one of {_VALID_KINDS})")


@dataclass
class Context:
    """One named, addressable device profile."""

    name: str
    connection: ConnectionSpec
    timeout: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"connection": self.connection.to_dict()}
        if self.timeout is not None:
            d["timeout"] = self.timeout
        return d

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> Context:
        if "connection" not in d:
            raise ValueError(f"context {name!r} is missing 'connection'")
        timeout = d.get("timeout")
        return cls(
            name=name,
            connection=ConnectionSpec.from_dict(d["connection"]),
            timeout=float(timeout) if timeout is not None else None,
        )


@dataclass
class Config:
    """The whole config file contents."""

    current_context: str | None = None
    contexts: dict[str, Context] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.current_context is not None:
            d["current-context"] = self.current_context
        d["contexts"] = {name: ctx.to_dict() for name, ctx in self.contexts.items()}
        if self.defaults:
            d["defaults"] = self.defaults
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Config:
        contexts_raw = d.get("contexts") or {}
        if not isinstance(contexts_raw, dict):
            raise ValueError("'contexts' must be a mapping of name -> context")
        contexts = {name: Context.from_dict(name, c) for name, c in contexts_raw.items()}
        defaults = d.get("defaults") or {}
        if not isinstance(defaults, dict):
            raise ValueError("'defaults' must be a mapping")
        return cls(current_context=d.get("current-context"), contexts=contexts, defaults=defaults)


class ContextStore:
    """Loads/saves `Config` and provides the `config` subcommand's operations."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_config_path()

    def load(self) -> Config:
        if not self.path.exists():
            return Config()
        try:
            raw = yaml.safe_load(self.path.read_text())
        except yaml.YAMLError as exc:
            raise ConfigFileCorruptError(f"could not parse {self.path}: {exc}") from exc
        if raw is None:
            return Config()
        if not isinstance(raw, dict):
            raise ConfigFileCorruptError(
                f"{self.path} must contain a YAML mapping at the top level"
            )
        try:
            return Config.from_dict(raw)
        except ValueError as exc:
            raise ConfigFileCorruptError(f"invalid config in {self.path}: {exc}") from exc

    def save(self, config: Config) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False))

    def list_contexts(self) -> list[Context]:
        return sorted(self.load().contexts.values(), key=lambda c: c.name)

    def get_context(self, name: str) -> Context:
        cfg = self.load()
        try:
            return cfg.contexts[name]
        except KeyError:
            raise ContextNotFoundError(name) from None

    def current_context(self) -> Context:
        """Return the `Context` the `current-context` pointer names.

        Raises `ContextStoreError` if unset, `ContextNotFoundError` if it
        points at a context that no longer exists.
        """
        cfg = self.load()
        if not cfg.current_context:
            raise ContextStoreError("current-context is not set")
        return self.get_context(cfg.current_context)

    def use_context(self, name: str) -> None:
        cfg = self.load()
        if name not in cfg.contexts:
            raise ContextNotFoundError(name)
        cfg.current_context = name
        self.save(cfg)

    def set_context(
        self,
        name: str,
        *,
        connection: ConnectionSpec,
        timeout: float | None = None,
        set_current: bool = False,
    ) -> None:
        """Create or overwrite a context. Becomes current if it's the first
        context ever defined, or if `set_current` is explicitly requested."""
        cfg = self.load()
        cfg.contexts[name] = Context(name=name, connection=connection, timeout=timeout)
        if set_current or cfg.current_context is None:
            cfg.current_context = name
        self.save(cfg)

    def delete_context(self, name: str) -> bool:
        """Delete a context. Returns True if it was the current context
        (in which case current-context is cleared)."""
        cfg = self.load()
        if name not in cfg.contexts:
            raise ContextNotFoundError(name)
        del cfg.contexts[name]
        was_current = cfg.current_context == name
        if was_current:
            cfg.current_context = None
        self.save(cfg)
        return was_current
