from __future__ import annotations

import logging

import pytest

from meshcorectl.logging_utils import redact_secrets


def test_redact_secrets_raises_meshcore_logger_to_info_while_active(meshcore_logger_at_debug):
    with redact_secrets():
        assert meshcore_logger_at_debug.level == logging.INFO
    assert meshcore_logger_at_debug.level == logging.DEBUG


def test_redact_secrets_restores_level_even_on_exception(meshcore_logger_at_debug):
    with pytest.raises(ValueError, match="boom"):
        with redact_secrets():
            raise ValueError("boom")
    assert meshcore_logger_at_debug.level == logging.DEBUG


def test_redact_secrets_leaves_notset_level_notset_when_never_configured():
    logger = logging.getLogger("meshcore")
    original = logger.level
    logger.setLevel(logging.NOTSET)
    try:
        with redact_secrets():
            assert logger.level == logging.INFO
        assert logger.level == logging.NOTSET
    finally:
        logger.setLevel(original)


def test_redact_secrets_does_not_touch_other_loggers():
    other = logging.getLogger("meshcorectl.somewhere")
    original = other.level
    other.setLevel(logging.DEBUG)
    try:
        with redact_secrets():
            assert other.level == logging.DEBUG
    finally:
        other.setLevel(original)
