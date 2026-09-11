"""Parses kubectl-`--since`-style relative duration strings ("30m", "2h", "1d").

Shared by `logs --since` and `top --history --since` now; Phase 3's `-l`
selector grammar (the `u<2d`/`u>1h` clauses ported from the original tool's
`apply_to` filter) will reuse this same parser rather than duplicating it.
"""

from __future__ import annotations

import re

_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

_PATTERN = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>[smhd])$")


def parse_duration(text: str) -> float:
    """Parse "30m", "2h", "1.5d", "45s" into a number of seconds.

    Raises `ValueError` (with a message naming the offending text) on
    anything else, so callers can surface it via `click.ClickException`.
    """
    match = _PATTERN.match(text.strip())
    if not match:
        raise ValueError(
            f"invalid duration {text!r}: expected a number followed by s/m/h/d, e.g. '30m'"
        )
    return float(match.group("value")) * _UNIT_SECONDS[match.group("unit")]
