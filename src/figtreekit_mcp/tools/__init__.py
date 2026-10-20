# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Tool handlers registry and shared helpers.

Every handler has the signature ``fn(ctx: Context, **kwargs) -> dict`` and
returns a JSON-serialisable dict (either ``ok: true`` result or the unified
error envelope).  Handlers are registered here by name so that ``server.py``
and the test suite share exactly one source of truth.
"""

from __future__ import annotations

import inspect
import itertools
import json
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from mcp.server.fastmcp import Context

from .._errors import ToolError
from .._workspace import RunStorage

if TYPE_CHECKING:  # pragma: no cover
    from ..server import AppContext

# name → handler (T01..T21, one entry per tool module import below)
TOOLS: Dict[str, Callable[..., Dict[str, Any]]] = {}


def tool(name: str):
    """Register a handler under its MCP tool name."""

    def deco(fn: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        if name in TOOLS:
            raise ValueError(f"duplicate tool registration: {name}")
        TOOLS[name] = fn
        return fn

    return deco


# --------------------------------------------------------------------------- #
# Context helpers
# --------------------------------------------------------------------------- #
def get_app(ctx: Context) -> "AppContext":
    """Return the lifespan AppContext (see ``server.lifespan``)."""
    lctx = getattr(ctx, "request_context", None)
    app = getattr(lctx, "lifespan_context", None) if lctx is not None else None
    if app is None:
        raise ToolError("internal_error", "缺少服务器上下文（lifespan 未初始化）", error_key="no_app_context")
    return app


_RUN_COUNTER = itertools.count()


def require_run(ctx: Context) -> RunStorage:
    """Allocate (once per call) the ``run_<uuid8>`` directory for this call."""
    app = get_app(ctx)
    if not hasattr(ctx, "_run_storage"):
        run = app.workspace.new_run()
        setattr(ctx, "_run_storage", run)
        # Enforce --keep-runs during long-lived sessions, not only at shutdown.
        if next(_RUN_COUNTER) % 16 == 0:
            try:
                app.workspace.cleanup()
            except OSError:  # pragma: no cover - best-effort housekeeping
                pass
        return run
    return getattr(ctx, "_run_storage")


def get_run_dir(ctx: Context) -> Optional[str]:
    storage = getattr(ctx, "_run_storage", None)
    return storage.name if storage else None


def resolve_mapping_file(app: "AppContext", path: Optional[str]) -> Optional[str]:
    """Whitelist-check a taxonomy mapping file; returns the resolved path."""
    if not path:
        return None
    resolved = app.workspace.assert_readable(path)
    app.workspace.check_file_size(resolved)
    return str(resolved)


def progress(ctx: Context, progress: int, total: int, message: str = "") -> None:
    """Best-effort progress notification (advisory; never raises).

    Tool handlers run in AnyIO worker threads (see ``server._threaded_tool``),
    while ``Context.report_progress`` / ``Context.info`` are coroutines bound
    to the server's event loop.  Inside a worker thread they are marshalled
    back with :func:`anyio.from_thread.run`; synchronous test doubles (and
    ``--self-test``'s fake context) are called directly.  Failures are
    swallowed on purpose — progress must never break a tool call.
    """
    _notify(ctx, "report_progress", progress, total)
    if message:
        _notify(ctx, "info", message)


def _notify(ctx: Any, method_name: str, *args: Any) -> None:
    """Invoke an async Context method from a worker thread, best effort."""
    try:
        method = getattr(ctx, method_name, None)
    except Exception:  # noqa: BLE001 - a broken attribute must not fail the call
        return
    if method is None:
        return
    try:
        from anyio.from_thread import run as run_on_loop
    except Exception:  # pragma: no cover - anyio is a hard MCP dependency
        run_on_loop = None
    if run_on_loop is not None:
        try:
            run_on_loop(method, *args)
            return
        except Exception:  # noqa: BLE001 - not a worker thread / sync method
            pass
    try:
        result = method(*args)
        # Never leave an unawaited coroutine behind (async context outside a
        # worker thread): close it instead of emitting a RuntimeWarning.
        if inspect.iscoroutine(result):
            result.close()
    except Exception:  # noqa: BLE001 - progress is advisory
        pass


# --------------------------------------------------------------------------- #
# Common result builders
# --------------------------------------------------------------------------- #
def nexus_artifact(entry: Dict[str, object]) -> Dict[str, object]:
    """Normalise a RunStorage.register() entry into a nexus_file descriptor."""
    return {
        "relative": entry["relative"],
        "absolute": entry["absolute"],
        "size_bytes": entry["size_bytes"],
    }


def tree_summary(styler: Any) -> Dict[str, object]:
    """Derive a compact summary from a configured styler (used by style/clade)."""
    content = styler.get_tree_content()
    tips: int = 0
    internals: int = 0
    rooted: Optional[bool] = None
    if content:
        tree = styler.parse_tree()
        if tree is not None:
            tips = len(tree.get_terminals())
            internals = len(tree.get_nonterminals()) if hasattr(tree, "get_nonterminals") else max(0, tips - 1)
            rooted = bool(getattr(tree, "rooted", None)) if getattr(tree, "rooted", None) is not None else None
    layout = styler.get_settings().get("layout.layoutType", "RECTILINEAR")
    return {
        "tips": tips,
        "internal_nodes": internals,
        "rooted": rooted,
        "layout": str(layout).lower(),
        "tree_count": getattr(styler, "_all_trees", None) and len(styler._all_trees) or 1,
    }


def export_nexus_file(
    styler: Any,
    run: RunStorage,
    base_name: str = "output.nex",
    *,
    include_taxa_block: bool = True,
) -> Dict[str, object]:
    """Export current styler state into the run dir (atomic write by figtreekit)."""
    if not base_name.endswith(".nex"):
        base_name += ".nex"
    safe = run.file_path(base_name)
    try:
        styler.export(str(safe), include_taxa_block=include_taxa_block)
    except Exception:
        # surface figtreekit ExportError under our envelope
        raise
    return nexus_artifact(run.register(safe))


# Re-export commonly used values for tool modules.
__all__ = ["TOOLS", "tool", "get_app", "require_run", "get_run_dir",
           "resolve_mapping_file", "progress", "nexus_artifact",
           "tree_summary", "export_nexus_file"]
