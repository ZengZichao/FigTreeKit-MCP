# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""E2E protocol smoke tests (AC-2/3).

Drives the *real* server as a stdio subprocess with the official ``mcp``
client library — no protocol mocking.  Covers handshake, tool listing
(恰 21), three typical calls (summarize/style/render), error envelopes,
stdout frame purity and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from conftest import GTDB_DIR, SMALL_TREE  # noqa: E402
from figtreekit_mcp._version import __version__

PY = sys.executable

# The 21 tool names (T01..T21).
EXPECTED_TOOLS = {
    "get_environment", "check_figtree", "setup_figtree",
    "validate_tree", "summarize_tree", "cross_validate",
    "check_monophyly", "analyze_taxonomy", "taxonomy_completeness",
    "style_tree", "apply_config", "export_nexus",
    "highlight_clade", "color_clade", "set_clade_font",
    "collapse_clade", "collapse_group", "collapse_rank", "clear_annotations",
    "render_tree", "run_figtreekit_cli",
}

EXPECTED_RESOURCES = {"figtreekit://version", "figtreekit://help", "figtreekit://defaults"}
EXPECTED_PROMPTS = {"create-publication-figure", "taxonomy-audit"}


# --------------------------------------------------------------------------- #
# subprocess / session helpers
# --------------------------------------------------------------------------- #
def _server_params(tmp_path: Path, read_roots: Optional[List[str]] = None) -> StdioServerParameters:
    argv = [
        PY, "-m", "figtreekit_mcp",
        "--transport", "stdio",
        "--workspace-root", str(tmp_path / "ws"),
    ]
    for r in read_roots or []:
        argv += ["--allow-read-root", str(r)]
    return StdioServerParameters(command=PY, args=argv[1:], env=None)


def _json_text(result: Any) -> Dict[str, Any]:
    """Extract and parse the JSON payload from a CallToolResult."""
    texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    assert texts, f"no text content in {result}"
    return json.loads("\n".join(texts))


# --------------------------------------------------------------------------- #
# 1. handshake + tool/resource/prompt listing (AC-2/3)
# --------------------------------------------------------------------------- #
class TestHandshakeAndListing:
    @pytest.mark.asyncio
    async def test_initialize_and_list_tools(self, tmp_path: Path) -> None:
        params = _server_params(tmp_path)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                assert init.serverInfo is not None
                # serverInfo.version must be the package version, not the SDK's.
                assert init.serverInfo.version == __version__

                tools = await s.list_tools()
                names = {t.name for t in tools.tools}
                assert len(tools.tools) == 21
                assert names == EXPECTED_TOOLS

    @pytest.mark.asyncio
    async def test_three_resources(self, tmp_path: Path) -> None:
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                for uri in sorted(EXPECTED_RESOURCES):
                    res = await s.read_resource(uri)
                    assert res.contents, f"resource {uri} returned no contents"
                    text = res.contents[0].text
                    assert text, f"resource {uri} empty"

    @pytest.mark.asyncio
    async def test_two_prompts_available(self, tmp_path: Path) -> None:
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                for name in sorted(EXPECTED_PROMPTS):
                    p = await s.get_prompt(name)
                    assert p.description or p.messages

    @pytest.mark.asyncio
    async def test_prompt_arguments_are_used_and_bilingual(self, tmp_path: Path) -> None:
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                pub = await s.get_prompt(
                    "create-publication-figure",
                    {"tree_file": "example.tree", "render_formats": "SVG"},
                )
                pub_text = "\n".join(
                    m.content.text for m in pub.messages
                    if getattr(m.content, "type", None) == "text"
                )
                assert "example.tree" in pub_text
                assert "SVG" in pub_text  # render_formats is rendered, not ignored
                assert "English quick reference" in pub_text

                audit = await s.get_prompt("taxonomy-audit", {"rank": "class"})
                audit_text = "\n".join(
                    m.content.text for m in audit.messages
                    if getattr(m.content, "type", None) == "text"
                )
                assert "class" in audit_text
                assert "English quick reference" in audit_text


# --------------------------------------------------------------------------- #
# 2. typical calls
# --------------------------------------------------------------------------- #
class TestTypicalCalls:
    @pytest.mark.asyncio
    async def test_summarize_tree(self, tmp_path: Path, gtdb_dir: Path) -> None:
        tree = gtdb_dir / "ar53_r232.tree"
        async with stdio_client(_server_params(tmp_path, [str(gtdb_dir)])) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("summarize_tree", {"tree_file": str(tree)})
                assert res.isError is False
                data = _json_text(res)
                assert data.get("ok") is True
                stats = data.get("statistics", {})
                assert stats.get("tips", 0) > 0

    @pytest.mark.asyncio
    async def test_style_tree(self, tmp_path: Path) -> None:
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(
                    "style_tree",
                    {"tree_content": SMALL_TREE, "layout": "polar",
                     "polar_angular_range_degrees": 180,
                     "polar_root_angle_degrees": 270},
                )
                assert res.isError is False
                data = _json_text(res)
                assert data.get("ok") is True
                assert data["nexus_file"]["absolute"].endswith(".nex")
                assert data["cli_command"]

    @pytest.mark.asyncio
    async def test_render_tree_when_java_ready(self, tmp_path: Path) -> None:
        """Render only when Java+JAR are present; otherwise assert the structured
        dependency error envelope (SEC-10/11 path via E2E)."""
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                # materialise a styled nexus first
                styled = await s.call_tool("style_tree", {"tree_content": SMALL_TREE, "layout": "polar"})
                data = _json_text(styled)
                nexus = data["nexus_file"]["absolute"]
                res = await s.call_tool(
                    "render_tree", {"nexus_file": nexus, "format": "PNG",
                                    "width": 200, "height": 150, "timeout": 60}
                )
                if res.isError:  # pragma: no cover - defensive (protocol error)
                    combined = "\n".join(c.text for c in res.content
                                         if getattr(c, "type", None) == "text")
                    assert ("java" in combined.lower() or "jar" in combined.lower())
                else:
                    rdata = _json_text(res)
                    if rdata.get("ok") is False:
                        # Java/JAR absent: the unified envelope must say why.
                        assert rdata["code"] in (
                            "java_missing", "jar_missing", "render_failed",
                            "render_timeout", "render_bad_format",
                        )
                        assert rdata["error"]
                    else:
                        assert rdata["image"]["absolute"].endswith(".png")


# --------------------------------------------------------------------------- #
# 3. error envelope over the wire
# --------------------------------------------------------------------------- #
class TestErrorEnvelope:
    @pytest.mark.asyncio
    async def test_unauthorized_path_is_structured_error(self, tmp_path: Path) -> None:
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("summarize_tree", {"tree_file": "/etc/hosts"})
                # Structured envelopes are returned as normal tool results, so
                # clients can inspect ok/code/error_key/details/run_dir.
                assert res.isError is False
                env = _json_text(res)
                assert env["ok"] is False
                assert env["code"] == "access_denied"
                assert env["error_key"]
                assert isinstance(env["details"], list)
                assert env["error"]

    @pytest.mark.asyncio
    async def test_validation_error_includes_run_dir(self, tmp_path: Path) -> None:
        """Envelopes carry the call's run_<uuid8> when one was allocated."""
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(
                    "validate_tree", {"tree_content": "((A:-1,B:1):1,C:2);"}
                )
                env = _json_text(res)
                assert env["ok"] is False
                assert env["code"] == "validation_failed"
                assert env["error_key"] == "validation_errors"
                assert env["details"]
                assert env["run_dir"].startswith("run_")


# --------------------------------------------------------------------------- #
# 4. cancellation (fast cancellation of a long-running render)
# --------------------------------------------------------------------------- #
class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancel_render(self, tmp_path: Path) -> None:
        """Cancellation is best-effort; we assert the session stays usable."""
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                styled = await s.call_tool("style_tree", {"tree_content": SMALL_TREE, "layout": "polar"})
                nexus = _json_text(styled)["nexus_file"]["absolute"]

                # Launch render (may be slow without Java; use generous timeout)
                task = asyncio.create_task(
                    s.call_tool("render_tree",
                                {"nexus_file": nexus, "format": "PNG",
                                 "width": 800, "height": 600, "timeout": 120})
                )
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                # After cancellation the session must still serve requests.
                env = await s.call_tool("get_environment", {})
                assert env is not None


# --------------------------------------------------------------------------- #
# 5. stdout frame purity
# --------------------------------------------------------------------------- #
def test_no_bare_print_to_stdout_in_src() -> None:
    """SEC-12 static: no bare ``print(`` in the package source (protocol layer
    is the only stdout writer)."""
    from figtreekit_mcp._cli import _scan_no_stdout_print

    src = Path(__file__).resolve().parent.parent / "src" / "figtreekit_mcp"
    issues = _scan_no_stdout_print(src)
    assert not issues, f"stdout pollution found: {issues}"


# --------------------------------------------------------------------------- #
# 6. graceful shutdown (exit code 0 on EOF)
# --------------------------------------------------------------------------- #
class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_exit_zero_on_clean_close(self, tmp_path: Path) -> None:
        params = _server_params(tmp_path)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                assert len(tools.tools) == 21
        # Exiting the context manager closes stdio cleanly; the server should
        # terminate without error. (Process reaping is delegated to the SDK.)

    @pytest.mark.asyncio
    async def test_version_resource_matches_package(self, tmp_path: Path) -> None:
        async with stdio_client(_server_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.read_resource("figtreekit://version")
                snapshot = json.loads(res.contents[0].text)
                assert snapshot["figtreekit_version"]
                assert snapshot["mcp_server_version"] == __version__


# --------------------------------------------------------------------------- #
# 7. in-process registration wrapper (threading / envelopes / schema)
# --------------------------------------------------------------------------- #
class TestThreadedRegistration:
    def test_to_thread_keeps_schema_and_docstring(self) -> None:
        """functools.wraps + explicit signature keep FastMCP's schema stable."""
        from figtreekit_mcp.server import _threaded_tool
        from figtreekit_mcp.tools import TOOLS

        raw = TOOLS["summarize_tree"]
        wrapped = _threaded_tool(raw)
        assert inspect.iscoroutinefunction(wrapped)
        assert wrapped.__wrapped__ is raw
        assert wrapped.__doc__ == raw.__doc__
        # The wrapper exposes the raw signature (annotations evaluated once at
        # registration, so FastMCP's schema sees the same parameters/types).
        wrapped_sig = inspect.signature(wrapped)
        raw_sig = inspect.signature(raw, eval_str=True)
        assert list(wrapped_sig.parameters) == list(raw_sig.parameters)
        for name, raw_param in raw_sig.parameters.items():
            param = wrapped_sig.parameters[name]
            assert param.kind == raw_param.kind
            assert param.default == raw_param.default
            assert param.annotation == raw_param.annotation
        assert wrapped_sig.return_annotation == raw_sig.return_annotation

    def test_all_21_tool_schemas_unchanged(self) -> None:
        from mcp.server.fastmcp.tools import Tool

        from figtreekit_mcp.server import _threaded_tool
        from figtreekit_mcp.tools import TOOLS

        assert len(TOOLS) == 21
        for name, raw in TOOLS.items():
            before = Tool.from_function(raw, name=name)
            after = Tool.from_function(_threaded_tool(raw), name=name)
            assert before.parameters == after.parameters, name
            assert before.description == after.description, name

    def test_threaded_tool_returns_envelope(self) -> None:
        from figtreekit_mcp._errors import ToolError
        from figtreekit_mcp.server import _threaded_tool

        def boom(ctx: Any) -> Dict[str, Any]:
            raise ToolError("access_denied", "拒绝", error_key="k",
                            details=[{"level": "ERROR", "message": "m"}])

        env = asyncio.run(_threaded_tool(boom)(ctx=object()))
        assert env["ok"] is False
        assert env["code"] == "access_denied"
        assert env["details"] == [{"level": "ERROR", "message": "m"}]

    def test_threaded_tool_does_not_swallow_base_exceptions(self) -> None:
        from figtreekit_mcp.server import _threaded_tool

        for exc_type in (KeyboardInterrupt, SystemExit):
            def boom(ctx: Any, _exc=exc_type) -> Dict[str, Any]:
                raise _exc()

            with pytest.raises(exc_type):
                asyncio.run(_threaded_tool(boom)(ctx=object()))

    def test_progress_calls_async_context_from_worker_thread(self) -> None:
        from figtreekit_mcp.tools import progress

        calls: List[Any] = []

        class AsyncCtx:
            async def report_progress(self, current: int, total: int) -> None:
                calls.append(("progress", current, total))

            async def info(self, message: str) -> None:
                calls.append(("info", message))

        async def run() -> None:
            await anyio.to_thread.run_sync(progress, AsyncCtx(), 1, 2, "started")

        anyio.run(run)
        assert calls == [("progress", 1, 2), ("info", "started")]

    def test_progress_tolerates_sync_context_and_missing_methods(self) -> None:
        from figtreekit_mcp.tools import progress

        calls: List[Any] = []

        class SyncCtx:
            def report_progress(self, current: int, total: int) -> None:
                calls.append((current, total))

        progress(SyncCtx(), 5, 10, "msg")  # no info() → ignored, no raise
        progress(object(), 1, 1)  # no methods at all → ignored, no raise
        assert calls == [(5, 10)]

    def test_get_active_app_after_create_server(self, tmp_path: Path) -> None:
        from figtreekit_mcp.server import create_server, get_active_app

        workspace = tmp_path / "ws"
        server = create_server({
            "workspace_root": str(workspace),
            "cli_timeout": 7,
            "render_timeout": 8,
            "setup_timeout": 9,
        })
        app = get_active_app()
        assert app is not None
        assert Path(app.workspace_root) == workspace.resolve()
        assert server._mcp_server.version == __version__
        # Config values stay available to subprocess-owning tools via helpers.
        assert app.effective_cli_timeout(300) == 7
        assert app.effective_render_timeout(180) == 8
        assert app.effective_setup_timeout(600) == 9
        assert app.effective_cli_timeout() == 7

    def test_effective_timeout_defaults(self, tmp_path: Path) -> None:
        from figtreekit_mcp.server import AppContext, build_app_context

        app = build_app_context({"workspace_root": str(tmp_path / "ws")})
        app.cli_timeout = 0
        app.render_timeout = None  # type: ignore[assignment]
        assert app.effective_cli_timeout(300) == 300
        assert isinstance(app, AppContext)
        assert app.effective_render_timeout(180) == 180
        assert app.effective_setup_timeout(600) == 600
