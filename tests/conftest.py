from __future__ import annotations

import pytest
from click.testing import CliRunner

from meshcorectl.context_store import ContextStore


@pytest.fixture
def store(tmp_path):
    """A ContextStore backed by a throwaway file, never the user's real config."""
    return ContextStore(tmp_path / "config.yaml")


@pytest.fixture
def runner():
    return CliRunner()
