# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Environment tools: T01 get_environment, T02 check_figtree, T03 setup_figtree."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any, Dict, Optional

import figtreekit
from figtreekit import _figtree_setup
from mcp.server.fastmcp import Context

from .._errors import ToolError, ok_envelope
from . import get_app, progress, tool
from .._logging import get_logger

_log = get_logger()

_JAVA_MAJOR_RE = re.compile(r'"(\d+)"|version\s+"?1\.(\d+)|version\s+"?(\d+)')


def _java_version(raw: str) -> str:
    m = _JAVA_MAJOR_RE.search(raw)
    if not m:
        return raw.strip() or "unknown"
    major = m.group(1) or m.group(2) or m.group(3)
    return f"{int(major)}.x"


def probe_java() -> Dict[str, Any]:
    """Return ``{"ok", "version", "message", "hints"}`` for Java availability."""
    ok, raw = _figtree_setup.check_java()
    version = _java_version(raw) if ok else ""
    return {
        "ok": ok,
        "version": version,
        "message": raw.strip() if raw else "",
        "hints": (["Java 8+ 未安装或不在 PATH。请安装 JDK/JRE 8+（如 Adoptium）。"]
                  if not ok else []),
    }


def probe_jar(app: "Any", jar_path: Optional[str] = None) -> Dict[str, Any]:
    """Return ``{"ok", "path", "hints"}`` for figtree_patched.jar availability."""
    jar = jar_path or app.jar_path
    if jar and jar != "auto":
        try:
            p = app.workspace.assert_readable(jar)
        except ToolError as exc:
            # A server-configured --jar may live outside the read roots; do not
            # let a probe raise — surface a clean, actionable hint instead.
            return {
                "ok": False,
                "path": str(jar),
                "hints": [
                    f"JAR 路径不在允许读取的白名单内：{jar}。{exc.error}。"
                    "请将 JAR 放入允许的根目录，或调整 --allow-read-root。"
                ],
            }
        if not p.is_file():
            return {"ok": False, "path": str(p),
                    "hints": [f"JAR 不存在：{p}。可执行 setup_figtree 安装。"]}
        return {"ok": True, "path": str(p), "hints": []}
    found = figtreekit.find_figtree_jar()
    if found:
        return {"ok": True, "path": found, "hints": []}
    return {"ok": False, "path": None,
            "hints": ["figtree_patched.jar 未找到。运行 setup_figtree 下载/编译，"
                      "或通过 --jar / FIGTREE_JAR 指定。"]}


def render_ready(app: "Any", jar_path: Optional[str] = None) -> Dict[str, Any]:
    java = probe_java()
    jar = probe_jar(app, jar_path)
    ready = bool(java["ok"] and jar["ok"])
    return {"java": java, "jar": jar, "render_ready": ready}


@tool("get_environment")
def get_environment(ctx: Context) -> Dict[str, Any]:
    """Report the FigTreeKit-MCP runtime environment.

    Returns versions of figtreekit / biopython / python / the MCP SDK, Java
    and figtree_patched.jar availability, the workspace root, and the allowed
    read-only roots.
    """
    app = get_app(ctx)
    env = render_ready(app)
    return ok_envelope(
        figtreekit_version=app.figtreekit_version,
        biopython_version=app.biopython_version,
        python_version=app.python_version,
        mcp_sdk_version=app.mcp_version,
        pillow=({"ok": True, "version": app.pillow_version} if app.pillow_version
                else {"ok": False, "version": None}),
        java=env["java"],
        jar=env["jar"],
        workspace_root=app.workspace_root,
        allowed_read_roots=app.allowed_read_roots,
        render_ready=env["render_ready"],
    )


@tool("check_figtree")
def check_figtree(ctx: Context, jar_path: Optional[str] = None) -> Dict[str, Any]:
    """Check Java 8+ and the figtree_patched.jar; return actionable hints.

    Args:
        jar_path: Optional explicit JAR path to check instead of auto-detection.
    """
    app = get_app(ctx)
    java = probe_java()
    jar = probe_jar(app, jar_path)
    ready = bool(java["ok"] and jar["ok"])
    hints = java["hints"] + jar["hints"]
    if not ready:
        raise ToolError(
            "jar_missing" if java["ok"] else "java_missing",
            "渲染依赖不完整（Java 或 JAR 缺失）",
            error_key="render_deps_missing",
            error_detail="\n".join(hints),
            details=[{"level": "WARNING", "message": h} for h in hints],
        )
    return ok_envelope(
        java_ok=java["ok"],
        java_version=java["version"],
        jar_ok=jar["ok"],
        jar_path=jar["path"],
        render_ready=ready,
        hints=hints,
    )


@tool("setup_figtree")
def setup_figtree(
    ctx: Context,
    jar_path: Optional[str] = None,
    check_only: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Download (or use given jar) and compile the patched FigTree JAR.

    Args:
        jar_path: Optional existing JAR to use (whitelisted; no compile).
        check_only: Only check dependencies (no download/compile).
        verbose: Print step-by-step setup progress.
    """
    app = get_app(ctx)

    if check_only:
        java = probe_java()
        jar = probe_jar(app, jar_path)
        ready = bool(java["ok"] and jar["ok"])
        hints = java["hints"] + jar["hints"]
        return ok_envelope(
            java_ok=java["ok"],
            java_version=java["version"],
            jar_ok=jar["ok"],
            jar_path=jar["path"],
            render_ready=ready,
            hints=hints,
            status=hints,
        )

    if jar_path:
        resolved = app.workspace.assert_readable(jar_path)
        if not resolved.is_file():
            raise ToolError(
                "invalid_argument",
                f"jar_path 必须是文件：{resolved}",
                error_key="jar_not_a_file",
            )
        app.workspace.check_file_size(resolved)
        progress(ctx, 100, 100, "使用已有 FigTree JAR")
        return ok_envelope(
            jar_path=str(resolved),
            status=[f"使用已有 FigTree JAR：{resolved}"],
        )

    # A bundled / previously installed JAR needs no download or compile.
    auto = probe_jar(app)
    if auto["ok"] and auto["path"]:
        progress(ctx, 100, 100, "FigTree JAR 已可用")
        return ok_envelope(
            jar_path=auto["path"],
            status=[f"FigTree JAR 已可用（already available）：{auto['path']}"],
        )

    progress(ctx, 10, 100, "开始 FigTree JAR 检查/安装")
    timeout_s = max(1, int(app.setup_timeout or 600))

    # Run the printing installer in a child process: it writes to its own
    # stdout/stderr pipes, so it can never corrupt MCP protocol frames; the
    # child is killed on timeout instead of leaking a daemon thread that still
    # holds a global stdout redirect.
    worker_code = (
        "import json, sys\n"
        "from figtreekit import _figtree_setup\n"
        "try:\n"
        "    jar = _figtree_setup.setup_figtree(\n"
        "        install_dir=None, jar_path=None, verbose=sys.argv[1] == '1')\n"
        "    print('__FTK_RESULT__' + json.dumps({'ok': True,\n"
        "          'jar': str(jar) if jar else None}))\n"
        "except BaseException as exc:\n"
        "    print('__FTK_RESULT__' + json.dumps({\n"
        "          'ok': False, 'error': f'{type(exc).__name__}: {exc}'}))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", worker_code, "1" if verbose else "0"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            "figtree_setup_failed",
            f"FigTree 安装超时（>{timeout_s}s）",
            error_key="setup_timeout",
            error_detail="安装子进程已被终止。",
        ) from exc

    result: Dict[str, Any] = {}
    status_lines: list[str] = []
    for line in (proc.stdout or "").splitlines():
        if line.startswith("__FTK_RESULT__"):
            try:
                result = json.loads(line[len("__FTK_RESULT__"):])
            except json.JSONDecodeError:  # pragma: no cover - defensive
                result = {}
        elif line.strip():
            status_lines.append(line)
    if not result.get("ok"):
        detail = result.get("error") or (proc.stderr or "")[-2000:] or f"exit {proc.returncode}"
        raise ToolError(
            "figtree_setup_failed",
            f"FigTree 安装失败：{detail}",
            error_key="setup_failed",
            error_detail=str(detail),
        )

    installed = result.get("jar") or figtreekit.find_figtree_jar()
    if not installed:
        raise ToolError(
            "figtree_setup_failed",
            "FigTree 安装完成但未找到 JAR",
            error_key="setup_no_jar",
        )
    progress(ctx, 100, 100, "FigTree JAR 安装完成")
    if not status_lines:
        status_lines = [f"FigTree JAR 已安装：{installed}"]
    return ok_envelope(jar_path=str(installed), status=status_lines)


# Import side-effect: register handlers into the TOOLS registry
__all__ = ["get_environment", "check_figtree", "setup_figtree"]
