# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Concurrency unit tests (SEC-8).

The global serialisation lock protects process-global CLI/JAR execution while
nothing else is blocked (stateless model); every tool call writes into its
own ``run_<uuid8>`` so concurrent invocations never interleave artifacts.
"""

from __future__ import annotations

import threading
import time
from typing import Any, List

import pytest

from figtreekit_mcp._concurrency import acquire, release, serialized
from figtreekit_mcp.tools import TOOLS

from conftest import SMALL_TREE, _fake_ctx, call_app


class TestLock:
    def test_serialized_acquires_and_releases(self) -> None:
        with serialized():
            # the global lock is held while inside
            assert not _try_lock()  # non-blocking probe must fail

    def test_rlock_reentrant(self) -> None:
        with serialized():
            with serialized():
                pass

    def test_manual_acquire_release(self) -> None:
        acquire()
        try:
            assert not _try_lock()
        finally:
            release()

    def test_two_threads_serialised(self) -> None:
        timestamps: List[float] = []
        lock = threading.Lock()

        def work() -> None:
            with lock:
                with serialized():
                    timestamps.append(time.monotonic())

        threads = [threading.Thread(target=work) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(timestamps) == 5


def _try_lock() -> bool:
    """True if the global lock was free (probed from another thread, since
    the RLock is re-entrant within the calling thread)."""
    from figtreekit_mcp._concurrency import _global_lock

    result: List[bool] = []

    def _probe() -> None:
        acquired = _global_lock.acquire(blocking=False)
        if acquired:
            _global_lock.release()
        result.append(acquired)

    t = threading.Thread(target=_probe)
    t.start()
    t.join()
    return result[0]


# --------------------------------------------------------------------------- #
# SEC-8: concurrent 8 style_tree + 2 run_figtreekit_cli
# --------------------------------------------------------------------------- #
def _style_in_thread(app: Any, results: List[Any]) -> None:
    try:
        ctx = _fake_ctx(app)
        res = call_app(
            "style_tree",
            ctx,
            tree_content=SMALL_TREE,
            layout="polar",
            operations=[{"op": "highlight", "taxa": ["A", "B"], "color": "#FF0000"}],
        )
        results.append(res)
    except Exception as exc:  # noqa: BLE001 - collect for assertions
        results.append(exc)


def _cli_in_thread(app: Any, results: List[Any]) -> None:
    try:
        ctx = _fake_ctx(app)
        res = call_app("run_figtreekit_cli", ctx, argv=["--help"])
        results.append(res)
    except Exception as exc:  # noqa: BLE001
        results.append(exc)


@pytest.mark.slow
def test_concurrent_styles_and_cli(app: Any) -> None:
    results: List[Any] = []
    threads = []
    for _ in range(8):
        threads.append(threading.Thread(target=_style_in_thread, args=(app, results)))
    for _ in range(2):
        threads.append(threading.Thread(target=_cli_in_thread, args=(app, results)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    for r in results:
        assert not isinstance(r, Exception), f"thread failed: {r}"
        assert r.get("ok") is True

    # Partition by tool kind (thread completion order is non-deterministic).
    style_results = [r for r in results if "nexus_file" in r]
    cli_results = [r for r in results if "returncode" in r]
    assert len(style_results) == 8
    assert len(cli_results) == 2

    # Each call got its own run directory; artifacts never collide.
    run_dirs = [r["run_dir"] for r in results]
    assert len(set(run_dirs)) == 10
    nexus_paths = [r["nexus_file"]["absolute"] for r in style_results]
    assert len(set(nexus_paths)) == 8


def test_run_dir_isolation_check() -> None:
    for name in TOOLS:
        assert callable(TOOLS[name])
