# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""FastMCP assembly: AppContext, server factory, 21-tool registration.

The lifespan captures an environment snapshot (versions / Java / JAR /
workspace) that tools read through ``tools.get_app(ctx)``; resources and
prompts are registered here too.

Registered tools are thin async wrappers around the synchronous handlers in
:data:`figtreekit_mcp.tools.TOOLS`.  FastMCP executes sync handlers *inline in
the event loop*, which blocks the protocol for the whole call; the wrappers
instead run the raw handler in an AnyIO worker thread and convert failures
into the unified error envelope (see :func:`_threaded_tool`).
"""

from __future__ import annotations

import functools
import inspect
import sys
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, get_type_hints

# Eager preload of the heavy optional import BEFORE ``FastMCP.run`` starts the
# event loop.  ``figtreekit.load_content`` imports ``Bio.Phylo`` (which pulls
# in numpy) lazily on the first styler call; importing numpy from inside a
# running asyncio loop deadlocks on Windows — confirmed: the first
# ``summarize_tree`` call never returns, while pre-importing here makes it
# return immediately.  Importing at module import time keeps tool calls
# deterministic and fast.
from Bio import Phylo  # noqa: F401  (event-loop import-deadlock workaround)

import anyio
import figtreekit
from mcp.server.fastmcp import FastMCP

from . import _concurrency
from ._errors import envelope_from_exception
from ._logging import get_logger
from ._version import __version__
from ._workspace import Workspace
from .tools import TOOLS, get_run_dir

_log = get_logger()

_INSTRUCTIONS = (
    "FigTreeKit-MCP exposes the FigTreeKit phylogenetic-tree workflow to AI "
    "assistants: validate (T04-T06), analyze (T07-T09), style (T10-T12), "
    "clade operations (T13-T19), render (T20) and full CLI passthrough "
    "(T21).\n\n"
    "Every styling/export/render call returns an equivalent ``cli_command`` "
    "and ``config_json`` so results are reproducible byte-for-byte.  Tree "
    "content may be passed directly (``tree_content``); file paths must be "
    "inside the whitelisted roots (see get_environment).  Multi-tree Nexus "
    "files require an explicit ``multi_tree`` / ``tree_index`` selection."
)


@dataclass
class AppContext:
    """Lifespan environment snapshot shared by all tool handlers."""

    workspace: Workspace
    jar_path: Optional[str]
    figtreekit_version: str
    biopython_version: str
    python_version: str
    mcp_version: str
    pillow_version: Optional[str]
    workspace_root: str
    allowed_read_roots: List[str]
    cli_timeout: int
    render_timeout: int
    setup_timeout: int = 600
    extra: Dict[str, Any] = field(default_factory=dict)

    def effective_cli_timeout(self, default: int = 300) -> int:
        """CLI pass-through timeout, falling back to *default* when unset."""
        return _positive_or(self.cli_timeout, default)

    def effective_render_timeout(self, default: int = 180) -> int:
        """JVM render timeout, falling back to *default* when unset."""
        return _positive_or(self.render_timeout, default)

    def effective_setup_timeout(self, default: int = 600) -> int:
        """FigTree JAR setup timeout, falling back to *default* when unset."""
        return _positive_or(self.setup_timeout, default)


def _positive_or(value: Optional[int], default: int) -> int:
    """Return *value* when it is a positive int, else *default*."""
    try:
        if value is not None and int(value) > 0:
            return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        pass
    return int(default)


# Single active server per process (documented limitation): tools/resources
# look the context up through ``get_active_app``.  The lock keeps concurrent
# ``create_server`` / ``get_active_app`` calls from observing a half-written
# entry; multiple live servers in one process are not supported.
_APP_LOCK = threading.Lock()
_APP_HOLDER: Dict[str, Optional[AppContext]] = {"app": None}


def get_active_app() -> Optional[AppContext]:
    """Return the currently configured AppContext (used by resources/tests)."""
    with _APP_LOCK:
        return _APP_HOLDER.get("app")


def _set_active_app(app: AppContext) -> None:
    """Atomically publish *app* as the process-wide active context."""
    with _APP_LOCK:
        _APP_HOLDER["app"] = app


def build_app_context(config: Dict[str, Any]) -> AppContext:
    """Construct the AppContext from a CLI/API config dict."""
    from importlib.metadata import version as _pkg_version

    workspace = Workspace(
        config["workspace_root"],
        config.get("read_roots") or [],
        keep_runs=config.get("keep_runs", 50),
        content_max_bytes=config.get("content_max_bytes", 10 * 1024 * 1024),
        file_max_bytes=config.get("file_max_bytes", 200 * 1024 * 1024),
    )

    def _ver(pkg: str) -> str:
        try:
            return _pkg_version(pkg)
        except Exception:  # pragma: no cover - best-effort
            return "unknown"

    pillow_version: Optional[str] = None
    try:
        pillow_version = _ver("pillow")
    except Exception:  # pragma: no cover
        pillow_version = None

    return AppContext(
        workspace=workspace,
        jar_path=config.get("jar"),
        figtreekit_version=figtreekit.__version__,
        biopython_version=_ver("biopython"),
        python_version=sys.version.split()[0],
        mcp_version=_ver("mcp"),
        pillow_version=pillow_version,
        workspace_root=str(workspace.root),
        allowed_read_roots=workspace.allowed_read_roots,
        cli_timeout=config.get("cli_timeout", 300),
        render_timeout=config.get("render_timeout", 180),
        setup_timeout=config.get("setup_timeout", 600),
    )


def _threaded_tool(
    fn: Callable[..., Dict[str, Any]],
) -> Callable[..., Awaitable[Dict[str, Any]]]:
    """Wrap a synchronous handler so FastMCP runs it off the event loop.

    The raw handler stays untouched in :data:`TOOLS` (tests call it directly);
    only the registration path is wrapped.  ``abandon_on_cancel=True`` lets a
    client cancellation return immediately instead of waiting for the worker.

    Exceptions become the unified error envelope.  ``BaseException``
    (``KeyboardInterrupt`` / ``SystemExit`` / cancellation) is deliberately not
    caught so shutdown and cancellation keep working.
    """

    @functools.wraps(fn)
    async def _async_tool(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        ctx = args[0] if args else kwargs.get("ctx")

        def _invoke() -> Dict[str, Any]:
            # figtreekit stores taxonomy rank prefixes and warning filters in
            # process-global state, and Java/CLI child processes are not safe
            # to run concurrently either.  The single RLock keeps concurrent
            # tool calls deterministic while the event loop stays responsive.
            with _concurrency.serialized():
                return fn(*args, **kwargs)

        try:
            return await anyio.to_thread.run_sync(_invoke, abandon_on_cancel=True)
        except Exception as exc:  # noqa: BLE001 - handlers raise ToolError
            return envelope_from_exception(exc, run_dir=get_run_dir(ctx))

    # FastMCP derives the tool schema/docstring from the wrapper.  Copy the
    # *evaluated* signature and hints, otherwise string annotations from
    # ``from __future__ import annotations`` in the tool modules would be
    # resolved against server.py's globals (missing names such as ``Union``).
    try:
        _async_tool.__signature__ = inspect.signature(fn, eval_str=True)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive (FastMCP resolves too)
        _async_tool.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
    try:
        _async_tool.__annotations__ = dict(get_type_hints(fn))
    except Exception:  # pragma: no cover - derive hints from the signature
        sig = _async_tool.__signature__  # type: ignore[attr-defined]
        _async_tool.__annotations__ = {
            name: param.annotation
            for name, param in sig.parameters.items()
            if param.annotation is not inspect.Parameter.empty
        }
        if sig.return_annotation is not inspect.Signature.empty:
            _async_tool.__annotations__["return"] = sig.return_annotation
    return _async_tool


def _register_tools(mcp: FastMCP) -> None:
    """Import every tool module (side-effect registration) and wire TOOLS."""
    import figtreekit_mcp.tools.environment  # noqa: F401  (registers T01-T03)
    import figtreekit_mcp.tools.validate  # noqa: F401  (T04-T06)
    import figtreekit_mcp.tools.analyze  # noqa: F401  (T07-T09)
    import figtreekit_mcp.tools.style  # noqa: F401  (T10-T12)
    import figtreekit_mcp.tools.clade  # noqa: F401  (T13-T19)
    import figtreekit_mcp.tools.render  # noqa: F401  (T20)
    import figtreekit_mcp.tools.passthrough  # noqa: F401  (T21)

    for name in sorted(TOOLS):
        mcp.tool(name=name)(_threaded_tool(TOOLS[name]))
        _log.debug("registered tool: %s", name)


@asynccontextmanager
async def _lifespan(server: FastMCP):
    app = get_active_app()
    yield app
    if app is not None:
        try:
            app.workspace.cleanup()
        except Exception:  # pragma: no cover - best-effort shutdown sweep
            _log.warning("workspace cleanup failed on shutdown")


def create_server(
    config: Optional[Dict[str, Any]] = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8777,
) -> FastMCP:
    """Create the fully-wired FastMCP server (tools + resources + prompts).

    Args:
        config: Keys: ``workspace_root``, ``read_roots``, ``jar``,
            ``content_max_bytes``, ``file_max_bytes``, ``cli_timeout``,
            ``render_timeout``, ``setup_timeout``, ``keep_runs``.
        host: Bind host (loopback by default) for sse/streamable-http.
        port: Bind port for sse/streamable-http.
    """
    cfg: Dict[str, Any] = config or {}
    if "workspace_root" not in cfg:
        from pathlib import Path

        cfg["workspace_root"] = str(
            Path.cwd() / "figtreekit-mcp-workspace"
        )
    _set_active_app(build_app_context(cfg))

    mcp = FastMCP(
        "figtreekit-mcp",
        instructions=_INSTRUCTIONS,
        lifespan=_lifespan,
        host=host,
        port=port,
    )
    # FastMCP 1.30 does not forward a version to the low-level server, whose
    # ``create_initialization_options`` then reports the MCP SDK version
    # (1.30.0).  Set the package version explicitly so ``initialize()`` returns
    # ``serverInfo.version == 0.1.0``.
    _mcp_server = getattr(mcp, "_mcp_server", None)
    if _mcp_server is not None and hasattr(_mcp_server, "version"):
        _mcp_server.version = __version__
    _register_tools(mcp)

    from . import prompts as _prompts
    from . import resources as _resources

    _resources.register(mcp)
    _prompts.register(mcp)
    return mcp
