# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Logging unit tests.

Golden rule: application logs go to stderr (never stdout — the MCP protocol
lane); timestamps are ISO-8601 with milliseconds and a ``Z`` suffix; the
verbosity level ladder is ``-q``→ERROR, default→WARNING, ``-v``→INFO,
``-vv``→DEBUG.
"""

from __future__ import annotations

import io
import logging
import re
from typing import TextIO

import pytest

from figtreekit_mcp._logging import _ISOTimeFormatter, _level_from_verbosity, setup_logger

_NAME = "figtreekit-mcp-test-logging"


@pytest.fixture(autouse=True)
def _clean_logger() -> None:
    yield
    lg = logging.getLogger(_NAME)
    for h in list(lg.handlers):
        lg.removeHandler(h)
    lg.setLevel(logging.NOTSET)


def _capture(*, verbose: int = 0, quiet: bool = False) -> tuple[logging.Logger, io.StringIO, io.StringIO]:
    err, out = io.StringIO(), io.StringIO()
    logger = setup_logger(name=_NAME, verbose=verbose, quiet=quiet, stream=err)
    # A stdout-side handler must never exist for this logger.
    assert all(getattr(h, "stream", None) is not out for h in logger.handlers)
    return logger, err, out


class TestLevels:
    def test_default_warning(self) -> None:
        assert _level_from_verbosity(0, False) == logging.WARNING

    def test_verbose_ladder(self) -> None:
        assert _level_from_verbosity(1, False) == logging.INFO
        assert _level_from_verbosity(2, False) == logging.DEBUG
        assert _level_from_verbosity(0, True) == logging.ERROR
        assert _level_from_verbosity(3, True) == logging.ERROR

    def test_quiet_hides_warning(self) -> None:
        logger, err, _ = _capture(quiet=True)
        logger.warning("hidden")
        assert err.getvalue() == ""

    def test_verbose_shows_info(self) -> None:
        logger, err, _ = _capture(verbose=1)
        logger.info("visible")
        assert "visible" in err.getvalue()

    def test_warning_shown_by_default(self) -> None:
        logger, err, _ = _capture()
        logger.warning("warn-msg")
        assert "warn-msg" in err.getvalue()


class TestTargets:
    def test_log_never_goes_to_stdout(self) -> None:
        logger, err, out = _capture(verbose=2)
        logger.debug("debug-msg")
        assert "debug-msg" in err.getvalue()
        assert out.getvalue() == ""

    def test_log_file_target(self, tmp_path) -> None:
        logf = str(tmp_path / "mcp.log")
        err = io.StringIO()
        logger = setup_logger(name=_NAME, verbose=2, log_file=logf, stream=err)
        logger.error("boom")
        content = open(logf, encoding="utf-8").read()
        assert "boom" in content
        assert "boom" in err.getvalue()


class TestISOFormat:
    def test_timestamp_format(self) -> None:
        logger, err, _ = _capture(verbose=2)
        logger.info("ts-msg")
        line = err.getvalue().splitlines()[0]
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z) (INFO|WARNING|LEVEL) ", line)
        assert m is not None, f"unexpected line: {line!r}"

    def test_formatter_direct(self) -> None:
        fm = _ISOTimeFormatter("%(asctime)s")
        rec = logging.LogRecord(_NAME, logging.INFO, __file__, 1,
                                "m", (), None)
        rec.created = 1_700_000_000.123456
        assert fm.formatTime(rec) == "2023-11-14T22:13:20.123Z"


def test_handler_dedup_on_second_setup() -> None:
    err = io.StringIO()
    setup_logger(name=_NAME, stream=err)
    setup_logger(name=_NAME, stream=err)
    logger = setup_logger(name=_NAME, stream=err)
    assert len(logger.handlers) <= 2  # console (+ file when configured)
    assert sum(1 for h in logger.handlers if isinstance(h, logging.StreamHandler)) == 1
