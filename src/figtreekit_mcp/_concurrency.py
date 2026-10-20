# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Concurrency guard for process-global operations.

``serialized`` is a single global re-entrant lock.  It is acquired by every
MCP tool invocation (see ``server._threaded_tool``) because ``figtreekit``
mutates process-global taxonomy rank prefixes and warning filters, and because
Java/CLI child processes and ``--self-test`` are not safe to overlap.
Tool calls therefore execute one-at-a-time; the asyncio event loop stays
responsive because the lock is acquired inside the worker thread.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

# The global lock serialising CLI/JAR execution.
_global_lock = threading.RLock()


@contextmanager
def serialized() -> Iterator[None]:
    """Acquire the global serialisation lock (re-entrant)."""
    with _global_lock:
        yield


def acquire() -> None:
    _global_lock.acquire()


def release() -> None:
    _global_lock.release()
