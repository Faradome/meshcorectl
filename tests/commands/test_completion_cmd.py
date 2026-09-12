from __future__ import annotations

from tests.conftest import invoke


def test_completion_bash(runner, store):
    result = invoke(runner, store, "completion", "bash")
    assert result.exit_code == 0, result.output
    assert "_MESHCORECTL_COMPLETE" in result.output
    assert "complete -o" in result.output


def test_completion_zsh(runner, store):
    result = invoke(runner, store, "completion", "zsh")
    assert result.exit_code == 0, result.output
    assert "_MESHCORECTL_COMPLETE" in result.output
    assert "#compdef meshcorectl" in result.output


def test_completion_fish(runner, store):
    result = invoke(runner, store, "completion", "fish")
    assert result.exit_code == 0, result.output
    assert "_MESHCORECTL_COMPLETE" in result.output
    assert "complete --no-files --command meshcorectl" in result.output


def test_completion_rejects_unknown_shell(runner, store):
    result = invoke(runner, store, "completion", "powershell")
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_completion_help_shows_load_instructions(runner, store):
    result = invoke(runner, store, "completion", "--help")
    assert result.exit_code == 0
    assert "source <(meshcorectl completion bash)" in result.output
