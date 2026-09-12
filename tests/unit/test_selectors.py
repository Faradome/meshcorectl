from __future__ import annotations

import time

import pytest

from meshcorectl.selectors import (
    Clause,
    SelectorError,
    filter_contacts,
    matches,
    parse_selector,
)

# --- parse_selector -----------------------------------------------------------


def test_parse_selector_single_flag():
    assert parse_selector("d") == [Clause("d", None, None)]


def test_parse_selector_single_value_clause():
    assert parse_selector("t=1") == [Clause("t", "=", "1")]


def test_parse_selector_multiple_clauses():
    assert parse_selector("t=1,u<2d") == [
        Clause("t", "=", "1"),
        Clause("u", "<", "2d"),
    ]


def test_parse_selector_strips_whitespace():
    assert parse_selector(" t = 1 , d ") == [Clause("t", "=", "1"), Clause("d", None, None)]


def test_parse_selector_ignores_empty_segments():
    assert parse_selector("t=1,,d") == [Clause("t", "=", "1"), Clause("d", None, None)]


@pytest.mark.parametrize("op", ["<", ">", "="])
def test_parse_selector_all_ops(op):
    assert parse_selector(f"h{op}2") == [Clause("h", op, "2")]


def test_parse_selector_empty_string_raises():
    with pytest.raises(SelectorError, match="empty selector"):
        parse_selector("")


def test_parse_selector_unknown_field_raises():
    with pytest.raises(SelectorError, match="unknown selector field"):
        parse_selector("z=1")


def test_parse_selector_missing_value_raises():
    with pytest.raises(SelectorError, match="missing value"):
        parse_selector("t=")


def test_parse_selector_garbage_raises():
    with pytest.raises(SelectorError, match="invalid selector clause"):
        parse_selector("not-a-clause-at-all")


def test_parse_selector_whitespace_only_raises():
    with pytest.raises(SelectorError, match="empty selector"):
        parse_selector("   ")


def test_parse_selector_non_integer_hops_raises():
    """`h` needs an integer; a bad value must be rejected here, at parse
    time -- not surface as a raw ValueError out of `int()` deep inside
    `matches()`, after a command has already connected to a device."""
    with pytest.raises(SelectorError, match="'h' needs an integer hop count"):
        parse_selector("h>abc")


def test_parse_selector_non_duration_lastmod_raises():
    """Same as above, for `u`: neither a duration suffix nor a bare number."""
    with pytest.raises(SelectorError, match="'u' needs a duration"):
        parse_selector("u<not-a-duration")


def test_parse_selector_valid_hops_and_duration_values_pass():
    # Regression guard: the validation added for the two tests above must
    # not reject the values it's supposed to accept.
    parse_selector("h>2")
    parse_selector("u<2d")
    parse_selector("u>1500000000")  # a bare epoch timestamp is also valid


# --- matches: t (type) ----------------------------------------------------------


def test_matches_type_by_name():
    contact = {"type": "repeater"}
    assert matches(contact, parse_selector("t=repeater")) is True
    assert matches(contact, parse_selector("t=client")) is False


def test_matches_type_by_legacy_numeric_code():
    contact = {"type": "repeater"}
    assert matches(contact, parse_selector("t=2")) is True
    assert matches(contact, parse_selector("t=1")) is False


def test_matches_type_case_insensitive():
    contact = {"type": "repeater"}
    assert matches(contact, parse_selector("t=REPEATER")) is True


# --- matches: h/d/f (hops) -------------------------------------------------------


@pytest.mark.parametrize(
    ("hops", "selector", "expected"),
    [
        (3, "h=3", True),
        (3, "h=2", False),
        (3, "h>2", True),
        (3, "h<2", False),
        (0, "d", True),
        (3, "d", False),
        (-1, "f", True),
        (0, "f", False),
        (None, "f", True),  # missing hops treated as unknown/flood
    ],
)
def test_matches_hops_variants(hops, selector, expected):
    contact = {"hops": hops}
    assert matches(contact, parse_selector(selector)) is expected


def test_matches_h_missing_hops_is_false():
    assert matches({}, parse_selector("h=1")) is False


# --- matches: u (updated/lastmod) -------------------------------------------------


def test_matches_u_absolute_epoch():
    contact = {"lastmod": 1000}
    assert matches(contact, parse_selector("u>500")) is True
    assert matches(contact, parse_selector("u<500")) is False


def test_matches_u_relative_duration_stale():
    old_contact = {"lastmod": time.time() - 3 * 86400}  # 3 days ago
    assert matches(old_contact, parse_selector("u<2d")) is True  # stale: not updated in 2d


def test_matches_u_relative_duration_fresh():
    fresh_contact = {"lastmod": time.time() - 60}  # 1 minute ago
    assert matches(fresh_contact, parse_selector("u>1h")) is True  # updated within the last hour
    assert matches(fresh_contact, parse_selector("u<1h")) is False


def test_matches_u_missing_lastmod_is_false():
    assert matches({}, parse_selector("u>0")) is False


# --- matches: multiple ANDed clauses -----------------------------------------------


def test_matches_all_clauses_must_hold():
    contact = {"type": "repeater", "hops": 0}
    assert matches(contact, parse_selector("t=repeater,d")) is True
    assert matches(contact, parse_selector("t=client,d")) is False


# --- filter_contacts ----------------------------------------------------------------


def test_filter_contacts_no_selector_returns_all():
    contacts = [{"type": "client"}, {"type": "repeater"}]
    assert filter_contacts(contacts, None) == contacts


def test_filter_contacts_explicit_empty_string_raises():
    """An empty `-l ""` is what a shell hands over for `-l "$VAR"` when
    $VAR is unset/empty -- it must be rejected as an invalid selector, not
    silently treated the same as "-l wasn't passed at all" and match every
    contact on a command like `delete`."""
    contacts = [{"type": "client"}, {"type": "repeater"}]
    with pytest.raises(SelectorError, match="empty selector"):
        filter_contacts(contacts, "")


def test_filter_contacts_applies_selector():
    contacts = [{"name": "a", "type": "client"}, {"name": "b", "type": "repeater"}]
    result = filter_contacts(contacts, "t=repeater")
    assert [c["name"] for c in result] == ["b"]
