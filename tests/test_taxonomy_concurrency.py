# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Regression test: taxonomy rank-prefix scopes must not leak or race."""

from __future__ import annotations

import threading
import time

from figtreekit.taxonomy import get_rank_prefixes

from figtreekit_mcp._core import temporary_rank_prefixes


def test_parallel_rank_prefix_scopes_are_isolated() -> None:
    before = dict(get_rank_prefixes())
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        prefix = f"x{index}"
        try:
            barrier.wait(timeout=5)
            with temporary_rank_prefixes(f"{prefix}:family"):
                if prefix not in get_rank_prefixes():
                    raise AssertionError(f"{prefix} missing inside its own scope")
                time.sleep(0.02)
        except BaseException as exc:  # noqa: BLE001 - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    assert dict(get_rank_prefixes()) == before
