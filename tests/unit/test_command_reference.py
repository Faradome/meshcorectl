"""Keeps docs/command-reference.md honest: regenerate it in memory from
the live CLI and diff against what's checked in. A command added, renamed,
or re-worded without re-running
`python3 scripts/generate_command_reference.py` fails this test instead of
silently rotting (PLAN.md §7's whole point for this doc).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import click

from meshcorectl.cli import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_command_reference.py"
DOC_PATH = REPO_ROOT / "docs" / "command-reference.md"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_command_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_reference_is_up_to_date():
    generator = _load_generator()
    expected = generator.build_reference(cli, "meshcorectl")
    actual = DOC_PATH.read_text()
    assert actual == expected, (
        "docs/command-reference.md is out of date; regenerate it with "
        "`python3 scripts/generate_command_reference.py`"
    )


def test_command_reference_lists_every_top_level_command():
    generator = _load_generator()
    text = generator.build_reference(cli, "meshcorectl")
    root_ctx = click.Context(cli, info_name="meshcorectl")
    for name in sorted(cli.list_commands(root_ctx)):
        assert f"## `meshcorectl {name}`" in text
