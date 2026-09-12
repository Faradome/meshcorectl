"""Keeps plaintext secrets out of `--verbose` debug logs.

The `meshcore` library logs everything on its own `"meshcore"` logger --
including a hex dump of every outbound frame (`commands/base.py`'s
"Sending raw data: <hex>") and, for a handful of commands, the plaintext
secret itself: a login password (`commands/messaging.py`'s login sender),
a device PIN (`commands/device.py`'s PIN setter), and message/channel
text (`commands/messaging.py`'s message senders) -- all at DEBUG.

`meshcorectl -vv` sets the root logger to DEBUG so operators can debug
connection issues, which would otherwise print those secrets straight to
the terminal -- and into journald/CI logs when run unattended (see
CWE-532). `redact_secrets()` briefly raises the upstream logger's own
level above DEBUG around a single call that hands it a secret, without
touching `-vv` debug output for anything else (connection lifecycle,
frame types, timeouts, and so on stay visible).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

UPSTREAM_LOGGER_NAME = "meshcore"


@contextmanager
def redact_secrets() -> Iterator[None]:
    """Suppress the upstream `meshcore` logger's DEBUG output for the
    duration of the `with` block, regardless of `-vv`.

    Wrap calls that hand a plaintext secret to
    `MeshCoreConnection.commands` -- the library logs the outbound frame,
    secret included, at DEBUG. Safe to use from async code: entering and
    exiting only flips a logger's level, nothing is awaited.
    """
    logger = logging.getLogger(UPSTREAM_LOGGER_NAME)
    previous = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.setLevel(previous)
