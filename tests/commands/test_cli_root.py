from __future__ import annotations

import logging
import sys

import pytest

from meshcorectl import __version__
from meshcorectl.cli import cli, main
from meshcorectl.output import OutputFormat


def test_help_exits_zero(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "meshcorectl" in result.output


def test_no_subcommand_shows_help(runner):
    # Click's stock Group behavior: print usage and exit 2 (a missing-command
    # usage error), same as running `git` or `meshcorectl config` bare.
    result = runner.invoke(cli, [])
    assert result.exit_code == 2
    assert "Usage" in result.output


def test_version_flag_prints_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_invalid_output_format_rejected(runner):
    result = runner.invoke(cli, ["-o", "xml", "config", "get-contexts"])
    assert result.exit_code == 2
    assert "xml" in result.output


def test_unknown_subcommand_rejected(runner):
    result = runner.invoke(cli, ["bogus-command"])
    assert result.exit_code == 2


def test_verbosity_flag_raises_logging_to_debug(runner):
    root_logger = logging.getLogger()
    original_level = root_logger.level
    try:
        result = runner.invoke(cli, ["-vv", "config", "get-contexts"])
        assert result.exit_code == 0
        assert root_logger.level == logging.DEBUG
    finally:
        root_logger.setLevel(original_level)


def test_single_v_raises_logging_to_info(runner):
    root_logger = logging.getLogger()
    original_level = root_logger.level
    try:
        runner.invoke(cli, ["-v", "config", "get-contexts"])
        assert root_logger.level == logging.INFO
    finally:
        root_logger.setLevel(original_level)


def test_default_verbosity_is_warning(runner):
    root_logger = logging.getLogger()
    original_level = root_logger.level
    try:
        runner.invoke(cli, ["config", "get-contexts"])
        assert root_logger.level == logging.WARNING
    finally:
        root_logger.setLevel(original_level)


def test_output_format_str_is_the_plain_value():
    assert str(OutputFormat.JSON) == "json"
    assert str(OutputFormat.TABLE) == "table"


def test_main_runs_cli_and_exits_with_its_code(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["meshcorectl", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert "meshcorectl" in capsys.readouterr().out


def test_main_translates_keyboard_interrupt_to_exit_130(monkeypatch, capsys):
    def raise_keyboard_interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("meshcorectl.cli.cli", raise_keyboard_interrupt)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 130
    assert "aborted" in capsys.readouterr().err
