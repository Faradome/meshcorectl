from __future__ import annotations

import pytest

from meshcorectl.durations import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("30s", 30),
        ("45m", 45 * 60),
        ("2h", 2 * 3600),
        ("1d", 86400),
        ("1.5h", 1.5 * 3600),
    ],
)
def test_parse_duration_valid(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "5", "5x", "h5", "-5m", "five minutes"])
def test_parse_duration_rejects_invalid(text):
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration(text)


def test_parse_duration_strips_whitespace():
    assert parse_duration("  10m  ") == 600
