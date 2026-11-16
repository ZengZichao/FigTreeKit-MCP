# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Process entry point: argparse, transport adaptation, signals, --self-test.

Exit codes follow figtreekit conventions: 0 ok, 1 runtime failure, 2 usage
error, 130 interrupted (SIGINT/SIGTERM).
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._errors import ToolError, envelope_from_exception
from ._logging import setup_logger
from ._version import __version__

_log = None  # configured in main()


def _positive_int(value: str) -> int:
    v = int(value)
    if v <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return v


def _non_negative_int(value: str) -> int:
    v = int(value)
    if v < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return v


def create_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="figtreekit-mcp",
        description=(
            "MCP server exposing FigTreeKit: validate, analyze, style, export "
            "and render phylogenetic trees for AI assistants."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for sse/http (default: 127.0.0.1, loopback only)",
    )
    parser.add_argument(
        "--port", type=_positive_int, default=8777, help="Bind port for sse/http (default: 8777)"
    )
    parser.add_argument(
        "--allow-remote-bind",
        action="store_true",
        help="Allow non-loopback binds (policy: Studio resolve_bind_host)",
    )
    parser.add_argument(
        "--workspace-root",
        type=str,
        default=None,
        help="Writable workspace root (default: ./figtreekit-mcp-workspace)",
    )
    parser.add_argument(
        "--allow-read-root",
        action="append",
        default=[],
        metavar="DIR",
        help="Read-only whitelist root (repeatable)",
    )
    parser.add_argument(
        "--jar", default=None, metavar="PATH", help="Explicit figtree_patched.jar path"
    )
    parser.add_argument(
        "--content-max-bytes",
        type=_positive_int,
        default=10 * 1024 * 1024,
        help="Max tree_content bytes (default: 10485760)",
    )
    parser.add_argument(
        "--file-max-bytes",
        type=_positive_int,
        default=200 * 1024 * 1024,
        help="Max whitelisted file bytes (default: 209715200)",
    )
    parser.add_argument(
        "--cli-timeout",
        type=_positive_int,
        default=300,
        help="Pass-through CLI timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--render-timeout",
        type=_positive_int,
        default=180,
        help="Render JVM timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--setup-timeout",
        type=_positive_int,
        default=600,
        help="FigTree setup timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--keep-runs",
        type=_non_negative_int,
        default=50,
        help="Run directories to keep (default: 50)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v INFO, -vv DEBUG)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="ERROR-level logs only")
    parser.add_argument("--log-file", default=None, help="Append logs to a file")
    parser.add_argument(
        "--self-test", action="store_true", help="Run self-diagnostics and exit (0/1)"
    )
    parser.add_argument("--version", action="version", version=f"figtreekit-mcp {__version__}")
    return parser


def _resolve_bind_host(host: str, allow_remote: bool) -> str:
    if allow_remote:
        return host
    on_loopback = host in ("127.0.0.1", "::1", "localhost", "")
    if not on_loopback:
        print(
            f"[figtreekit-mcp] 拒绝非回环绑定 {host!r}：请显式使用 --allow-remote-bind。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return host


def _config_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    if args.workspace_root:
        root: str = args.workspace_root
    else:
        root = str(Path.cwd() / "figtreekit-mcp-workspace")
    return {
        "workspace_root": root,
        "read_roots": list(args.allow_read_root or []),
        "jar": args.jar,
        "content_max_bytes": args.content_max_bytes,
        "file_max_bytes": args.file_max_bytes,
        "cli_timeout": args.cli_timeout,
        "render_timeout": args.render_timeout,
        "setup_timeout": args.setup_timeout,
        "keep_runs": args.keep_runs,
    }


# --------------------------------------------------------------------------- #
# --self-test
# --------------------------------------------------------------------------- #
class _FakeCtx:
    """Minimal Context stand-in for self-test handler invocation."""

    request_context = None

    def __init__(self, app: Any) -> None:
        self.request_context = types.SimpleNamespace(lifespan_context=app)

    def report_progress(self, *a: Any, **k: Any) -> None:
        pass

    def info(self, *a: Any, **k: Any) -> None:
        pass


def _scan_no_stdout_print(src_dir: Path) -> List[str]:
    """Static check: no bare ``print(`` writing to stdout (SEC-12).

    CLI entry files (``_cli.py`` / ``__main__.py``) are excluded: their
    stdout output is the terminal surface (--self-test table, --version),
    never MCP protocol frames.

    Hidden files (``._*.py`` / ``.__*.py`` AppleDouble junk, ``.DS_Store``
    siblings) and ``__pycache__`` are skipped: they are metadata, not Python
    source, and are often binary (a strict UTF-8 decode would crash).  Any
    remaining undecodable byte is replaced rather than aborting the scan.
    """
    exclude = {"_cli.py", "__main__.py"}
    issues: List[str] = []
    for p in sorted(src_dir.rglob("*.py")):
        rel_parts = p.relative_to(src_dir).parts
        if p.name in exclude:
            continue
        if any(part.startswith(".") or part == "__pycache__" for part in rel_parts):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if re.match(r"^print\s*\(", stripped):
                issues.append(f"{p.relative_to(src_dir.parent)}:{lineno}: 裸 print() 写入 stdout")
    return issues


def run_self_test(mcp: Any) -> int:
    """Run the self-test checklist; returns process exit code."""
    from .server import get_active_app

    app = get_active_app()
    checks: List[tuple] = []
    ok = "\u001b[32m[PASS]\u001b[0m"
    fail = "\u001b[31m[FAIL]\u001b[0m"

    # 1. dependencies
    deps_ok = True
    for pkg in ("mcp", "figtreekit", "Bio"):
        try:
            __import__(pkg)
        except Exception as exc:  # noqa: BLE001
            deps_ok = False
            checks.append((f"依赖可导入: {pkg}", False, str(exc)))
    if deps_ok:
        checks.append(("依赖可导入 (mcp/figtreekit/biopython)", True, ""))

    # 2. tool registry
    from .tools import TOOLS

    expected = {
        "get_environment",
        "check_figtree",
        "setup_figtree",
        "validate_tree",
        "summarize_tree",
        "cross_validate",
        "check_monophyly",
        "analyze_taxonomy",
        "taxonomy_completeness",
        "style_tree",
        "apply_config",
        "export_nexus",
        "highlight_clade",
        "color_clade",
        "set_clade_font",
        "collapse_clade",
        "collapse_group",
        "collapse_rank",
        "clear_annotations",
        "render_tree",
        "run_figtreekit_cli",
    }
    missing = expected - set(TOOLS)
    checks.append(
        (
            "工具注册（恰 21 个）",
            len(TOOLS) == 21 and not missing,
            f"missing={sorted(missing)} count={len(TOOLS)}",
        )
    )

    # 3. protocol-frame purity (static)
    src_dir = Path(__file__).resolve().parent
    issues = _scan_no_stdout_print(src_dir)
    checks.append(("协议帧净化（无裸 print）", not issues, "; ".join(issues[:3])))

    # 4. Java / JAR probe（缺失 = WARN 不失败）
    try:
        from .tools.environment import probe_jar, probe_java

        j = probe_java()
        jr = probe_jar(app)
        checks.append(("Java 探测", True, "" if j["ok"] else "[WARN] java 缺失"))
        checks.append(("JAR 探测", True, "" if jr["ok"] else "[WARN] jar 缺失"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Java/JAR 探测", False, str(exc)))

    # 5. round trip: small tree → style_tree → nexus → (render if java)
    rt_ok, rt_msg = _self_test_roundtrip(app)
    checks.append(("样例往返 style_tree→.nex", rt_ok, rt_msg))

    # 6. workspace: writable run dir + whitelist rejection
    ws_ok, ws_msg = _self_test_workspace(app)
    checks.append(("工作区可写 / 越权拒绝", ws_ok, ws_msg))

    # ---- render if available ----
    try:
        from .tools.environment import probe_java

        if probe_java()["ok"]:
            _ok, msg = _self_test_render(app)
            checks.append(("样例渲染 PNG（Java 可用）", _ok, msg))
        else:
            checks.append(("样例渲染 PNG（Java 不可用）", True, "[WARN] 跳过"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("样例渲染 PNG", False, str(exc)))

    print_sep = "┌" + "─" * 74 + "┐"
    print_sep_end = "└" + "─" * 74 + "┘"
    print(f"figtreekit-mcp {__version__} --self-test")
    print(print_sep)
    all_pass = True
    for name, passed, msg in checks:
        all_pass = all_pass and passed
        tag = ok if passed else fail
        line = f"{tag} {name}"
        if msg:
            line += f"  — {msg}"
        print(line)
    print(print_sep_end)
    print(f"结果: {'ALL PASS' if all_pass else 'FAILED'}")
    return 0 if all_pass else 1


def _self_test_roundtrip(app: Any) -> tuple:
    from .tools import TOOLS

    ctx = _FakeCtx(app)
    small = "(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"
    res = TOOLS["style_tree"](
        ctx,
        tree_content=small,
        layout="polar",
        polar_angular_range_degrees=180,
        polar_root_angle_degrees=270,
        operations=[{"op": "highlight", "taxa": ["A", "B"], "color": "#FF0000"}],
    )
    if not res.get("ok"):
        return False, str(res)
    nexus = res.get("nexus_file", {}).get("absolute")
    if not nexus or not Path(nexus).is_file():
        return False, f"nexus 未生成: {res}"
    return True, Path(nexus).name


def _self_test_render(app: Any) -> tuple:
    from .tools import TOOLS

    ctx = _FakeCtx(app)
    small = "(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"
    res = TOOLS["style_tree"](ctx, tree_content=small, layout="polar")
    if not res.get("ok"):
        return False, f"style_tree: {res}"
    timeout = app.effective_render_timeout(120) if app is not None else 120
    render = TOOLS["render_tree"](
        ctx,
        nexus_file=res["nexus_file"]["absolute"],
        format="PNG",
        width=400,
        height=300,
        timeout=timeout,
    )
    if not render.get("ok"):
        _log.info("render skipped: %s", render.get("error"))
        return True, "[WARN] 渲染未完成: " + str(render.get("error"))[:120]
    img = render.get("image", {})
    if not img.get("absolute") or not Path(img["absolute"]).is_file():
        return False, f"image 未生成: {render}"
    return True, Path(img["absolute"]).name


def _self_test_workspace(app: Any) -> tuple:
    try:
        run = app.workspace.new_run()
        probe = run.run_dir / "probe.txt"
        probe.write_text("ok", encoding="utf-8")
        if not probe.is_file():
            return False, "写入失败"
        run_dir = run.name
        # whitelist rejection (use an absolute path outside every plausible
        # root: "/etc/hosts" is not absolute on Windows).
        outside = (
            "C:/__figtreekit_mcp_outside_probe__"
            if os.name == "nt"
            else "/__figtreekit_mcp_outside_probe__"
        )
        try:
            app.workspace.assert_readable(outside)
            return False, "越权路径未被拒绝"
        except ToolError:
            pass
        return True, run_dir
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------- #
# signals
# --------------------------------------------------------------------------- #
def _install_signal_handlers(logger: Any) -> None:
    def _handler(signum: int, frame: Any) -> None:
        logger.warning("收到信号 %s，退出（130）", signum)
        raise SystemExit(130)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            pass


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point (console script ``figtreekit-mcp``)."""
    parser = create_cli_parser()
    args = parser.parse_args(argv)

    global _log
    _log = setup_logger(
        verbose=args.verbose,
        quiet=args.quiet,
        log_file=args.log_file,
    )

    if args.self_test:
        try:
            mcp = _build_server(args)
            return run_self_test(mcp)
        except Exception as exc:  # noqa: BLE001 - self-test must never hang
            env = envelope_from_exception(exc)
            print(
                f"[FAIL] self-test 初始化失败: {env.get('code')} {env.get('error')}",
                file=sys.stderr,
            )
            return 1

    try:
        mcp = _build_server(args)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[figtreekit-mcp] 服务器初始化失败: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    host = _resolve_bind_host(args.host, args.allow_remote_bind)
    transport = args.transport
    _log.info("starting transport=%s host=%s port=%s", transport, host, args.port)
    _install_signal_handlers(_log)
    try:
        if transport == "stdio":
            mcp.run(transport="stdio")
        elif transport == "sse":
            mcp.run(transport="sse")
        else:
            mcp.run(transport="streamable-http")
    except SystemExit as exc:
        code = int(exc.code or 0)
        if code == 130:
            _log.warning("进程被信号中断，退出码 130")
        return code
    return 0


def _build_server(args: argparse.Namespace) -> Any:
    from .server import create_server

    host = _resolve_bind_host(args.host, args.allow_remote_bind)
    return create_server(
        _config_from_args(args),
        host=host,
        port=args.port,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
