from __future__ import annotations

from meshcorectl.output.table import COLUMN_GAP, format_table, lookup


def test_lookup_simple_key():
    assert lookup({"name": "foo"}, "name") == "foo"


def test_lookup_dotted_path():
    assert lookup({"battery": {"percent": 87}}, "battery.percent") == 87


def test_lookup_missing_top_level_returns_none():
    assert lookup({}, "name") is None


def test_lookup_missing_nested_returns_none():
    assert lookup({"battery": {}}, "battery.percent") is None


def test_lookup_intermediate_not_a_mapping_returns_none():
    assert lookup({"battery": 5}, "battery.percent") is None


def test_format_table_basic_alignment():
    rows = [{"name": "alice", "hops": 1}, {"name": "bobby", "hops": 12}]
    out = format_table(rows, [("NAME", "name"), ("HOPS", "hops")])
    lines = out.splitlines()
    assert lines[0] == "NAME    HOPS"
    assert lines[1] == "alice   1"
    assert lines[2] == "bobby   12"


def test_format_table_no_trailing_whitespace_on_last_column():
    rows = [{"name": "a", "note": "x"}]
    out = format_table(rows, [("NAME", "name"), ("NOTE", "note")])
    for line in out.splitlines():
        assert line == line.rstrip()


def test_format_table_missing_value_renders_as_dash():
    rows = [{"name": "a"}]
    out = format_table(rows, [("NAME", "name"), ("TYPE", "type")])
    assert out.splitlines()[1] == "a".ljust(len("NAME")) + COLUMN_GAP + "-"


def test_format_table_empty_string_renders_as_dash():
    rows = [{"name": ""}]
    out = format_table(rows, [("NAME", "name")])
    assert out.splitlines()[1] == "-"


def test_format_table_boolean_renders_lowercase():
    rows = [{"name": "a", "flood": True}, {"name": "b", "flood": False}]
    out = format_table(rows, [("NAME", "name"), ("FLOOD", "flood")])
    assert "true" in out
    assert "false" in out


def test_format_table_list_value_joined_with_commas():
    rows = [{"name": "a", "tags": ["x", "y", "z"]}]
    out = format_table(rows, [("NAME", "name"), ("TAGS", "tags")])
    assert out.splitlines()[1] == "a".ljust(len("NAME")) + COLUMN_GAP + "x,y,z"


def test_format_table_empty_list_renders_as_dash():
    rows = [{"name": "a", "tags": []}]
    out = format_table(rows, [("NAME", "name"), ("TAGS", "tags")])
    assert out.splitlines()[1] == "a".ljust(len("NAME")) + COLUMN_GAP + "-"


def test_format_table_no_rows_is_header_only():
    out = format_table([], [("NAME", "name"), ("TYPE", "type")])
    assert out == "NAME   TYPE"


def test_format_table_single_column_no_padding():
    out = format_table([{"name": "alice"}], [("NAME", "name")])
    assert out.splitlines() == ["NAME", "alice"]


def test_format_table_dotted_column_key():
    rows = [{"battery": {"percent": 87}}]
    out = format_table(rows, [("BATTERY", "battery.percent")])
    assert out.splitlines()[1] == "87"


def test_format_table_widens_column_to_longest_value():
    # NAME is not the last column here, so it gets padded to the width of
    # its longest value ("a-very-long-contact-name") -- the last column
    # (HOPS) never is, per test_format_table_no_trailing_whitespace above.
    rows = [{"name": "a-very-long-contact-name", "hops": 1}, {"name": "short", "hops": 2}]
    out = format_table(rows, [("NAME", "name"), ("HOPS", "hops")])
    width = len("a-very-long-contact-name")
    header, first, second = out.splitlines()
    assert header == "NAME".ljust(width) + COLUMN_GAP + "HOPS"
    assert first == "a-very-long-contact-name" + COLUMN_GAP + "1"
    assert second == "short".ljust(width) + COLUMN_GAP + "2"
