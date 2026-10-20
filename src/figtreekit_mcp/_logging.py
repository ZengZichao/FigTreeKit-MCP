# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Logging for FigTreeKit-MCP.

Protocol rule: **stdout carries only MCP protocol frames.**  All application
logging goes to stderr (and optionally a log file).  This module provides a
plain, deterministic formatter with ISO-8601 timestamps matching figtreekit's
convention, plus a ``FlushStreamHandler`` that forces a flush before exit so
that crash diagnostics are never lost.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Optional, TextIO


class _ISOTimeFormatter(logging.Formatter):
    """Formatter emitting ``YYYY-MM-DDTHH:MM:SS.mmmZ`` timestamps."""

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FlushStreamHandler(logging.StreamHandler):
    """Stream handler that flushes every record (crash-safe diagnostics)."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        try:
            self.flush()
        except Exception:  # pragma: no cover - best-effort
            pass


def _level_from_verbosity(verbose: int, quiet: bool) -> int:
    if quiet:
        return logging.ERROR
    if verbose >= 2:
        return logging.DEBUG
    if verbose == 1:
        return logging.INFO
    return logging.WARNING


def setup_logger(
    *,
    name: str = "figtreekit-mcp",
    verbose: int = 0,
    quiet: bool = False,
    log_file: Optional[str] = None,
    stream: Optional[TextIO] = None,
) -> logging.Logger:
    """Configure the process logger: stderr + optional file, both guarded.

    Args:
        name: Logger name.
        verbose: ``-v/-vv`` count (0..2).
        quiet: ``-q`` (ERROR only).
        log_file: Optional path to append all-level records to.
        stream: Stream for the console handler (defaults to ``sys.stderr``).

    Returns:
        The configured logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Deduplicate handlers when re-configured (e.g. called twice in tests).
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = _ISOTimeFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = FlushStreamHandler(stream=stream if stream is not None else sys.stderr)
    console.setLevel(_level_from_verbosity(verbose, quiet))
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "figtreekit-mcp") -> logging.Logger:
    """Return the configured logger, lazily configuring with safe defaults."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        setup_logger(name=name)
    return logger


# Convenient aliases used across the code base.
log_debug = lambda msg: get_logger().debug(msg)  # noqa: E731 (doc parity helper)
