# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""MCP resources: ``figtreekit://version``, ``figtreekit://help``,
``figtreekit://defaults``."""

from __future__ import annotations

import json
from typing import Any, Dict

import figtreekit
from figtreekit import _cli as fk_cli
from figtreekit.styler import _get_figtree_defaults
from mcp.server.fastmcp import FastMCP

from ._logging import get_logger
from ._version import __version__
from .server import get_active_app

_log = get_logger()


def _version_snapshot() -> Dict[str, Any]:
    app = get_active_app()
    if app is None:
        return {
            "figtreekit_version": figtreekit.__version__,
            "mcp_server_version": __version__,
            "server_warning": "AppContext 尚未初始化 / AppContext is not initialised",
        }
    java_ok = jar_ok = False
    java_version = ""
    jar_path = None
    try:  # best-effort probe; never fail a resource read
        from .tools.environment import probe_java, probe_jar

        j = probe_java()
        java_ok, java_version = bool(j["ok"]), j["version"]
        jr = probe_jar(app)
        jar_ok, jar_path = bool(jr["ok"]), jr["path"]
    except Exception as exc:  # noqa: BLE001
        _log.debug("version resource probe failed: %s", exc)
    return {
        "figtreekit_version": app.figtreekit_version,
        "mcp_server_version": __version__,
        "biopython_version": app.biopython_version,
        "python_version": app.python_version,
        "mcp_sdk_version": app.mcp_version,
        "pillow": app.pillow_version,
        "java": {"ok": java_ok, "version": java_version},
        "jar": {"ok": jar_ok, "path": jar_path},
        "render_ready": java_ok and jar_ok,
        "workspace_root": app.workspace_root,
        "allowed_read_roots": app.allowed_read_roots,
    }


def _help_text() -> str:
    try:
        parser = fk_cli.create_cli_parser()
        help_out = parser.format_help()
    except Exception as exc:  # pragma: no cover - defensive
        help_out = f"(figtreekit --help 不可用 / unavailable：{exc})"
    return (
        "# figtreekit CLI 帮助（figtreekit_mcp 透传的目标命令）\n"
        "# figtreekit CLI help (target of the figtreekit_mcp passthrough)\n\n"
        "> 等价性约定：MCP 工具的 ``cli_command`` 输出可直接粘贴到 zsh 复现；\n"
        "> 工具参考文档（docs/tools_reference_CN.md）给出了 MCP 参数 ↔ CLI 参数 ↔ figtree block 键 的映射表。\n"
        "> Reproducibility: every ``cli_command`` returned by a tool can be pasted\n"
        "> into a shell and reproduces the same FigTree configuration.\n\n"
        "```text\n" + help_out + "\n```"
    )


def _defaults_json() -> str:
    try:
        defaults = _get_figtree_defaults()
        return json.dumps(defaults, indent=2, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensive
        return json.dumps({"error": str(exc)})


def register(mcp: FastMCP) -> None:
    """Register the three resources on the server."""

    @mcp.resource("figtreekit://version")
    def _version_resource() -> str:
        """运行时版本 / JAR / Java 状态快照（JSON）。Runtime environment snapshot (JSON)."""
        return json.dumps(_version_snapshot(), indent=2, ensure_ascii=False)

    @mcp.resource("figtreekit://help")
    def _help_resource() -> str:
        """figtreekit CLI 全量帮助 + MCP↔CLI 对照提示（文本）。Full CLI help (text)."""
        return _help_text()

    @mcp.resource("figtreekit://defaults")
    def _defaults_resource() -> str:
        """FigTree 默认配置参数（figtree block 键，JSON）。FigTree defaults (JSON)."""
        return _defaults_json()


__all__ = ["register"]
