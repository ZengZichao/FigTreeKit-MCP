# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Passthrough tool: T21 run_figtreekit_cli.

Escape hatch guaranteeing full ``figtreekit`` CLI coverage.  argv is passed as
an array to ``subprocess.run`` with ``shell=False`` (zero shell);
output paths are forcibly rewritten into the call's ``run_<uuid>`` directory
and every rewrite is disclosed in the ``rewrites`` field (SEC-4).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .._errors import ToolError, ok_envelope
from .._logging import get_logger
from .._workspace import RunStorage
from . import get_app, require_run, tool

_log = get_logger()

_MAX_ARGV = 256
_MAX_ARG_LEN = 4096
_MAX_TAIL = 65536
_INPUT_FILE_FLAGS = ("--config", "--taxonomy-mapping-file", "--sequences")
# Output flags plus the unambiguous argparse abbreviations of `--output` and
# `--log-file` (argparse accepts `--outp`, `--log`, ...).
_OUTPUT_FLAGS = (
    "-o",
    "--output",
    "--outp",
    "--outpu",
    "--out",
    "--render",
    "--log-file",
    "--log-fil",
    "--log-fi",
    "--log-f",
    "--log-",
    "--log",
)
# Every flag from figtreekit/_cli.py that consumes a value; used to skip
# flag values when looking for positional input tokens.
_VALUE_FLAGS = frozenset(
    {
        "-o",
        "--output",
        "--outp",
        "--outpu",
        "--out",
        "--config",
        "--multi-tree",
        "--seed",
        "--taxonomy-levels",
        "--taxonomy-delimiter-mode",
        "--taxonomy-table-sep",
        "--taxonomy-source-priority",
        "--taxonomy-mapping-file",
        "--table-sep",
        "--mol-type",
        "--sequences",
        "--log-file",
        "--log-fil",
        "--log-fi",
        "--log-f",
        "--log-",
        "--log",
        "--figtree-jar",
        "--render",
        "--render-format",
        "--render-width",
        "--render-height",
        "--branch-width",
        "--branch-color-attribute",
        "--background-color",
        "--foreground-color",
        "--selection-color",
        "--layout",
        "--expansion",
        "--zoom",
        "--rooting-type",
        "--transform",
        "--order",
        "--clade",
        "--collapse-taxa",
        "--collapse-rank",
        "--collapse-style",
        "--auto-color",
        "--highlight",
        "--color-clade",
        "--font-clade",
        "--analyze-taxonomy",
        "--check-monophyly",
        "--set",
        "--font-name",
        "--font-size",
        "--font-style",
        "--label-color",
        "--node-display-attribute",
        "--branch-display-attribute",
        "--root-age",
        "--scale-factor",
        "--angular-range",
        "--root-angle",
        "--radial-spread",
        "--curvature",
        "--root-length",
        "--legend-position",
    }
)


def _validate_argv(argv: Any) -> List[str]:
    if not isinstance(argv, list) or not argv:
        raise ToolError(
            "invalid_argument",
            "argv 必须是至少一个元素的字符串数组",
            error_key="empty_argv",
        )
    if len(argv) > _MAX_ARGV:
        raise ToolError(
            "invalid_argument",
            f"argv 长度 {len(argv)} 超过限制 {_MAX_ARGV}",
            error_key="argv_too_long",
        )
    if argv[0] in ("figtreekit", "python", "python3", "-m"):
        raise ToolError(
            "invalid_argument",
            f"argv[0] '{argv[0]}' 与内置执行器冲突；argv 应仅为 figtreekit 的参数",
            error_key="argv0_conflict",
        )
    for a in argv:
        if not isinstance(a, str):
            raise ToolError("invalid_argument", "argv 元素必须是字符串", error_key="bad_argv_type")
        if len(a) > _MAX_ARG_LEN:
            raise ToolError(
                "invalid_argument",
                f"argv 单个元素长度 {len(a)} 超过限制 {_MAX_ARG_LEN}",
                error_key="argv_elem_too_long",
            )
    return list(argv)


def _rewrite_output_args(argv: List[str], run_dir: Path) -> List[str]:
    """Rewrite ``-o/--output/--render/--log-file`` targets into run_dir."""
    run_dir = run_dir.resolve()
    result: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        matched = False
        for flag in _OUTPUT_FLAGS:
            if a == flag and i + 1 < len(argv):
                target = argv[i + 1]
                new_target = _force_into_run(target, run_dir)
                result += [flag, new_target]
                i += 2
                matched = True
                break
            if a.startswith(flag + "="):
                target = a[len(flag) + 1 :]
                result.append(f"{flag}={_force_into_run(target, run_dir)}")
                i += 1
                matched = True
                break
            if a.startswith("-o") and len(a) > 2 and not a.startswith("--"):
                # -oOUTPUT attached form
                result.append(f"-o{_force_into_run(a[2:], run_dir)}")
                i += 1
                matched = True
                break
        if not matched:
            result.append(a)
            i += 1
    return result


def _force_into_run(target: str, run_dir: Path) -> str:
    """Converge an output target under run_dir; return the rewritten value."""
    if not target or not target.strip() or target.strip() == "-":
        return target
    run_dir = run_dir.resolve()
    # ``Path.name`` handles POSIX and Windows separators; use only the
    # basename so neither ``..`` nor a drive/absolute prefix can escape.
    name = Path(target).name
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ToolError(
            "invalid_argument",
            f"输出目标文件名不合法：'{target}'",
            error_key="bad_output_target",
        )
    resolved = (run_dir / name).resolve()
    if not resolved.is_relative_to(run_dir):
        raise ToolError(
            "access_denied",
            "输出目标解析后逃逸出运行目录，已拒绝",
            error_key="output_escape",
            error_detail=f"{target} → {resolved}",
        )
    return str(resolved)


def _verify_inputs(argv: List[str], app: Any, run: Optional[RunStorage] = None) -> None:
    """Whitelist-check referenced input files inside argv (SEC access model).

    A value-aware scan skips the value of every known flag, so only genuine
    input files / positional tokens are checked.  Relative paths resolve
    against the execution cwd (``run.run_dir``), not the server cwd.
    """
    base_dir = run.run_dir if run is not None else app.workspace.root
    i = 0
    positionals: List[str] = []
    while i < len(argv):
        a = argv[i]
        if a == "--figtree-jar" or a.startswith("--figtree-jar="):
            raise ToolError(
                "invalid_argument",
                "--figtree-jar 不允许通过透传指定（任意 JAR 执行会绕过安全模型）；"
                "请使用 render_tree 的 jar_path 或服务端配置。",
                error_key="figtree_jar_forbidden",
            )
        if a.startswith("-") and a != "-":
            flag, sep, inline = a.partition("=")
            if sep:
                if flag in _INPUT_FILE_FLAGS and inline != "<input>":
                    _check_readable(app, inline, base_dir)
                i += 1
                continue
            if a in _VALUE_FLAGS:
                if i + 1 < len(argv):
                    value = argv[i + 1]
                    if a in _INPUT_FILE_FLAGS and value != "<input>":
                        _check_readable(app, value, base_dir)
                    i += 2
                else:
                    i += 1
                continue
            if a.startswith("-o") and len(a) > 2:
                i += 1  # attached output target, rewritten later
                continue
            i += 1  # boolean / unknown flag
            continue
        positionals.append(a)
        i += 1

    for token in positionals:
        if token == "<input>":
            continue
        candidate = Path(token).expanduser()
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        if candidate.exists():
            _check_readable(app, str(candidate), base_dir)


def _check_readable(app: Any, path: str, base_dir: Optional[Path] = None) -> None:
    if base_dir is None:
        base_dir = app.workspace.root
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    p = app.workspace.assert_readable(candidate)
    app.workspace.check_file_size(p)


def _tail(raw: Optional[str]) -> str:
    if not raw:
        return ""
    return raw[-_MAX_TAIL:]


@tool("run_figtreekit_cli")
def run_figtreekit_cli(
    ctx: Context,
    argv: Optional[List[str]] = None,
    tree_content: Optional[str] = None,
    input_file: Optional[str] = None,
    timeout: int = 300,
    capture_tail_bytes: int = 65536,
) -> Dict[str, Any]:
    """Run the figtreekit CLI with arbitrary argv (full CLI coverage; no
    shell).  Outputs are redirected into the run directory; each rewrite is
    disclosed in ``rewrites``.

    Args:
        argv: The figtreekit arguments as an array.  Use ``<input>`` as a
            placeholder consumed by tree_content / input_file.
        tree_content: If provided, written as run_dir/input.tre and replaces
            ``<input>`` in argv.
        input_file: Or a whitelisted file reference (same placeholder rule).
        timeout: Max execution seconds (default 300).
        capture_tail_bytes: Max bytes of stdout/stderr kept (default 64 KiB).
    """
    app = get_app(ctx)
    run = require_run(ctx)
    args = _validate_argv(argv)

    # ---- materialise tree input / placeholder ---------------------------
    if tree_content is not None and input_file is not None:
        raise ToolError(
            "invalid_argument",
            "tree_content 与 input_file 不能同时提供",
            error_key="mutually_exclusive_input",
        )
    if tree_content is not None:
        app.workspace.check_content_size(tree_content)
        input_path = run.run_dir / "input.tre"
        input_path.write_text(tree_content, encoding="utf-8")
        args = [_materialise(a, str(input_path)) for a in args]
    elif input_file is not None:
        resolved = app.workspace.assert_readable(input_file)
        app.workspace.check_file_size(resolved)
        args = [_materialise(a, str(resolved)) for a in args]

    _verify_inputs(args, app, run)
    rewritten = _rewrite_output_args(args, run.run_dir)
    rewrites = _diff_rewrites(args, rewritten)

    # ---- execution (zero shell) ------------------------------------------
    started = time.monotonic()
    cmd = [sys.executable, "-m", "figtreekit", *rewritten]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(run.run_dir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            "cli_timeout",
            f"透传命令超时（>{timeout}s）",
            error_key="cli_timeout",
            error_detail=f"cmd={' '.join(cmd[:120])}…",
        ) from exc
    elapsed = round(time.monotonic() - started, 2)

    artifacts = _scan_artifacts(run)
    tail_bytes = max(1, min(int(capture_tail_bytes or _MAX_TAIL), _MAX_TAIL))

    if proc.returncode != 0:
        joiner = (
            (proc.stdout or "")[-tail_bytes:] + "\n[stderr]\n" + (proc.stderr or "")[-tail_bytes:]
        )
        raise ToolError(
            "cli_failed",
            f"figtreekit 命令以退出码 {proc.returncode} 结束",
            error_key="cli_failed",
            error_detail=joiner[-4096:],
            details=[
                {"level": "ERROR", "message": "returncode={}".format(proc.returncode)},
                {"level": "DIAG", "message": "stdout_tail=" + _tail(proc.stdout)[-tail_bytes:]},
                {"level": "DIAG", "message": "stderr_tail=" + _tail(proc.stderr)[-tail_bytes:]},
            ],
        )

    return ok_envelope(
        returncode=proc.returncode,
        stdout_tail=_tail(proc.stdout)[-tail_bytes:],
        stderr_tail=_tail(proc.stderr)[-tail_bytes:],
        artifacts=artifacts,
        rewrites=rewrites,
        elapsed_s=elapsed,
        run_dir=run.name,
    )


def _materialise(arg: str, path: str) -> str:
    return path if arg == "<input>" else arg


def _diff_rewrites(before: List[str], after: List[str]) -> List[str]:
    if before == after:
        return []
    out: List[str] = []
    for b, a in zip(before, after):
        if b != a:
            out.append(f"{b} → {a}")
    for b in before[len(after) :]:
        out.append(f"{b} → (dropped)")
    for a in after[len(before) :]:
        out.append(f"(added) → {a}")
    return out


def _scan_artifacts(run: RunStorage, before: Optional[set] = None) -> List[Dict[str, Any]]:
    """Register run-dir artifacts (images get mime/data_uri like T20).

    ``before`` is accepted for backwards compatibility and unused.
    """
    artifacts: List[Dict[str, Any]] = []
    run_dir = run.run_dir.resolve()
    for p in sorted(run.run_dir.iterdir()):
        if p.is_symlink() or not p.is_file():
            continue
        if p.name == "input.tre":
            continue
        if p.suffix.lower() in (
            ".nex",
            ".png",
            ".pdf",
            ".svg",
            ".jpg",
            ".jpeg",
            ".log",
            ".txt",
            ".json",
            ".newick",
            ".tre",
        ):
            try:
                if not p.resolve().is_relative_to(run_dir):
                    continue
                artifacts.append(run.register(p, with_data_uri=True))
            except (OSError, ToolError):  # pragma: no cover - best effort
                continue
    return artifacts


__all__ = ["run_figtreekit_cli"]
