# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Clade tools: T13 highlight_clade, T14 color_clade, T15 set_clade_font,
T16 collapse_clade, T17 collapse_group, T18 collapse_rank, T19 clear_annotations.

Each tool operates on a tree source, mutates the styler through the figtreekit
public API, and exports a FigTree-compatible Nexus.
"""

from __future__ import annotations

import re
import warnings
from typing import Any, Dict, List, Optional

import figtreekit
from mcp.server.fastmcp import Context

from .._core import (
    color_groups_by_result,
    collapse_monophyletic_groups,
    make_styler,
    resolve_tree_source,
    temporary_rank_prefixes,
)
from .._errors import ToolError
from .._logging import get_logger
from .. import cli_command
from ..params import ParamSpec
from . import (
    get_app,
    nexus_artifact,
    require_run,
    resolve_mapping_file,
    tool,
    tree_summary,
)

_log = get_logger()

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# Generic ``[&...]`` annotations.  ``[&R]`` / ``[&U]`` are Nexus root markers
# and must be kept: removing them before parsing changes the rooting state and
# is not what "strip annotations" is supposed to do.
_STRIP_ANNOTATION_RE = re.compile(r"\[&(?![RU]\])[^\]]*\]")
# Embedded FigTree annotations written by a previous FigTreeKit run.
_EMBEDDED_HILIGHT_RE = re.compile(r"\[&[^\]]*?!hilight=\{[^}]*\}[^\]]*\]")
_EMBEDDED_COLLAPSE_RE = re.compile(r"\[&[^\]]*?!collapse=\{[^}]*\}[^\]]*\]")
_EMBEDDED_CARTOON_RE = re.compile(r"\[&[^\]]*?!cartoon=\{[^}]*\}[^\]]*\]")


# --------------------------------------------------------------------------- #
# input helpers
# --------------------------------------------------------------------------- #
def _require(ctx: Context, value: Optional[List[Any]], param: str) -> List[Any]:
    if not value:
        raise ToolError(
            "invalid_argument",
            f"{param} 不能为空（至少一条操作）",
            error_key=f"missing_{param}",
        )
    return value


def _check_taxa(entry: Any, idx: int, param: str) -> List[str]:
    taxa = entry.get("taxa") if isinstance(entry, dict) else None
    if not taxa or not isinstance(taxa, list) or not all(isinstance(t, str) and t for t in taxa):
        raise ToolError(
            "invalid_argument",
            f"{param}[{idx}].taxa 必须是非空字符串名单",
            error_key="bad_taxa",
        )
    return list(taxa)


def _check_color(entry: Any, idx: int, param: str) -> str:
    color = entry.get("color", "#999999")
    if not _HEX_RE.match(color):
        raise ToolError(
            "invalid_argument",
            f"{param}[{idx}].color 必须是 #RRGGBB 形式，得到 '{color}'",
            error_key="bad_color",
        )
    return color.lower()


def _check_style(entry: Any, idx: int, param: str, default: str = "collapse") -> str:
    style = entry.get("collapse_type", default)
    if style not in ("collapse", "cartoon"):
        raise ToolError(
            "invalid_argument",
            f"{param}[{idx}].collapse_type 必须是 collapse|cartoon",
            error_key="bad_collapse_type",
        )
    return style


def _strip_annotations(content: str) -> str:
    """Remove generic ``[&...]`` annotations, preserving ``[&R]``/``[&U]``."""
    return _STRIP_ANNOTATION_RE.sub("", content)


def _strip_embedded_hilights(content: str) -> str:
    """Remove ``[&!hilight=...]`` comments embedded in the tree text."""
    return _EMBEDDED_HILIGHT_RE.sub("", content)


def _strip_embedded_collapses(content: str) -> str:
    """Remove embedded ``[&!collapse=...]`` / ``[&!cartoon=...]`` comments."""
    return _EMBEDDED_CARTOON_RE.sub("", _EMBEDDED_COLLAPSE_RE.sub("", content))


# --------------------------------------------------------------------------- #
# shared export pipeline
# --------------------------------------------------------------------------- #
def _clade_export(
    ctx: Context,
    *,
    content: str,
    node_format: str,
    sr: Any,
    op_args: List[str],
    records: List[Dict[str, Any]],
    run_name: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    run = require_run(ctx)
    in_path = run.run_dir / "input.tre"
    in_path.write_text(content, encoding="utf-8")
    base = f"{run_name or 'output'}.nex"
    out = run.file_path(base)
    sr.styler.export(str(out), include_taxa_block=True)
    artifact = nexus_artifact(run.register(out))

    cmd = cli_command.build_figtreekit_command(str(in_path), str(out), op_args)
    summary = tree_summary(sr.styler)
    summary["format"] = node_format
    result: Dict[str, Any] = {
        "ok": True,
        "nexus_file": artifact,
        "cli_command": cmd,
        "config_json": "{}",
        "operations_applied": records,
        "summary": summary,
        "run_dir": run.name,
    }
    if extra:
        result.update(extra)
    return result


def _params_ops_args(
    operations: List[Dict[str, Any]],
    *,
    taxonomy_levels: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    table_sep: Optional[str] = None,
) -> List[str]:
    """CLI argv reflecting the executed clade operations (+ taxonomy context)."""
    return ParamSpec(
        operations=operations,
        taxonomy_levels=taxonomy_levels,
        taxonomy_mapping_file=taxonomy_mapping_file,
        table_sep=table_sep,
    ).to_cli_args()


# --------------------------------------------------------------------------- #
# T13 highlight_clade
# --------------------------------------------------------------------------- #
@tool("highlight_clade")
def highlight_clade(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    highlights: Optional[List[Dict[str, Any]]] = None,
    clear_existing: bool = False,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Add FigTree hilight annotations (background bands) to one or more clades.

    Args:
        highlights: [{"taxa": ["A","B"], "color": "#804548", "width": 1.0,
                     "offset": 0}] entries.  ``offset`` must be an integer
                     (the CLI parses ``--highlight`` offsets with ``int()``).
        clear_existing: Clear existing highlights before applying — including
                        ``[&!hilight=...]`` comments already embedded in the
                        tree text (not just pending annotations).
    """
    app = get_app(ctx)
    _require(ctx, highlights, "highlights")
    records: List[Dict[str, str]] = []
    ops: List[Dict[str, Any]] = []
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    if clear_existing:
        # Strip embedded hilights before loading: clear_clade_hilights() only
        # clears pending annotations and would leave these untouched.
        content = _strip_embedded_hilights(content)
    sr = make_styler(content, multi_tree="first")
    styler = sr.styler
    if clear_existing:
        styler.clear_clade_hilights()
        records.append({"op": "clear_hilights", "status": "applied"})
    for i, h in enumerate(highlights or []):
        taxa = _check_taxa(h, i, "highlights")
        color = _check_color(h, i, "highlights")
        width = float(h.get("width", 4))
        if width <= 0:
            raise ToolError(
                "invalid_argument",
                f"highlights[{i}].width 必须 > 0，得到 {width}",
                error_key="bad_width",
            )
        raw_offset = h.get("offset", 0)
        if (
            not isinstance(raw_offset, (int, float))
            or isinstance(raw_offset, bool)
            or float(raw_offset) != int(raw_offset)
        ):
            raise ToolError(
                "invalid_argument",
                f"highlights[{i}].offset 必须是整数（CLI 的 --highlight 偏移按 int 解析），"
                f"得到 {raw_offset!r}",
                error_key="bad_offset",
            )
        offset = int(raw_offset)
        try:
            styler.highlight_clade(taxa, color=color, width=width, offset=offset)
            records.append(
                {
                    "op": "highlight",
                    "status": "applied",
                    "taxa_count": str(len(taxa)),
                    "color": color,
                }
            )
            ops.append(
                {"op": "highlight", "taxa": taxa, "color": color, "width": width, "offset": offset}
            )
        except figtreekit.ValidationError as exc:
            records.append(
                {
                    "op": "highlight",
                    "status": "skipped",
                    "reason": str(exc),
                    "taxa_count": str(len(taxa)),
                }
            )
    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(ops),
        records=records,
        run_name=run_name,
        extra={"highlights_applied": sum(1 for r in records if r["status"] == "applied")},
    )


# --------------------------------------------------------------------------- #
# T14 color_clade
# --------------------------------------------------------------------------- #
@tool("color_clade")
def color_clade(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    colors: Optional[List[Dict[str, Any]]] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Color a clade's MRCA branch (``all=false``) or all descendant branches
    (``all=true``).

    Args:
        colors: [{"taxa": ["A","B"], "color": "#2196F3", "all": false}].
    """
    app = get_app(ctx)
    _require(ctx, colors, "colors")
    records: List[Dict[str, str]] = []
    ops: List[Dict[str, Any]] = []
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    sr = make_styler(content, multi_tree="first")
    styler = sr.styler
    for i, c in enumerate(colors or []):
        taxa = _check_taxa(c, i, "colors")
        color = _check_color(c, i, "colors")
        all_branches = bool(c.get("all", False))
        op_name = "color_all" if all_branches else "color"
        try:
            if all_branches:
                styler.set_clade_color_all(taxa, color)
            else:
                styler.set_clade_color(taxa, color)
            records.append(
                {"op": op_name, "status": "applied", "taxa_count": str(len(taxa)), "color": color}
            )
            ops.append({"op": op_name, "taxa": taxa, "color": color})
        except figtreekit.ValidationError as exc:
            records.append({"op": op_name, "status": "skipped", "reason": str(exc)})
    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(ops),
        records=records,
        run_name=run_name,
        extra={"colors_applied": sum(1 for r in records if r["status"] == "applied")},
    )


# --------------------------------------------------------------------------- #
# T15 set_clade_font
# --------------------------------------------------------------------------- #
@tool("set_clade_font")
def set_clade_font(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    fonts: Optional[List[Dict[str, Any]]] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Set font name/style/size for a clade's tip labels.

    Args:
        fonts: [{"taxa": ["A"], "font_name": "Arial", "font_style": 1,
                 "font_size": 14}]; font_style 0 plain / 1 bold / 2 italic /
                 3 bold-italic.
    """
    app = get_app(ctx)
    _require(ctx, fonts, "fonts")
    records: List[Dict[str, str]] = []
    ops: List[Dict[str, Any]] = []
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    sr = make_styler(content, multi_tree="first")
    styler = sr.styler
    for i, f in enumerate(fonts or []):
        taxa = _check_taxa(f, i, "fonts")
        fstyle = int(f.get("font_style", 0))
        fsize = int(f.get("font_size", 12))
        fname = str(f.get("font_name", "Arial"))
        if fstyle not in (0, 1, 2, 3) or fsize <= 0:
            raise ToolError(
                "invalid_argument",
                f"fonts[{i}]: font_style 0-3 且 font_size > 0",
                error_key="bad_font",
            )
        try:
            styler.set_clade_font(taxa, font_name=fname, font_style=fstyle, font_size=fsize)
            records.append({"op": "font", "status": "applied", "taxa_count": str(len(taxa))})
            ops.append(
                {
                    "op": "font",
                    "taxa": taxa,
                    "font_name": fname,
                    "font_style": fstyle,
                    "font_size": fsize,
                }
            )
        except figtreekit.ValidationError as exc:
            records.append({"op": "font", "status": "skipped", "reason": str(exc)})
    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(ops),
        records=records,
        run_name=run_name,
        extra={"fonts_applied": sum(1 for r in records if r["status"] == "applied")},
    )


# --------------------------------------------------------------------------- #
# T16 collapse_clade
# --------------------------------------------------------------------------- #
@tool("collapse_clade")
def collapse_clade(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    collapses: Optional[List[Dict[str, Any]]] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Collapse clades by exact taxon names into ``collapse`` (triangle+label)
    or ``cartoon`` style.

    Args:
        collapses: [{"taxa": ["A","B","C"], "label": "Clade1",
                     "collapse_type": "collapse|cartoon"}].
    """
    app = get_app(ctx)
    _require(ctx, collapses, "collapses")
    records: List[Dict[str, str]] = []
    ops: List[Dict[str, Any]] = []
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    sr = make_styler(content, multi_tree="first")
    styler = sr.styler
    for i, c in enumerate(collapses or []):
        taxa = _check_taxa(c, i, "collapses")
        style = _check_style(c, i, "collapses")
        label = c.get("label")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                styler.collapse_clade(taxa, label=label, collapse_type=style)
            except figtreekit.ValidationError as exc:
                records.append({"op": "collapse", "status": "skipped", "reason": str(exc)})
                continue
        compat = [w for w in caught if issubclass(w.category, figtreekit.CompatibilityWarning)]
        if compat:
            records.append(
                {"op": "collapse", "status": "skipped", "reason": str(compat[0].message)}
            )
            continue
        records.append({"op": "collapse", "status": "applied", "taxa_count": str(len(taxa))})
        spec = {"op": "collapse", "taxa": taxa}
        if label:
            spec["label"] = label
        if style != "collapse":
            spec["collapse_type"] = style
        ops.append(spec)
    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(ops),
        records=records,
        run_name=run_name,
        extra={"collapses_applied": sum(1 for r in records if r["status"] == "applied")},
    )


# --------------------------------------------------------------------------- #
# T17 collapse_group
# --------------------------------------------------------------------------- #
@tool("collapse_group")
def collapse_group(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    groups: Optional[List[Dict[str, Any]]] = None,
    strict: bool = False,
    taxonomy_levels: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Collapse clades by taxonomic group name with a monophyly pre-check
    (supports LUCA / LACA / LBCA / root).

    A group whose lookup fails (unknown name / unresolvable taxonomy) is
    recorded as a per-group ``skipped`` entry and never aborts the whole
    request; ``strict=True`` converts that failure into ``monophyly_error``.

    Args:
        groups: [{"group": "Cyanobacteriota", "label": "...",
                  "collapse_type": "collapse"}].
        strict: Fail with ``monophyly_error`` on a non-monophyletic group.
        taxonomy_levels: Custom rank prefixes (``prefix:rank,...``).
        taxonomy_mapping_file: Optional taxonomy mapping table (whitelisted),
            for trees whose taxonomy is not embedded in tip labels.
    """
    app = get_app(ctx)
    _require(ctx, groups, "groups")
    records: List[Dict[str, str]] = []
    ops: List[Dict[str, Any]] = []
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    mapping = resolve_mapping_file(app, taxonomy_mapping_file)

    with temporary_rank_prefixes(taxonomy_levels):
        sr = make_styler(content, multi_tree="first", taxonomy_mapping_file=mapping)
        styler = sr.styler
        for i, g in enumerate(groups or []):
            grp = g.get("group") if isinstance(g, dict) else None
            if not grp or not isinstance(grp, str):
                raise ToolError(
                    "invalid_argument",
                    f"groups[{i}].group 必须是非空类群名字符串",
                    error_key="bad_group",
                )
            label = g.get("label")
            style = _check_style(g, i, "groups")
            # Monophyly pre-check.  Unknown / unresolvable group names raise
            # ValidationError here — isolate them per group instead of losing
            # earlier successful collapses.
            try:
                check = styler.check_monophyly_by_group(grp)
            except figtreekit.ValidationError as exc:
                if strict:
                    raise ToolError(
                        "monophyly_error",
                        f"strict 模式下无法解析类群 '{grp}'",
                        error_key="collapse_group_failed",
                        error_detail=str(exc),
                    ) from exc
                records.append(
                    {"op": "collapse_group", "group": grp, "status": "skipped", "reason": str(exc)}
                )
                continue
            if not check.get("is_monophyletic"):
                msg = check.get("warning") or f"类群 '{grp}' 非单系，跳过折叠"
                if strict:
                    raise ToolError(
                        "monophyly_error",
                        f"strict 模式下无法折叠非单系类群 '{grp}'",
                        error_key="collapse_non_monophyletic",
                        error_detail=msg,
                    )
                records.append(
                    {"op": "collapse_group", "group": grp, "status": "skipped", "reason": msg}
                )
                continue
            try:
                styler.collapse_by_group(grp, label=label, collapse_type=style)
            except figtreekit.ValidationError as exc:
                if strict:
                    raise ToolError(
                        "monophyly_error",
                        f"strict 模式下折叠类群 '{grp}' 失败：{exc}",
                        error_key="collapse_group_failed",
                        error_detail=str(exc),
                    ) from exc
                records.append(
                    {"op": "collapse_group", "group": grp, "status": "skipped", "reason": str(exc)}
                )
                continue
            resolved = list(check.get("resolved_taxa") or [])
            records.append(
                {
                    "op": "collapse_group",
                    "group": grp,
                    "status": "applied",
                    "taxa_count": str(len(resolved)),
                }
            )
            spec: Dict[str, Any] = {"op": "collapse_group", "group": grp}
            if label:
                spec["label"] = label
            if style != "collapse":
                spec["collapse_type"] = style
            if (label and label != grp) or style != "collapse":
                # --clade carries neither label nor style; give the argv
                # renderer the resolved taxa so it can reproduce the collapse
                # exactly through --collapse-taxa.
                spec["taxa"] = resolved
            ops.append(spec)

    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(
            ops, taxonomy_levels=taxonomy_levels, taxonomy_mapping_file=mapping
        ),
        records=records,
        run_name=run_name,
        extra={"groups_applied": sum(1 for r in records if r["status"] == "applied")},
    )


# --------------------------------------------------------------------------- #
# T18 collapse_rank
# --------------------------------------------------------------------------- #
@tool("collapse_rank")
def collapse_rank(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    rank: Optional[str] = None,
    collapse_style: str = "collapse",
    auto_color_rank: Optional[str] = None,
    strict: bool = False,
    taxonomy_levels: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Collapse all monophyletic groups at a rank (optionally auto-coloring at
    a rank first) — reproduces ``figtreekit --collapse-rank``.

    Args:
        rank: Rank to collapse (class, phylum, ...).
        collapse_style: collapse | cartoon.
        auto_color_rank: Rank for the pre-collapse palette coloring
            (defaults to phylum, matching the CLI).
        strict: Fail when a monophyletic group cannot be collapsed.
        taxonomy_mapping_file: Optional taxonomy mapping table (whitelisted),
            for trees whose taxonomy is not embedded in tip labels.
    """
    app = get_app(ctx)
    rank = rank or "class"
    if rank not in (
        "domain",
        "superphylum",
        "phylum",
        "class",
        "order",
        "family",
        "genus",
        "species",
    ):
        raise ToolError(
            "invalid_argument",
            f"rank 必须是 domain|superphylum|phylum|class|order|family|genus|species，得到 '{rank}'",
            error_key="bad_rank",
        )
    if collapse_style not in ("collapse", "cartoon"):
        raise ToolError(
            "invalid_argument",
            "collapse_style 必须是 collapse|cartoon",
            error_key="bad_collapse_style",
        )

    mapping = resolve_mapping_file(app, taxonomy_mapping_file)
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    with temporary_rank_prefixes(taxonomy_levels):
        sr = make_styler(content, multi_tree="first", taxonomy_mapping_file=mapping)
        styler = sr.styler
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            color_rank = auto_color_rank or "phylum"
            result_color = styler.analyze_taxonomy(rank=color_rank, style_monophyletic=False)
        _ = color_groups_by_result(styler, result_color)
        with warnings.catch_warnings(record=True) as caught2:
            warnings.simplefilter("always")
            result = styler.analyze_taxonomy(rank=rank, style_monophyletic=False)
        records = collapse_monophyletic_groups(
            styler, result, collapse_style=collapse_style, strict=strict
        )
        warn_msgs = [
            str(w.message)
            for w in caught + caught2
            if issubclass(w.category, figtreekit.CompatibilityWarning)
        ]

    records_total = [{"op": "auto_color", "rank": color_rank, "status": "applied"}] + records
    ops = [
        {"op": "auto_color", "rank": color_rank},
        {
            "op": "collapse_rank",
            "rank": rank,
            "collapse_style": collapse_style,
            "auto_color_rank": color_rank,
        },
    ]
    if warn_msgs:
        records_total.append(
            {"op": "warnings", "status": "info", "reason": "；".join(warn_msgs)[:500]}
        )
    extra: Dict[str, Any] = {
        "collapsed_groups": sum(1 for r in records if r["status"] == "applied"),
        "skipped_groups": sum(1 for r in records if r["status"] == "skipped"),
    }
    if warn_msgs:
        extra["warnings"] = warn_msgs
    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(
            ops, taxonomy_levels=taxonomy_levels, taxonomy_mapping_file=mapping
        ),
        records=records_total,
        run_name=run_name,
        extra=extra,
    )


# --------------------------------------------------------------------------- #
# T19 clear_annotations
# --------------------------------------------------------------------------- #
@tool("clear_annotations")
def clear_annotations(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    clear_hilights: bool = True,
    clear_collapses: bool = True,
    strip_annotations: bool = False,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Clear highlight and collapse annotations, including embedded ones.

    Both *pending* annotations and ``[&!hilight=...]`` / ``[&!collapse=...]``
    comments already present in the input tree text are removed before the
    tree is loaded/exported.  Colors and fonts are intentionally NOT part of
    this tool (use ``color_clade`` / ``set_clade_font`` to manage them).

    Args:
        clear_hilights: Clear background highlights (default true).
        clear_collapses: Clear collapses/cartoons (default true).
        strip_annotations: Also strip generic ``[&...]`` annotations from the
            text.  Nexus root markers ``[&R]`` / ``[&U]`` are preserved so
            rooting is unchanged.
    """
    app = get_app(ctx)
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    records: List[Dict[str, str]] = []
    ops: List[Dict[str, Any]] = []
    if strip_annotations:
        # Generic annotations are removed from the materialised input before
        # loading; [&R]/[&U] survive so the exported rooting matches the CLI
        # (which keeps them when not stripping).
        content = _strip_annotations(content)
        records.append({"op": "strip_annotations", "status": "applied"})
    if clear_hilights:
        content = _strip_embedded_hilights(content)
    if clear_collapses:
        content = _strip_embedded_collapses(content)
    sr = make_styler(content, multi_tree="first")
    styler = sr.styler
    if clear_hilights:
        styler.clear_clade_hilights()
        records.append({"op": "clear_hilights", "status": "applied"})
        ops.append({"op": "clear_hilights"})
    if clear_collapses:
        styler.clear_collapses()
        records.append({"op": "clear_collapses", "status": "applied"})
    return _clade_export(
        ctx,
        content=content,
        node_format=node.format,
        sr=sr,
        op_args=_params_ops_args(ops),
        records=records,
        run_name=run_name,
        extra={},
    )


__all__ = [
    "highlight_clade",
    "color_clade",
    "set_clade_font",
    "collapse_clade",
    "collapse_group",
    "collapse_rank",
    "clear_annotations",
]
