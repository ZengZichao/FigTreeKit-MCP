#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Example 03 - publication-style polar figure (Nexus + PNG/PDF).

Runs with **zero external data** by default (built-in 12-tip tree with
GTDB-style taxonomy tags).  Two modes are supported:

* default: style, export ``.nex`` and render PNG + PDF.  Rendering requires
  Java 8+ and ``figtree_patched.jar``; when they are missing the script exits
  **non-zero** (no silent success);
* ``--style-only``: style and export the ``.nex`` only, never touch Java, and
  exit 0.

Usage (from the repository root)::

    python examples/03_publication_figure.py --style-only
    python examples/03_publication_figure.py
    python examples/03_publication_figure.py --tree /path/to/tree.nwk \\
        --mapping /path/to/taxonomy.tsv

Exit codes: 0 = success (including ``--style-only``), 1 = styling/render
failure, 2 = usage error / missing input / missing dependency.
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
        "       bash scripts/setup_env.sh",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

_BUILTIN_TREE = (
    "(((T1_p__PhyA_c__Cls1:0.1,T2_p__PhyA_c__Cls1:0.2):0.3,"
    "(T3_p__PhyA_c__Cls2:0.1,T4_p__PhyA_c__Cls2:0.15):0.25):0.5,"
    "(T5_p__PhyB_c__Cls3:0.1,T6_p__PhyB_c__Cls3:0.12):0.3,"
    "((T7_p__PhyC_c__Cls4:0.1,T8_p__PhyD_c__Cls5:0.1):0.2,"
    "(T9_p__PhyC_c__Cls4:0.2,T10_p__PhyC_c__Cls6:0.2):0.3):0.4,"
    "(T11_p__PhyE_c__Cls7:0.1,T12_p__PhyE_c__Cls8:0.1):0.2);"
)
_TAXONOMY_LEVELS = "d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus"
_RENDER_FORMATS = (("PNG", 2400, 1600), ("PDF", 2400, 1600))


class _FakeCtx:
    """Minimal stand-in for ``mcp.server.fastmcp.Context``."""

    def __init__(self, app: Any) -> None:
        self.request_context = types.SimpleNamespace(lifespan_context=app)

    def report_progress(self, *a: Any, **k: Any) -> None:
        pass

    def info(self, *a: Any, **k: Any) -> None:
        pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Example 03: polar publication figure via FigTreeKit-MCP.",
    )
    parser.add_argument(
        "--tree",
        default=os.environ.get("FIGTREEKIT_MCP_TREE"),
        help="Newick/Nexus tree file (default: built-in 12-tip tree; "
             "env: FIGTREEKIT_MCP_TREE)",
    )
    parser.add_argument(
        "--mapping",
        default=os.environ.get("FIGTREEKIT_MCP_MAPPING"),
        help="Optional taxonomy mapping table (TSV/CSV); only needed when "
             "tip labels carry no taxonomy (env: FIGTREEKIT_MCP_MAPPING)",
    )
    parser.add_argument(
        "--style-only",
        action="store_true",
        help="Export the styled .nex only; skip rendering (no Java/JAR needed)",
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
    create_server({
        "workspace_root": workspace,
        "read_roots": read_roots,
        "jar": None,
    })
    app = get_active_app()
    if app is None:  # pragma: no cover - defensive
        raise RuntimeError("create_server() did not install an AppContext")
    return _FakeCtx(app)


def _print_error(prefix: str, exc: ToolError) -> None:
    key = exc.code if exc.code == exc.error_key else f"{exc.code}/{exc.error_key}"
    print(f"[FAIL] {prefix}: {key}: {exc.error}", file=sys.stderr)
    if exc.error_detail:
        print(f"       {exc.error_detail}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)

    tree_path: Optional[Path] = None
    mapping_path: Optional[Path] = None
    if args.tree:
        tree_path = Path(args.tree).expanduser().resolve()
        if not tree_path.is_file():
            print(f"[FAIL] tree file not found: {tree_path}", file=sys.stderr)
            return 2
    if args.mapping:
        mapping_path = Path(args.mapping).expanduser().resolve()
        if not mapping_path.is_file():
            print(f"[FAIL] mapping file not found: {mapping_path}",
                  file=sys.stderr)
            return 2

    read_roots: List[str] = []
    for path in (tree_path, mapping_path):
        if path and str(path.parent) not in read_roots:
            read_roots.append(str(path.parent))
    workspace = _resolve_workspace(args.workspace)

    target: Dict[str, str] = (
        {"tree_file": str(tree_path)} if tree_path else {"tree_content": _BUILTIN_TREE}
    )
    taxonomy_kwargs: Dict[str, str] = {"taxonomy_levels": _TAXONOMY_LEVELS}
    if mapping_path:
        taxonomy_kwargs["taxonomy_mapping_file"] = str(mapping_path)

    mode = "style-only (no Java/JAR)" if args.style_only else "render PNG + PDF"
    print("== FigTreeKit-MCP example 03: publication figure ==")
    print(f"tree      : {tree_path or 'built-in 12-tip tree (embedded taxonomy)'}")
    print(f"mapping   : {mapping_path or 'none (taxonomy parsed from tip labels)'}")
    print(f"mode      : {mode}")
    print(f"workspace : {workspace}")

    try:
        ctx = _make_ctx(workspace, read_roots)

        summary = TOOLS["summarize_tree"](
            ctx, **target, include_tip_labels=False,
        )
        stats = summary.get("statistics", {})
        print("== summarize_tree ==")
        print(f"  tips={stats.get('tips')} "
              f"tree_count={summary.get('tree_count')} "
              f"format={summary.get('format')}")

        print("== style_tree (polar + class collapse/cartoon + phylum colors) ==")
        styled = TOOLS["style_tree"](
            ctx, **target, **taxonomy_kwargs,
            layout="polar",
            auto_color_rank="phylum",
            tip_labels="hide",
            polar_angular_range_degrees=180,
            polar_root_angle_degrees=90,
            scale_axis="show",
            scale_axis_reverse=False,
            scale_axis_font_size=14,
            scale_axis_significant_digits=2,
            operations=[{
                "op": "collapse_rank",
                "rank": "class",
                "collapse_style": "cartoon",
            }],
        )
    except ToolError as exc:
        _print_error("styling failed", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - report, do not traceback
        print(f"[FAIL] unexpected error: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1

    if not styled.get("ok"):
        print(f"[FAIL] style_tree: {styled.get('error_key')}", file=sys.stderr)
        return 1

    nexus = styled.get("nexus_file", {}).get("absolute")
    if not nexus or not Path(nexus).is_file():
        print("[FAIL] Nexus was not written", file=sys.stderr)
        return 1

    print(f"  nexus_file={nexus}")
    print(f"  cli_command={styled.get('cli_command')}")
    for record in styled.get("operations_applied", []):
        detail = ", ".join(f"{k}={v}" for k, v in record.items()
                           if k not in ("op", "status"))
        suffix = f" ({detail})" if detail else ""
        print(f"  operation: {record.get('op')}={record.get('status')}{suffix}")

    # The exported Nexus must really carry the styling annotations; otherwise
    # a silently ignored operation would still look like success.
    nexus_text = Path(nexus).read_text(encoding="utf-8")
    if "!color" not in nexus_text:
        print("[FAIL] exported Nexus has no !color annotations", file=sys.stderr)
        return 1
    collapse_applied = any(
        record.get("op") == "collapse_rank"
        and record.get("status") == "applied"
        and int(record.get("applied_count") or 0) > 0
        for record in styled.get("operations_applied", [])
    )
    if collapse_applied and "!collapse" not in nexus_text and "!cartoon" not in nexus_text:
        print("[FAIL] exported Nexus has no !collapse/!cartoon annotations",
              file=sys.stderr)
        return 1
    print("[PASS] exported Nexus contains the expected style annotations")

    rendered: List[tuple[str, str]] = []
    if args.style_only:
        print("== render_tree ==")
        print("  skipped (--style-only)")
    else:
        print("== render_tree ==")
        for fmt, width, height in _RENDER_FORMATS:
            try:
                result = TOOLS["render_tree"](
                    ctx, nexus_file=nexus, format=fmt,
                    width=width, height=height,
                )
            except ToolError as exc:
                _print_error(f"render {fmt}", exc)
                print(
                    "  hint: install Java 8+ and figtree_patched.jar "
                    "(TOOLS check_figtree / setup_figtree), or rerun with "
                    "--style-only.",
                    file=sys.stderr,
                )
                return 1
            if not result.get("ok"):
                print(f"[FAIL] render {fmt}: {result.get('error_key')}",
                      file=sys.stderr)
                print(
                    "  hint: rerun with --style-only if rendering is not "
                    "available in this environment.",
                    file=sys.stderr,
                )
                return 1
            image = result.get("image", {})
            path = image.get("absolute")
            if not path or not Path(path).is_file():
                print(f"[FAIL] render {fmt}: output file missing",
                      file=sys.stderr)
                return 1
            rendered.append((fmt, path))
            dimensions = ""
            if image.get("width") and image.get("height"):
                dimensions = f"{image['width']}x{image['height']}, "
            print(f"  {fmt}: {path} ({dimensions}{image.get('size_bytes')} bytes)")

    print()
    print("Artifacts:")
    print(f"  nexus: {nexus}")
    for fmt, path in rendered:
        print(f"  {fmt}: {path}")
    if args.style_only:
        print("Result: styled Nexus exported; rendering skipped (exit 0).")
    else:
        print("Result: styled Nexus and rendered images produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
