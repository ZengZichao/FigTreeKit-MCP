# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Unified error envelope and exception mapping for FigTreeKit-MCP.

Every tool handler returns (or, on failure, returns) a JSON-serialisable dict
with the same shape:

.. code-block:: json

    {"ok": false,
     "code": "validation_failed",
     "error_key": "negative_branch_length",
     "error": "树包含负分支长度，FigTree 无法渲染",
     "error_detail": "tree 'TREENAME' at ...",
     "details": [{"level": "CRITICAL", "message": "..."}],
     "run_dir": "run_abc1234"}

The mapping between figtreekit's exception hierarchy and our stable error
codes lives in :data:`EXCEPTION_TO_CODE`.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

import figtreekit
from figtreekit import exceptions as fk_exc

# --------------------------------------------------------------------------- #
# Error codes
# --------------------------------------------------------------------------- #
ERROR_CODES = (
    "invalid_argument",
    "input_too_large",
    "access_denied",
    "anomalous_content",
    "tree_parse_error",
    "validation_failed",
    "taxonomy_conflict",
    "monophyly_error",
    "export_failed",
    "java_missing",
    "jar_missing",
    "figtree_setup_failed",
    "render_bad_format",
    "render_timeout",
    "render_failed",
    "cli_failed",
    "cli_timeout",
    "cancelled",
    "internal_error",
)


class ToolError(Exception):
    """Raised by handlers to produce a structured error envelope.

    Args:
        code: One of :data:`ERROR_CODES`.
        error: Human-readable Chinese message.
        error_key: Machine-readable key (defaults to ``code``).
        error_detail: Technical detail (traceable, English ok).
        details: Structured list of ``{"level","message"}`` entries.
    """

    def __init__(
        self,
        code: str,
        error: str,
        *,
        error_key: Optional[str] = None,
        error_detail: str = "",
        details: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        if code not in ERROR_CODES and code != "cancelled":
            code = "internal_error"
        self.code = code
        self.error_key = error_key or code
        self.error = error
        self.error_detail = error_detail
        self.details = details or []
        super().__init__(error)


# --------------------------------------------------------------------------- #
# figtreekit exception → stable code mapping
# --------------------------------------------------------------------------- #
EXCEPTION_TO_CODE: List[tuple] = [
    # order matters: most specific first
    (fk_exc.RenderError, "render_failed"),
    (fk_exc.ExportError, "export_failed"),
    (fk_exc.MonophylyError, "monophyly_error"),
    (fk_exc.TaxonomyConflictError, "taxonomy_conflict"),
    (fk_exc.PhyloFormatError, "tree_parse_error"),
    (fk_exc.ParseError, "tree_parse_error"),
    (fk_exc.ValidationError, "validation_failed"),
    (FileNotFoundError, "access_denied"),
    (PermissionError, "access_denied"),
    (ValueError, "invalid_argument"),
]


def _code_for_exc(exc: Exception) -> str:
    for exc_type, code in EXCEPTION_TO_CODE:
        if isinstance(exc, exc_type):
            return code
    return "internal_error"


# --------------------------------------------------------------------------- #
# Envelope builders
# --------------------------------------------------------------------------- #
def ok_envelope(**fields: Any) -> Dict[str, Any]:
    """Build an ``ok: true`` result dict."""
    result: Dict[str, Any] = {"ok": True}
    result.update(fields)
    return result


def error_envelope(
    *,
    code: str,
    error_key: Optional[str] = None,
    error: str,
    error_detail: str = "",
    details: Optional[List[Dict[str, str]]] = None,
    run_dir: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build an ``ok: false`` error envelope (stable shape)."""
    env: Dict[str, Any] = {
        "ok": False,
        "code": code,
        "error_key": error_key or code,
        "error": error,
        "error_detail": error_detail,
        "details": details or [],
    }
    if run_dir is not None:
        env["run_dir"] = run_dir
    env.update(extra)
    return env


def envelope_from_exception(exc: BaseException, *, run_dir: Optional[str] = None) -> Dict[str, Any]:
    """Convert any exception into a structured error envelope.

    figtreekit errors are mapped to stable codes; unexpected exceptions become
    ``internal_error`` with a short stack summary (never printed to stdout).
    """
    if isinstance(exc, ToolError):
        return error_envelope(
            code=exc.code,
            error_key=exc.error_key,
            error=exc.error,
            error_detail=exc.error_detail,
            details=exc.details,
            run_dir=run_dir,
        )

    if isinstance(exc, fk_exc.CompatibilityWarning):
        return error_envelope(
            code="validation_failed",
            error_key="compatibility_warning",
            error=str(exc),
            run_dir=run_dir,
        )

    code = _code_for_exc(exc)
    detail = str(exc)
    stack_summary = ""
    if code == "internal_error":
        stack_summary = "\n".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)[:20]
        )

    return error_envelope(
        code=code,
        error_key=code,
        error=_friendly_message(code, exc),
        error_detail=detail,
        details=[{"level": "CRITICAL", "message": str(exc).strip()}] if str(exc).strip() else [],
        run_dir=run_dir,
        **({"stack_summary": stack_summary} if stack_summary else {}),
    )


def _friendly_message(code: str, exc: BaseException) -> str:
    """Chinese human-readable message per stable code."""
    table = {
        "invalid_argument": f"参数校验失败：{exc}",
        "input_too_large": f"输入超过大小限额：{exc}",
        "access_denied": f"路径访问被拒绝（不在白名单内）：{exc}",
        "anomalous_content": f"输入包含异常内容（控制字符/双向文本）：{exc}",
        "tree_parse_error": f"树文件解析失败：{exc}",
        "validation_failed": f"验证失败：{exc}",
        "taxonomy_conflict": f"分类学数据冲突：{exc}",
        "monophyly_error": f"单系性分析错误：{exc}",
        "export_failed": f"Nexus 导出失败：{exc}",
        "java_missing": f"Java 不可用：{exc}",
        "jar_missing": f"figtree_patched.jar 缺失：{exc}",
        "figtree_setup_failed": f"FigTree 安装失败：{exc}",
        "render_bad_format": f"不支持的渲染格式：{exc}",
        "render_timeout": f"渲染超时：{exc}",
        "render_failed": f"渲染失败：{exc}",
        "cli_failed": f"透传命令执行失败：{exc}",
        "cli_timeout": f"透传命令超时：{exc}",
        "cancelled": "操作已被客户端取消",
        "internal_error": f"内部错误（{type(exc).__name__}）：{exc}",
    }
    return table.get(code, f"错误（{code}）：{exc}")


def collect_warnings(warnings_list) -> List[Dict[str, str]]:
    """Normalise figtreekit compatibility warnings into envelope ``details``."""
    messages = []
    for w in warnings_list:
        msg = getattr(w, "message", w)
        # warn() may be called with (message, category) or a Warning instance;
        # prefer the message text over the WarningMessage repr.
        if isinstance(msg, Warning):
            msg = str(msg)
        messages.append(str(msg))
    return [{"level": "WARNING", "message": m} for m in messages]


def guard(fn):
    """Decorator: wrap a handler so every exception becomes an error envelope.

    The envelope is *returned* (``ok: false``) rather than raised, so the MCP
    layer receives structured JSON and the process never crashes.
    """

    def wrapper(*args, **kwargs):
        run_dir: Optional[str] = None
        try:
            return fn(*args, **kwargs)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - everything → envelope
            return envelope_from_exception(exc, run_dir=run_dir)

    return wrapper
