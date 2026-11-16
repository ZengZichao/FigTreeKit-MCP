#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Example 01 - validate and summarize a phylogenetic tree.

This example runs end-to-end with **zero external data**: by default it uses a
small built-in 12-tip Newick tree.  Pass ``--tree`` (or set
``FIGTREEKIT_MCP_TREE``) to analyse your own Newick/Nexus file instead.

The script drives the same in-process MCP tool handlers as the server:

1. ``validate_tree`` - deep validation (format, counts, structural errors);
2. ``summarize_tree`` - statistics, branch lengths, tip-label preview.

Usage (from the repository root)::

    python examples/01_validate_and_summarize.py
    python examples/01_validate_and_summarize.py --tree /path/to/tree.nwk

Exit codes: 0 = validation and summary succeeded, 1 = a tool reported an
error, 2 = usage error / missing input / missing dependency.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Make the checkout importable even without ``pip install -e .``.
# The package lives under ``src/``; the repository root is kept as well so the
# script also works when the package is installed in editable mode.
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (_ROOT, _ROOT / "src"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

try:  # pragma: no cover - exercised by running the script
    from figtreekit_mcp._errors import ToolError
    from figtreekit_mcp.server import create_server, get_active_app
    from figtreekit_mcp.tools import TOOLS
except ModuleNotFoundError as exc:  # pragma: no cover
    print(
        f"[FAIL] missing dependency {exc.name!r}. Install the project first:\n"
        "       bash scripts/setup_env.sh\n"
        "       (or: python -m pip install -e '.[dev,render]')",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

# A tiny tree with GTDB-style embedded taxonomy.  Example 02/03 reuse the same
# topology, so the three scripts tell one consistent story without downloads.
_BUILTIN_TREE = (
    "(((T1_p__PhyA_c__Cls1:0.1,T2_p__PhyA_c__Cls1:0.2):0.3,"
    "(T3_p__PhyA_c__Cls2:0.1,T4_p__PhyA_c__Cls2:0.15):0.25):0.5,"
    "(T5_p__PhyB_c__Cls3:0.1,T6_p__PhyB_c__Cls3:0.12):0.3,"
    "((T7_p__PhyC_c__Cls4:0.1,T8_p__PhyD_c__Cls5:0.1):0.2,"
    "(T9_p__PhyC_c__Cls4:0.2,T10_p__PhyC_c__Cls6:0.2):0.3):0.4,"
    "(T11_p__PhyE_c__Cls7:0.1,T12_p__PhyE_c__Cls8:0.1):0.2);"
)


class _FakeCtx:
    """Minimal stand-in for ``mcp.server.fastmcp.Context``.

    Tool handlers only read ``ctx.request_context.lifespan_context`` and call
    the advisory ``report_progress`` / ``info`` methods.
    """

    def __init__(self, app: Any) -> None:
        self.request_context = types.SimpleNamespace(lifespan_context=app)

    def report_progress(self, *a: Any, **k: Any) -> None:
        pass

    def info(self, *a: Any, **k: Any) -> None:
        pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Example 01: validate and summarize a tree via FigTreeKit-MCP.",
    )
    parser.add_argument(
        "--tree",
        default=os.environ.get("FIGTREEKIT_MCP_TREE"),
        help="Newick/Nexus tree file (default: built-in 12-tip tree; env: FIGTREEKIT_MCP_TREE)",
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("FIGTREEKIT_MCP_WORKSPACE"),
        help="Writable workspace directory (default: a temporary directory; "
        "env: FIGTREEKIT_MCP_WORKSPACE)",
    )
    return parser


def _resolve_workspace(value: Optional[str]) -> str:
    if value:
        path = Path(value).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    return tempfile.mkdtemp(prefix="figtreekit-mcp-example-")


def _make_ctx(workspace: str, read_roots: List[str]) -> _FakeCtx:
    # ``create_server`` imports and registers all 21 tool handlers, so
    # ``TOOLS`` is complete before we call a handler directly.
    create_server(
        {
            "workspace_root": workspace,
            "read_roots": read_roots,
            "jar": None,
        }
    )
    app = get_active_app()
    if app is None:  # pragma: no cover - defensive
        raise RuntimeError("create_server() did not install an AppContext")
    return _FakeCtx(app)


def _print_error(prefix: str, exc: ToolError) -> None:
    key = exc.code if exc.code == exc.error_key else f"{exc.code}/{exc.error_key}"
    print(f"[FAIL] {prefix}: {key}: {exc.error}", file=sys.stderr)
    if exc.error_detail:
        print(f"       {exc.error_detail}", file=sys.stderr)
    for item in exc.details:
        print(f"       {item.get('level', 'ERROR')}: {item.get('message', '')}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)

    tree_path: Optional[Path] = None
    if args.tree:
        tree_path = Path(args.tree).expanduser().resolve()
        if not tree_path.is_file():
            print(f"[FAIL] tree file not found: {tree_path}", file=sys.stderr)
            return 2

    workspace = _resolve_workspace(args.workspace)
    read_roots = [str(tree_path.parent)] if tree_path else []
    source = str(tree_path) if tree_path else "built-in 12-tip Newick tree"
    target: Dict[str, str] = (
        {"tree_file": str(tree_path)} if tree_path else {"tree_content": _BUILTIN_TREE}
    )

    print("== FigTreeKit-MCP example 01: validate + summarize ==")
    print(f"input     : {source}")
    print(f"workspace : {workspace}")

    try:
        ctx = _make_ctx(workspace, read_roots)
        validation = TOOLS["validate_tree"](ctx, **target)
        summary = TOOLS["summarize_tree"](
            ctx,
            **target,
            include_tip_labels=True,
            tip_labels_limit=20,
        )
    except ToolError as exc:
        _print_error("tool call failed", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - report, do not traceback
        print(f"[FAIL] unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("== validate_tree ==")
    print(
        "  [PASS] valid={valid} format={fmt} leaf_count={leaves} tree_count={trees}".format(
            valid=validation.get("valid"),
            fmt=validation.get("format"),
            leaves=validation.get("leaf_count"),
            trees=validation.get("tree_count"),
        )
    )
    warnings = validation.get("warnings") or []
    if warnings:
        print(f"  warnings: {len(warnings)}")
        for w in warnings[:5]:
            print(f"    WARNING: {w}")

    stats: Dict[str, Any] = summary.get("statistics", {})
    branch: Dict[str, Any] = stats.get("branch_lengths", {})
    print("== summarize_tree ==")
    print(
        f"  format={summary.get('format')} tree_count={summary.get('tree_count')} "
        f"tips={stats.get('tips')}"
    )
    print(f"  internal_nodes={stats.get('internal_nodes')} rooted={stats.get('rooted')}")
    print(
        "  branch_lengths min={mn} max={mx} negative={neg} has_missing={miss}".format(
            mn=branch.get("min"),
            mx=branch.get("max"),
            neg=branch.get("negative"),
            miss=branch.get("has_missing"),
        )
    )
    preview = summary.get("tip_labels_preview") or []
    print(f"  tip_labels_total={summary.get('tip_labels_total')} preview(first 20)={preview}")
    if summary.get("multi_tree_hint"):
        print(f"  multi_tree_hint: {summary['multi_tree_hint']}")

    print()
    print("| format | tips | trees | issues | verdict |")
    print("|--------|------|-------|--------|---------|")
    issues = "none (ERROR)" if not warnings else f"{len(warnings)} warning(s)"
    print(
        f"| {validation.get('format')} | {stats.get('tips')} | "
        f"{validation.get('tree_count')} | {issues} | PASS |"
    )
    print()
    print("Result: validation and summary passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
