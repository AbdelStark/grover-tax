"""Logging configuration for `grover_tax` Python entry points.

Per `docs/spec/05-observability.md` §"Logging", Python entry points use
`logging.basicConfig(level=logging.INFO, format=...)`. This module exposes a
single idempotent configurator (`configure()`) that the four entry points
(`gen_fixtures`, `analyze`, `plot`, `sim_reference`) call before they emit
any log records.

Idempotence matters because `pytest` plugins, `uv run`, and the standalone
`__main__` flow can all end up calling `configure()` more than once. We
detect a prior call by checking for a sentinel attribute on the root logger.

This module is named `logging.py` for parity with the issue specification.
Absolute imports (the Python 3 default) mean inner `import logging` lines
resolve to the standard library, not to this module — but to avoid even the
appearance of shadowing, we import the stdlib module under its own name and
do not re-export anything from it.
"""

from __future__ import annotations

import logging as _stdlib_logging

__all__ = ["LOG_FORMAT", "configure", "get_logger"]

# Per RFC-0010 (environmental hygiene) and SPEC §"Logging", the line format is
# load-bearing for the proverlog grammar parsing in `analyze.py`. Keep the
# format stable; if it changes, RFC-0011's M7 parser must change in lockstep.
LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

_CONFIGURED_SENTINEL = "_grover_tax_logging_configured"


def configure(level: int = _stdlib_logging.INFO) -> None:
    """Initialise root logging exactly once per process.

    Args:
        level: Log level to set on the root logger. Defaults to `INFO`,
            which is what every harness invocation uses. Tests may pass a
            higher level (`logging.CRITICAL`) to silence the harness.

    Calling `configure()` more than once is a no-op — the function leaves
    the existing handler set intact, which keeps test capture (`caplog`)
    working and prevents duplicated handler emission.
    """
    root = _stdlib_logging.getLogger()
    if getattr(root, _CONFIGURED_SENTINEL, False):
        return
    _stdlib_logging.basicConfig(level=level, format=LOG_FORMAT)
    # Mark the root logger so a subsequent call short-circuits.
    setattr(root, _CONFIGURED_SENTINEL, True)


def get_logger(name: str) -> _stdlib_logging.Logger:
    """Return a child logger; configures the root once on first use.

    Equivalent to `logging.getLogger(name)` but guarantees the root logger
    has been configured per `configure()` before the caller touches it.
    """
    configure()
    return _stdlib_logging.getLogger(name)
