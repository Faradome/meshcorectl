from __future__ import annotations

import json

import pytest
import yaml

from meshcorectl.output import OutputFormat, render, resources


@pytest.fixture
def widget_kind():
    """Registers a synthetic resource kind for the duration of one test,
    per output/resources.py's `temporary()` helper, so these tests don't
    depend on any real resource (Phase 2+) being registered yet."""
    spec = resources.ResourceSpec(
        columns=(("NAME", "name"), ("TYPE", "type")),
        wide_columns=(("HOPS", "hops"),),
        name_key="name",
    )
    with resources.temporary("widget", spec):
        yield "widget"


def test_resources_get_unknown_kind_raises():
    with pytest.raises(KeyError, match="no resource spec registered"):
        resources.get("does-not-exist")


def test_resources_temporary_cleans_up_after_itself():
    assert not resources.is_registered("widget")
    with resources.temporary("widget", resources.ResourceSpec(columns=(("NAME", "name"),))):
        assert resources.is_registered("widget")
    assert not resources.is_registered("widget")


def test_resources_temporary_restores_previous_registration():
    original = resources.ResourceSpec(columns=(("A", "a"),))
    resources.register("widget", original)
    try:
        with resources.temporary("widget", resources.ResourceSpec(columns=(("B", "b"),))):
            assert resources.get("widget") is not original
        assert resources.get("widget") is original
    finally:
        resources.unregister("widget")


def test_render_json_single_object_stays_an_object(widget_kind):
    out = render({"name": "alice", "type": 1}, OutputFormat.JSON, widget_kind)
    assert json.loads(out) == {"name": "alice", "type": 1}


def test_render_json_list_stays_a_list(widget_kind):
    rows = [{"name": "alice", "type": 1}, {"name": "bob", "type": 2}]
    out = render(rows, OutputFormat.JSON, widget_kind)
    assert json.loads(out) == rows


def test_render_yaml_round_trips(widget_kind):
    rows = [{"name": "alice", "type": 1}]
    out = render(rows, OutputFormat.YAML, widget_kind)
    assert yaml.safe_load(out) == rows


def test_render_name_prints_one_name_per_line(widget_kind):
    rows = [{"name": "alice", "type": 1}, {"name": "bob", "type": 2}]
    out = render(rows, OutputFormat.NAME, widget_kind)
    assert out == "alice\nbob"


def test_render_table_uses_default_columns_only(widget_kind):
    rows = [{"name": "alice", "type": 1, "hops": 3}]
    out = render(rows, OutputFormat.TABLE, widget_kind)
    assert "NAME" in out and "TYPE" in out
    assert "HOPS" not in out


def test_render_wide_appends_wide_columns(widget_kind):
    rows = [{"name": "alice", "type": 1, "hops": 3}]
    out = render(rows, OutputFormat.WIDE, widget_kind)
    assert "NAME" in out and "TYPE" in out and "HOPS" in out


def test_render_table_single_object_is_one_row(widget_kind):
    out = render({"name": "alice", "type": 1}, OutputFormat.TABLE, widget_kind)
    assert len(out.splitlines()) == 2  # header + one data row
