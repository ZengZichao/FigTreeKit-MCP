# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Render tool: T20 render_tree.

Renders a Nexus file (or tree content) via the patched FigTree JAR with the
``figtreekit`` kernel, applies background/foreground/label colour post
processing for raster formats, and returns a ``data_uri`` preview when the
result is ≤ 512 KiB (token economy).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import figtreekit
from mcp.server.fastmcp import Context

from .._core import resolve_tree_source
from .._errors import ToolError, ok_envelope
from .._logging import get_logger
from .. import cli_command
from . import get_app, progress, require_run, tool
from .environment import probe_jar, probe_java

_log = get_logger()

_RENDER_FORMATS = ("PNG", "PDF", "SVG", "JPEG")
_EXT = {"PNG": ".png", "PDF": ".pdf", "SVG": ".svg", "JPEG": ".jpg"}


@tool("render_tree")
def render_tree(
    ctx: Context,
    nexus_file: Optional[str] = None,
    tree_content: Optional[str] = None,
    format: Optional[str] = None,
    width: int = 1600,
    height: int = 1000,
    background_color: Optional[str] = None,
    foreground_color: Optional[str] = None,
    label_color: Optional[str] = None,
    jar_path: Optional[str] = None,
    timeout: Optional[int] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a Nexus file (or tree content) to PNG/PDF/SVG/JPEG via the
    patched FigTree JAR; returns paths plus an optional base64 data URI
    preview.  Applies background/foreground/label colour post-processing for
    raster formats.

    Args:
        nexus_file: Path to a Nexus file (whitelisted; takes precedence).
        tree_content: Newick/Nexus content rendered through a base export.
        format: PNG|PDF|SVG|JPEG (default PNG).
        width: Image width in pixels.
        height: Image height in pixels.
        background_color: #RRGGBB background (raster post-process).
        foreground_color: #RRGGBB foreground (raster post-process).
        label_color: #RRGGBB protected label colour.
        jar_path: Explicit figtree_patched.jar path (default: app config /
            auto-detection).
        timeout: Max seconds for the JVM render call (default:
            app.render_timeout, normally 180).
        run_name: Optional artifact base name.
    """
    app = get_app(ctx)
    run = require_run(ctx)
    fmt = (format or "PNG").upper()
    if fmt not in _RENDER_FORMATS:
        raise ToolError(
            "render_bad_format",
            f"format 必须是 {_RENDER_FORMATS} 之一，得到 '{fmt}'",
            error_key="bad_render_format",
        )
    if width <= 0 or height <= 0:
        raise ToolError("invalid_argument", "width/height 必须 > 0", error_key="bad_render_size")
    render_timeout = app.render_timeout if timeout is None else timeout
    if render_timeout <= 0:
        raise ToolError("invalid_argument", "timeout 必须 > 0", error_key="bad_render_timeout")

    # ----- dependency check (java → jar) ---------------------------------
    java = probe_java()
    if not java["ok"]:
        raise ToolError(
            "java_missing",
            "渲染需要 Java 8+，但当前环境未找到 java",
            error_key="java_missing",
            error_detail=java["message"],
            details=[{"level": "WARNING", "message": h} for h in java["hints"]],
        )
    jar = probe_jar(app, jar_path)
    if not jar["ok"]:
        raise ToolError(
            "jar_missing",
            "渲染需要 figtree_patched.jar，但未找到",
            error_key="jar_missing",
            error_detail="\n".join(jar["hints"]),
            details=[{"level": "WARNING", "message": h} for h in jar["hints"]],
        )
    jar_path = jar["path"]
    if jar_path is None:  # keep mypy happy
        raise ToolError("jar_missing", "figtree_patched.jar 未找到", error_key="jar_missing")

    # ----- input resolution ----------------------------------------------
    if nexus_file is not None:
        in_path = app.workspace.assert_readable(nexus_file)
        if not in_path.is_file():
            raise ToolError(
                "invalid_argument",
                f"nexus_file 必须是可读取的文件：{in_path}",
                error_key="nexus_not_a_file",
            )
        app.workspace.check_file_size(in_path)
        input_cli = str(in_path)
    elif tree_content is not None:
        content, _node = resolve_tree_source(tree_content, None, app.workspace)
        in_path = run.run_dir / "input.nex"
        in_path.write_text(content, encoding="utf-8")
        input_cli = str(in_path)
    else:
        raise ToolError(
            "invalid_argument",
            "render_tree 必须提供 nexus_file 或 tree_content 之一",
            error_key="missing_render_input",
        )

    out_path = run.file_path(f"{run_name or 'output'}{_EXT[fmt]}")
    progress(ctx, 10, 100, f"开始渲染 {fmt}（{width}×{height}）")

    ext_suffix = _EXT[fmt]
    try:
        figtreekit.render_with_figtree(
            str(in_path),
            str(out_path),
            format=fmt,
            width=width,
            height=height,
            jar_path=jar_path,
            timeout=render_timeout,
            background_color=background_color,
            foreground_color=foreground_color,
            label_color=label_color,
        )
    except figtreekit.RenderError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            raise ToolError(
                "render_timeout",
                f"渲染超时（>{render_timeout}s）",
                error_key="render_timeout",
                error_detail=msg,
            ) from exc
        raise ToolError(
            "render_failed",
            f"FigTree 渲染失败：{msg}",
            error_key="render_failed",
            error_detail=msg,
        ) from exc
    except FileNotFoundError as exc:
        # The input file was validated above, so a missing file here means the
        # JAR vanished between probe and render (or an unexpected IO error).
        msg = str(exc)
        if (
            "input" not in msg.lower()
            and "tree file" not in msg.lower()
            and not Path(jar_path).is_file()
        ):
            raise ToolError(
                "jar_missing", f"figtree_patched.jar 缺失：{exc}", error_key="jar_missing"
            ) from exc
        raise ToolError(
            "render_failed",
            f"渲染输入文件不可读：{exc}",
            error_key="render_failed",
            error_detail=msg,
        ) from exc

    artifact = run.register(out_path)
    progress(ctx, 100, 100, "渲染完成")

    # Reproducible command (view-only; MCP never executes strings).  render_tree
    # does not export a .nex, so ``-o`` is intentionally omitted; note that the
    # CLI cannot reproduce Python-side colour post-processing.
    cli_command_str = _build_render_command(
        input_cli, run.run_dir / "render.nex", out_path, fmt, width, height, jar_path
    )
    config_json = json.dumps(
        {
            "format": fmt,
            "width": width,
            "height": height,
            "colors": {
                "background_color": background_color,
                "foreground_color": foreground_color,
                "label_color": label_color,
            },
            "jar": jar_path,
        },
        indent=2,
        ensure_ascii=False,
    )
    post_processed = [c for c in (background_color, foreground_color, label_color) if c]
    warnings = []
    if post_processed:
        warnings.append(
            {
                "level": "WARNING",
                "message": "cli_command 无法复现 background/foreground/label 颜色的 "
                "Python 后处理，仅复现布局、尺寸与渲染格式。",
            }
        )

    return ok_envelope(
        image=artifact,
        cli_command=cli_command_str,
        config_json=config_json,
        reproducible=not post_processed,
        warnings=warnings,
        format=fmt,
        width=artifact.get("width", width) if artifact.get("width") else width,
        height=artifact.get("height", height) if artifact.get("height") else height,
        run_dir=run.name,
        ext=ext_suffix,
    )


def _build_render_command(
    input_path: str,
    nexus_out: Path,
    out_path: Path,
    fmt: str,
    width: int,
    height: int,
    jar_path: str,
) -> str:
    """Build the paste-able ``python -m figtreekit … --render`` command.

    The CLI requires ``-o`` even in render mode (it re-exports the Nexus before
    rendering), so the command writes a companion ``render.nex`` next to the
    image.  Colour post-processing done by Python is not representable.
    """
    parts = [
        cli_command.quote_arg("python"),
        "-m",
        "figtreekit",
        cli_command.quote_arg(input_path),
        "-o",
        cli_command.quote_arg(str(nexus_out)),
        "--force",
        "--render",
        cli_command.quote_arg(str(out_path)),
        "--render-format",
        fmt,
        "--render-width",
        str(width),
        "--render-height",
        str(height),
        "--figtree-jar",
        cli_command.quote_arg(jar_path),
    ]
    return " ".join(parts)


__all__ = ["render_tree"]
