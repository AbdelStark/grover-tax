"""Unit tests for `grover_tax.logging`."""

from __future__ import annotations

import logging as stdlib_logging

from grover_tax.logging import (
    _CONFIGURED_SENTINEL,
    LOG_FORMAT,
    configure,
    get_logger,
)


def _reset_root_logger() -> None:
    """Strip the configured-sentinel and handlers so each test starts clean."""
    root = stdlib_logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    if hasattr(root, _CONFIGURED_SENTINEL):
        delattr(root, _CONFIGURED_SENTINEL)


def test_configure_attaches_one_handler() -> None:
    _reset_root_logger()
    try:
        configure()
        root = stdlib_logging.getLogger()
        assert getattr(root, _CONFIGURED_SENTINEL) is True
        handler_count = len(root.handlers)
        assert handler_count >= 1
        # Calling configure() again is a no-op.
        configure()
        assert len(root.handlers) == handler_count
    finally:
        _reset_root_logger()


def test_configure_respects_level() -> None:
    _reset_root_logger()
    try:
        configure(level=stdlib_logging.CRITICAL)
        assert stdlib_logging.getLogger().level == stdlib_logging.CRITICAL
    finally:
        _reset_root_logger()


def test_log_format_is_the_canonical_spec_format() -> None:
    # Per `docs/spec/05-observability.md` §"Logging" the format is frozen.
    assert LOG_FORMAT == "%(asctime)s %(name)s %(levelname)s %(message)s"


def test_get_logger_returns_named_child_and_configures_root() -> None:
    _reset_root_logger()
    try:
        log = get_logger("grover_tax.test")
        assert log.name == "grover_tax.test"
        root = stdlib_logging.getLogger()
        assert getattr(root, _CONFIGURED_SENTINEL) is True
    finally:
        _reset_root_logger()
