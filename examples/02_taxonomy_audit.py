#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Example 02 - taxonomy audit with a colored Nexus export.

Runs with **zero external data** by default: the built-in tree carries
GTDB-style taxonomy tags (``p__`` / ``c__``) in its tip labels and contains one
deliberately non-monophyletic phylum (``PhyC``).

Pipeline:

1. ``analyze_taxonomy(rank="phylum")`` - monophyly summary;
2. ``taxonomy_completeness`` - coverage per rank;
3. ``style_tree`` - export a Nexus with real branch colors.

Important detail: FigTreeKit resolves ``taxa`` in clade operations against
**tip labels**, so passing a phylum *name* (for example ``"PhyC"``) to
``color_all`` / ``color`` silently does nothing.  This example therefore uses
``auto_color_rank="phylum"`` (the same ``color_groups_by_result`` code path:
monophyletic groups -> ``set_clade_color_all``, non-monophyletic groups ->
per-tip ``set_clade_color``) and, when the complete tip list is available,
explicit per-tip ``color`` operations built from resolved tip labels.  The
exported Nexus is then checked for ``!color`` annotations.

Usage (from the repository root)::

    python examples/02_taxonomy_audit.py
    python examples/02_taxonomy_audit.py --tree /path/to/tree.nwk \\
        --mapping /path/to/taxonomy.tsv

Exit codes: 0 = audit + coloring succeeded, 1 = a tool failed or coloring was
a no-op, 2 = usage error / missing input / missing dependency.
"""
from __future__ import annotations

import argparse
import os
import re
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
_PALETTE = [
    "#E53935", "#D81B60", "#8E24AA", "#5E35B1", "#3949AB",
    "#1E88E5", "#00897B", "#43A047", "#F4511E", "#6D4C41",
]
_COLOR_RE = re.compile(r"!color=#[0-9a-fA-F]{6}")


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
        description="Example 02: taxonomy audit + colored Nexus via FigTreeKit-MCP.",
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
        "--rank",
        default="phylum",
        choices=("domain", "superphylum", "phylum", "class", "order",
                 "family", "genus", "species"),
        help="Taxonomic rank to audit (default: phylum)",
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


def _display_group(name: str) -> str:
    """FigTreeKit may return ``_PhyA`` for underscore-delimited labels."""
    return name.strip("_") or name


def _print_error(prefix: str, exc: ToolError) -> None:
    key = exc.code if exc.code == exc.error_key else f"{exc.code}/{exc.error_key}"
    print(f"[FAIL] {prefix}: {key}: {exc.error}", file=sys.stderr)
    if exc.error_detail:
        print(f"       {exc.error_detail}", file=sys.stderr)


def _tip_is_colored(text: str, tip: str) -> bool:
    """True when *tip* carries an inline ``!color`` annotation."""
    pattern = re.escape(tip) + r"(?::[^,\[\]()]*)?\[&!color=#[0-9a-fA-F]{6}\]"
    return re.search(pattern, text) is not None


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

    print("== FigTreeKit-MCP example 02: taxonomy audit ==")
    print(f"tree      : {tree_path or 'built-in 12-tip tree (embedded taxonomy)'}")
    print(f"mapping   : {mapping_path or 'none (taxonomy parsed from tip labels)'}")
    print(f"rank      : {args.rank}")
    print(f"workspace : {workspace}")

    try:
        ctx = _make_ctx(workspace, read_roots)

        # 1) Monophyly audit -------------------------------------------------
        analysis = TOOLS["analyze_taxonomy"](
            ctx, **target, **taxonomy_kwargs, rank=args.rank,
        )
        if not analysis.get("ok"):
            print(f"[FAIL] analyze_taxonomy: {analysis.get('error_key')}",
                  file=sys.stderr)
            return 1
        summary: Dict[str, Any] = analysis.get("summary", {})
        mono: List[Dict[str, Any]] = analysis.get("monophyletic", [])
        non_mono: List[Dict[str, Any]] = analysis.get("non_monophyletic", [])

        # 2) Completeness ----------------------------------------------------
        completeness = TOOLS["taxonomy_completeness"](
            ctx, **target, **taxonomy_kwargs,
        )
        if not completeness.get("ok"):
            print(f"[FAIL] taxonomy_completeness: "
                  f"{completeness.get('error_key')}", file=sys.stderr)
            return 1
    except ToolError as exc:
        _print_error("taxonomy audit failed", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - report, do not traceback
        print(f"[FAIL] unexpected error: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1

    print(f"== analyze_taxonomy(rank={args.rank}) ==")
    print(
        "  total_labels={t} mapped={m} unmapped={u}".format(
            t=summary.get("total_labels"), m=summary.get("mapped_labels"),
            u=summary.get("unmapped_labels"),
        )
    )
    print(
        "  groups={g} monophyletic={mo} non_monophyletic={nmo} "
        "monophyly_rate={rate}%".format(
            g=summary.get("total_groups"), mo=summary.get("monophyletic"),
            nmo=summary.get("non_monophyletic"),
            rate=summary.get("monophyly_rate"),
        )
    )
    print("  monophyletic    : " + (", ".join(
        f"{_display_group(g['group'])}({g['taxa_count']})" for g in mono
    ) or "none"))
    print("  non-monophyletic: " + (", ".join(
        f"{_display_group(g['group'])}({g['taxa_count']})" for g in non_mono
    ) or "none"))

    print("== taxonomy_completeness ==")
    print(
        "  coverage={c}% complete={ct} incomplete={it} missing={mt}".format(
            c=completeness.get("coverage"),
            ct=completeness.get("complete_total"),
            it=completeness.get("incomplete_total"),
            mt=completeness.get("missing_total"),
        )
    )
    print(f"  rank_coverage={completeness.get('rank_coverage')}")

    # 3) Build real per-tip operations for non-monophyletic groups -----------
    # ``analyze_taxonomy`` returns group names and counts (not tip lists), so
    # resolve the actual tips with ``check_monophyly``.  The MCP response
    # previews at most 10 tips; when a group is larger we leave the coloring to
    # ``auto_color_rank`` (which resolves the complete list internally).
    operations: List[Dict[str, Any]] = []
    per_tip_targets: Dict[str, List[str]] = {}
    if mapping_path is not None:
        print("  note: mapping file supplied - explicit per-tip override is "
              "skipped; auto_color_rank uses the resolved mapping.")
    else:
        for index, group in enumerate(non_mono):
            name = group["group"]
            try:
                check = TOOLS["check_monophyly"](
                    ctx, **target, groups=[name],
                    taxonomy_levels=_TAXONOMY_LEVELS,
                )
            except ToolError as exc:
                print(f"  note: cannot resolve tips for {_display_group(name)} "
                      f"({exc.error_key}); auto_color_rank still colors it.")
                continue
            entry = check["results"][0]
            tips = list(entry.get("resolved_taxa_preview") or [])
            if tips and entry.get("resolved_taxa_count") == len(tips):
                color = _PALETTE[index % len(_PALETTE)]
                # One ``color`` op per terminal: set_clade_color colors the
                # MRCA branch, so a single op with all tips would over-color.
                for tip in tips:
                    operations.append(
                        {"op": "color", "taxa": [tip], "color": color}
                    )
                per_tip_targets[name] = tips
            else:
                print(
                    f"  note: {_display_group(name)} has "
                    f"{entry.get('resolved_taxa_count')} tips; only a preview "
                    "is returned, so explicit per-tip ops are skipped."
                )

    # 4) Style + export ------------------------------------------------------
    print("== style_tree (phylum auto-color + explicit non-monophyletic tips) ==")
    try:
        styled = TOOLS["style_tree"](
            ctx, **target, **taxonomy_kwargs,
            layout="rectilinear",
            tip_labels="show",
            auto_color_rank=args.rank,
            operations=operations or None,
        )
    except ToolError as exc:
        _print_error("style_tree failed", exc)
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
    print("  operations_applied:")
    for record in styled.get("operations_applied", []):
        detail = ", ".join(f"{k}={v}" for k, v in record.items()
                           if k not in ("op", "status"))
        suffix = f" ({detail})" if detail else ""
        print(f"    - {record.get('op')}: {record.get('status')}{suffix}")

    # 5) Verify that coloring actually happened ------------------------------
    text = Path(nexus).read_text(encoding="utf-8")
    annotations = _COLOR_RE.findall(text)
    if not annotations:
        print("[FAIL] exported Nexus contains no !color annotations - "
              "coloring was a no-op", file=sys.stderr)
        return 1
    print(f"[PASS] exported Nexus contains {len(annotations)} !color "
          "annotation(s)")

    failed = False
    for name, tips in per_tip_targets.items():
        missing = [tip for tip in tips if not _tip_is_colored(text, tip)]
        if missing:
            failed = True
            print(f"[FAIL] {_display_group(name)}: {len(missing)} of "
                  f"{len(tips)} tips lack !color", file=sys.stderr)
        else:
            print(f"[PASS] {_display_group(name)}: {len(tips)}/{len(tips)} "
                  "non-monophyletic tips carry !color")
    if failed:
        return 1

    print()
    print("Audit result:")
    print("| group | monophyletic | taxa_count |")
    print("|-------|--------------|------------|")
    for group in sorted(mono + non_mono,
                        key=lambda g: (-g["taxa_count"], g["group"])):
        is_mono = any(g["group"] == group["group"] for g in mono)
        print(f"| {_display_group(group['group'])} | "
              f"{'yes' if is_mono else 'no'} | {group['taxa_count']} |")
    print()
    print("Result: taxonomy audit completed; Nexus coloring verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
