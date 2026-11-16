# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Style tools: T10 style_tree, T11 apply_config, T12 export_nexus.

``style_tree`` is the core tool: it applies the full FigTreeKit parameter
surface in the CLI's fixed order, delegates to the figtreekit
public API, and returns the exported Nexus plus an equivalent ``cli_command``
and ``config_json`` so results are reproducible byte-for-byte.
"""

from __future__ import annotations

import json
import warnings
from typing import Any, Dict, List, Optional

import figtreekit
from figtreekit import (
    FigTreeStyler,
    LayoutType,
    OrderType,
    RootingType,
    TransformType,
)
from mcp.server.fastmcp import Context

from .._core import (
    StyleResult,
    color_groups_by_result,
    collapse_monophyletic_groups,
    make_styler,
    resolve_tree_source,
    temporary_rank_prefixes,
)
from .._errors import ToolError, ok_envelope
from .._logging import get_logger
from .. import cli_command
from ..params import ParamSpec
from . import (
    get_app,
    nexus_artifact,
    progress,
    require_run,
    resolve_mapping_file,
    tool,
    tree_summary,
)

_log = get_logger()


# --------------------------------------------------------------------------- #
# CLI-equivalent styling application (mirrors figtreekit._cli.apply_cli_args)
# --------------------------------------------------------------------------- #
def apply_mcp_styling(styler: FigTreeStyler, spec: ParamSpec) -> None:
    """Apply a ParamSpec to a styler in CLI order."""
    # --- appearance ---
    if spec.branch_width is not None:
        styler.set_appearance(branch_line_width=spec.branch_width)
    if spec.branch_color_attribute is not None:
        styler.set_appearance(branch_color_attribute=spec.branch_color_attribute)
    if spec.background_color is not None:
        styler.set_appearance(background_color=spec.background_color.lower())
    if spec.foreground_color is not None:
        styler.set_appearance(foreground_color=spec.foreground_color.lower())
    if spec.selection_color is not None:
        styler.set_appearance(selection_color=spec.selection_color.lower())

    # --- layout ---
    if spec.layout is not None:
        styler.set_layout(layout_type=LayoutType[spec.layout.upper()])
    if spec.expansion is not None:
        styler.set_layout(expansion=spec.expansion)
    if spec.zoom is not None:
        styler.set_layout(zoom=spec.zoom)

    # --- trees ---
    if spec.unrooted:
        styler.set_trees(rooting=False)
    if spec.rooted and not spec.unrooted:
        styler.set_trees(rooting=True)
    if spec.rooting_type is not None:
        styler.set_trees(
            rooting=True,
            rooting_type=(
                RootingType.USER_SELECTION if spec.rooting_type == "user" else RootingType.MID_POINT
            ),
        )
    if spec.transform is not None:
        styler.set_trees(
            transform=True,
            transform_type=(
                TransformType.CLADOGRAM
                if spec.transform == "cladogram"
                else TransformType.PHYLOGRAM
            ),
        )
    if spec.order is not None:
        styler.set_trees(
            order=True,
            order_type=(
                OrderType.INCREASING_NODE_DENSITY
                if spec.order == "increasing"
                else OrderType.DECREASING_NODE_DENSITY
            ),
        )

    # --- tip labels ---
    if spec.tip_labels == "show":
        styler.set_tip_labels(is_shown=True)
    elif spec.tip_labels == "hide":
        styler.set_tip_labels(is_shown=False)
    if spec.tip_label_font_name is not None:
        styler.set_tip_labels(font_name=spec.tip_label_font_name)
    if spec.tip_label_font_size is not None:
        styler.set_tip_labels(font_size=spec.tip_label_font_size)
    if spec.tip_label_font_style is not None:
        styler.set_tip_labels(font_style=spec.tip_label_font_style)
    if spec.label_color is not None:
        styler.set_tip_label_colors(spec.label_color.lower())

    # --- node / branch labels ---
    if spec.node_labels == "show":
        styler.set_node_labels(is_shown=True)
    elif spec.node_labels == "hide":
        styler.set_node_labels(is_shown=False)
    if spec.node_display_attribute is not None:
        styler.set_node_labels(display_attribute=spec.node_display_attribute, is_shown=True)
    if spec.branch_labels == "show":
        styler.set_branch_labels(is_shown=True)
    elif spec.branch_labels == "hide":
        styler.set_branch_labels(is_shown=False)
    if spec.branch_display_attribute is not None:
        styler.set_branch_labels(display_attribute=spec.branch_display_attribute, is_shown=True)

    # --- scale bar / axis / scale ---
    if spec.scale_bar == "show":
        styler.set_scale_bar(is_shown=True)
    elif spec.scale_bar == "hide":
        styler.set_scale_bar(is_shown=False)
    if spec.scale_axis == "show":
        styler.set_scale_axis(is_shown=True)
    elif spec.scale_axis == "hide":
        styler.set_scale_axis(is_shown=False)
    if spec.root_age is not None:
        styler.set_scale(root_age=spec.root_age)
    if spec.scale_factor is not None:
        styler.set_scale(scale_factor=spec.scale_factor)

    # --- polar ---
    if spec.polar_angular_range_degrees is not None:
        styler.set_polar_layout(angular_range=spec.polar_angular_range_degrees)
    if spec.polar_root_angle_degrees is not None:
        styler.set_polar_layout(root_angle=spec.polar_root_angle_degrees)

    # --- align tip labels ---
    if spec.align_tip_labels is not None:
        styler.set_align_tip_labels(bool(spec.align_tip_labels))

    # --- radial / rectilinear ---
    if spec.radial_spread is not None:
        styler.set_radial_layout(spread=spec.radial_spread)
    if spec.curvature is not None:
        styler.set_rectilinear_layout(curvature=spec.curvature)
    if spec.root_length is not None:
        styler.set_rectilinear_layout(root_length=spec.root_length)

    # --- legend ---
    if spec.legend == "show":
        styler.set_legend(is_shown=True)
    elif spec.legend == "hide":
        styler.set_legend(is_shown=False)
    if spec.legend_position is not None:
        styler.set_legend(position=spec.legend_position)

    # --- scale-axis extras (CLI --set equivalents) ---
    if spec.scale_axis_reverse is not None:
        styler.set_scale_axis(reverse_axis=bool(spec.scale_axis_reverse))
    if spec.scale_axis_font_size is not None:
        styler.set_scale_axis(font_size=spec.scale_axis_font_size)
    if spec.scale_axis_significant_digits is not None:
        styler.set_scale_axis(significant_digits=spec.scale_axis_significant_digits)

    # --- additional config (applied last, like CLI --set) ---
    if spec.additional_config:
        for key, value in spec.additional_config.items():
            styler.set_custom_param(key, _coerce_value(value))


def _coerce_value(value: Any) -> Any:
    """Match figtreekit CLI ``_coerce_value`` for direct config values."""
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "false"):
            return low == "true"
        if low in ("null", "none"):
            return None
        try:
            if "." in value or "e" in low:
                return float(value)
            return int(value)
        except ValueError:
            return value
    return value


# --------------------------------------------------------------------------- #
# Ordered clade operations
# --------------------------------------------------------------------------- #
def apply_operations(
    styler: FigTreeStyler, operations: List[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """Execute ordered clade operations, returning per-op records."""
    records: List[Dict[str, str]] = []
    for i, op in enumerate(operations):
        name = op.get("op")
        try:
            if name == "highlight":
                styler.highlight_clade(
                    taxa_or_group(op),
                    color=op.get("color", "#804548"),
                    width=float(op.get("width", 4)),
                    offset=int(op.get("offset", 0)),
                )
                records.append(_rec(name, "applied", group=op.get("group")))
            elif name in ("color", "color_all"):
                color = op.get("color", "#999999")
                if name == "color_all":
                    styler.set_clade_color_all(taxa_or_group(op), color)
                else:
                    styler.set_clade_color(taxa_or_group(op), color)
                records.append(_rec(name, "applied", group=op.get("group")))
            elif name == "font":
                styler.set_clade_font(
                    taxa_or_group(op),
                    font_name=op.get("font_name", "Arial"),
                    font_style=int(op.get("font_style", 0)),
                    font_size=int(op.get("font_size", 12)),
                )
                records.append(_rec(name, "applied", group=op.get("group")))
            elif name == "collapse":
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    styler.collapse_clade(
                        taxa_or_group(op),
                        label=op.get("label"),
                        collapse_type=op.get("collapse_type", "collapse"),
                    )
                records.append(_rec_collapse(op, caught))
            elif name == "collapse_group":
                records.append(_collapse_group_op(styler, op))
            elif name == "collapse_rank":
                records.append(_collapse_rank_op(styler, op))
            elif name == "clear_hilights":
                styler.clear_clade_hilights()
                records.append({"op": name, "status": "applied"})
            else:
                records.append(
                    {"op": str(name), "status": "skipped", "reason": f"未知操作（位置 {i}）"}
                )
        except figtreekit.ValidationError as exc:
            records.append(_rec(name, "skipped", group=op.get("group"), reason=str(exc)))
        except Exception as exc:  # noqa: BLE001 - per-op isolation
            records.append(_rec(name, "error", group=op.get("group"), reason=str(exc)))
    return records


def taxa_or_group(op: Dict[str, Any]) -> List[str]:
    taxa = op.get("taxa") or []
    return list(taxa) if isinstance(taxa, (list, tuple)) else [str(taxa)]


def _rec(
    op: str, status: str, *, group: Any = None, reason: str = "", taxa_count: int = 0
) -> Dict[str, str]:
    r: Dict[str, str] = {"op": op, "status": status}
    if group:
        r["group"] = str(group)
    if taxa_count:
        r["taxa_count"] = str(taxa_count)
    if reason:
        r["reason"] = reason
    return r


def _rec_collapse(op: Dict[str, Any], caught: List[Any]) -> Dict[str, str]:
    compat = [w for w in caught if issubclass(w.category, figtreekit.CompatibilityWarning)]
    if compat:
        return _rec("collapse", "skipped", group=op.get("group"), reason=str(compat[0].message))
    return _rec("collapse", "applied", group=op.get("group"), taxa_count=len(taxa_or_group(op)))


def _collapse_group_op(styler: FigTreeStyler, op: Dict[str, Any]) -> Dict[str, str]:
    group = str(op.get("group", ""))
    if not group:
        return _rec("collapse_group", "skipped", reason="缺少 group")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            styler.collapse_by_group(
                group,
                label=op.get("label"),
                collapse_type=op.get("collapse_type", "collapse"),
            )
        compat = [w for w in caught if issubclass(w.category, figtreekit.CompatibilityWarning)]
        if compat:
            return _rec("collapse_group", "skipped", group=group, reason=str(compat[0].message))
    except figtreekit.ValidationError as exc:
        return _rec("collapse_group", "skipped", group=group, reason=str(exc))
    return _rec("collapse_group", "applied", group=group)


def _collapse_rank_op(styler: FigTreeStyler, op: Dict[str, Any]) -> Dict[str, str]:
    rank = str(op.get("rank", "class"))
    ctype = op.get("collapse_style") or op.get("collapse_type") or "collapse"
    acr = op.get("auto_color_rank")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = styler.analyze_taxonomy(rank=rank, style_monophyletic=False)
    if acr:
        _ = color_groups_by_result(styler, result)
    records = collapse_monophyletic_groups(styler, result, collapse_style=ctype, strict=False)
    applied = [r for r in records if r["status"] == "applied"]
    skipped = [r for r in records if r["status"] == "skipped"]
    rec = {"op": "collapse_rank", "rank": rank, "status": "applied" if applied else "noop"}
    rec["applied_count"] = str(len(applied))
    if skipped:
        rec["reason"] = "；".join(f"{r['group']}: {r['reason']}" for r in skipped)[:300]
    del caught
    return rec


# --------------------------------------------------------------------------- #
# Shared style→export pipeline (T10/T11)
# --------------------------------------------------------------------------- #
def _export_with_command(
    ctx: Context,
    sr: StyleResult,
    spec: ParamSpec,
    *,
    run_name: Optional[str],
    base_name: str,
    operations_records: List[Dict[str, str]],
    content: str,
    node_format: str,
    single_tree: bool = False,
    extra_warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Export the styled nexus and assemble cli_command / config_json / summary."""
    run = require_run(ctx)
    # Materialise the input file for reproducibility (content-direct case).
    in_path = run.run_dir / "input.tre"
    in_path.write_text(content, encoding="utf-8")
    in_path_abs = str(in_path)

    out_path = run.file_path(base_name)
    styler = sr.styler
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        styler.export(str(out_path), include_taxa_block=True, single_tree=single_tree)
    for w in caught:
        if issubclass(w.category, figtreekit.CompatibilityWarning):
            _log.debug("export warning: %s", w.message)

    artifact = nexus_artifact(run.register(out_path))
    cmd = cli_command.build_figtreekit_command(in_path_abs, str(out_path), spec.to_cli_args())
    config_json = json.dumps(spec.to_config_dict(), indent=2, ensure_ascii=False)

    summary = tree_summary(styler)
    summary["format"] = node_format
    result = ok_envelope(
        nexus_file=artifact,
        cli_command=cmd,
        config_json=config_json,
        operations_applied=operations_records,
        summary=summary,
        run_dir=run.name,
    )
    if extra_warnings:
        result["warnings"] = list(extra_warnings)
    return result


def _auto_color_and_collapse(
    styler: FigTreeStyler,
    *,
    auto_color_rank: Optional[str],
    collapse_rank: Optional[str],
    collapse_style: str,
) -> List[Dict[str, str]]:
    """Steps 5–6 of the style pipeline (auto-color → rank collapse).

    CLI parity (``figtreekit._cli``):

    * ``--auto-color RANK`` colors every group at *RANK* first;
    * ``--collapse-rank RANK`` then **always** runs its own phylum pass
      (Step 1) — even when an explicit ``--auto-color`` rank was requested —
      and paints each collapsed MRCA with its parent phylum's color
      (Step 3).  Consequently the collapse triangle always uses the phylum
      palette, not the requested auto-color palette.  We therefore build a
      dedicated phylum color context whenever ``collapse_rank`` is set.
    """
    records: List[Dict[str, str]] = []
    if auto_color_rank is not None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = styler.analyze_taxonomy(rank=auto_color_rank, style_monophyletic=False)
        color_groups_by_result(styler, result)
        records.append(
            {
                "op": "auto_color",
                "rank": auto_color_rank,
                "status": "applied",
                "groups": str(
                    len(result.get("monophyletic", {})) + len(result.get("non_monophyletic", {}))
                ),
            }
        )
    if collapse_rank is not None:
        # Step 1 (CLI parity): ALWAYS auto-color by phylum before collapsing,
        # independent of any explicit auto_color_rank requested above.  This
        # is the palette context used for post-coloring the collapse nodes.
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            color_result = styler.analyze_taxonomy(rank="phylum", style_monophyletic=False)
        color_info = color_groups_by_result(styler, color_result)
        # Step 2: collapse at the target rank (never the auto-colour rank).
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            collapse_result = styler.analyze_taxonomy(rank=collapse_rank, style_monophyletic=False)
        phylum_taxa_sets = {name: list(t) for name, t in color_info.get("group_taxa", {}).items()}
        color_map = color_info.get("color_map", {})
        collapse_records = collapse_monophyletic_groups(
            styler,
            collapse_result,
            collapse_style=collapse_style,
            strict=False,
            phylum_taxa_sets=phylum_taxa_sets,
            color_map=color_map,
        )
        records.extend(collapse_records)
    return records


#: Operations that must run *after* the taxonomy auto-color / collapse-rank
#: steps, mirroring the CLI's clade-collapse stage (annotations → auto-color →
#: collapses).
_COLLAPSE_OPS = frozenset({"collapse", "collapse_group", "collapse_rank"})


def split_operations(
    operations: Optional[List[Dict[str, Any]]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split operations into (annotation ops, collapse ops), preserving order."""
    if not operations:
        return [], []
    annotations = [op for op in operations if op.get("op") not in _COLLAPSE_OPS]
    collapses = [op for op in operations if op.get("op") in _COLLAPSE_OPS]
    return annotations, collapses


def _reproducibility_warnings(sr: StyleResult, spec: ParamSpec) -> List[str]:
    """Explicitly flag parameter combinations the CLI cannot reproduce 1:1."""
    warns: List[str] = []
    ops = spec.operations or []
    if sr.tree_count > 1:
        if spec.multi_tree in ("split", "all"):
            warns.append(
                "multi_tree=split/all：CLI 会为每棵树分别输出一个文件，MCP 仅对选中树"
                "样式化并在单个文件中保留全部树，二者输出布局不同。"
            )
        if spec.multi_tree == "random" and spec.seed is None:
            warns.append("multi_tree=random 未提供 seed：重新运行命令会随机选择另一棵树。")
        if spec.tree_index is not None and spec.multi_tree is None:
            warns.append("tree_index 没有对应的 CLI 参数，命令无法按索引重放。")
    has_color = any(op.get("op") == "color" for op in ops)
    has_color_all = any(op.get("op") == "color_all" for op in ops)
    if has_color and has_color_all:
        warns.append(
            "--color-all 是 CLI 全局开关：命令会对所有 --color-clade 生效，"
            "无法同时表达逐条 color 与 color_all。"
        )
    if any(
        op.get("op") == "collapse_group" and (op.get("label") or op.get("collapse_type"))
        for op in ops
    ):
        warns.append(
            "collapse_group 的 label/collapse_type 无 CLI --clade 参数可表达，"
            "命令仅复现类群折叠本身。"
        )
    return warns


# --------------------------------------------------------------------------- #
# T10 style_tree
# --------------------------------------------------------------------------- #
@tool("style_tree")
def style_tree(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    taxonomy_levels: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    table_sep: Optional[str] = None,
    taxonomy_delimiter_mode: Optional[str] = None,
    layout: Optional[str] = None,
    expansion: Optional[int] = None,
    zoom: Optional[float] = None,
    rooted: Optional[bool] = None,
    unrooted: Optional[bool] = None,
    rooting_type: Optional[str] = None,
    transform: Optional[str] = None,
    order: Optional[str] = None,
    background_color: Optional[str] = None,
    foreground_color: Optional[str] = None,
    selection_color: Optional[str] = None,
    branch_width: Optional[float] = None,
    branch_color_attribute: Optional[str] = None,
    tip_labels: Optional[str] = None,
    tip_label_font_name: Optional[str] = None,
    tip_label_font_size: Optional[int] = None,
    tip_label_font_style: Optional[int] = None,
    label_color: Optional[str] = None,
    align_tip_labels: Optional[bool] = None,
    node_labels: Optional[str] = None,
    node_display_attribute: Optional[str] = None,
    branch_labels: Optional[str] = None,
    branch_display_attribute: Optional[str] = None,
    scale_bar: Optional[str] = None,
    scale_axis: Optional[str] = None,
    scale_axis_reverse: Optional[bool] = None,
    scale_axis_font_size: Optional[int] = None,
    scale_axis_significant_digits: Optional[int] = None,
    root_age: Optional[float] = None,
    scale_factor: Optional[float] = None,
    polar_angular_range_degrees: Optional[float] = None,
    polar_root_angle_degrees: Optional[float] = None,
    radial_spread: Optional[float] = None,
    curvature: Optional[int] = None,
    root_length: Optional[int] = None,
    legend: Optional[str] = None,
    legend_position: Optional[str] = None,
    auto_color_rank: Optional[str] = None,
    collapse_rank: Optional[str] = None,
    collapse_style: str = "collapse",
    operations: Optional[List[Dict[str, Any]]] = None,
    additional_config: Optional[Dict[str, Any]] = None,
    multi_tree: Optional[str] = None,
    tree_index: Optional[int] = None,
    seed: Optional[int] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Style a tree with the full FigTreeKit parameter surface and export a
    FigTree-compatible Nexus file. Returns the file, an
    equivalent ``cli_command`` and a ``config_json`` for byte-for-byte
    reproducibility, plus per-operation records.

    Execution order mirrors the CLI: plain clade annotations (highlight /
    color / font / clear) → taxonomy auto-color / collapse-rank → collapse
    operations.  ``--color-all`` is a global CLI switch, so mixing
    ``color`` and ``color_all`` operations cannot be represented exactly on
    the command line (the command colors every listed clade).

    Multi-tree files: ``multi_tree="first"|"last"|"random"`` style one tree
    and export only that tree (CLI parity); pass ``seed`` to make
    ``random`` reproducible.  ``split``/``all`` cannot be reproduced by a
    single MCP artifact (the CLI writes one file per tree), so the selected
    tree is styled while all trees are preserved, and an explicit
    ``warnings`` entry is returned.

    Args: See the mapped parameter table in docs/tools_reference_EN.md; every argument
    is optional (unspecified = figtreekit default).
    """
    app = get_app(ctx)
    spec = ParamSpec(
        tree_content=tree_content,
        tree_file=tree_file,
        taxonomy_levels=taxonomy_levels,
        taxonomy_mapping_file=taxonomy_mapping_file,
        table_sep=table_sep,
        taxonomy_delimiter_mode=taxonomy_delimiter_mode,
        layout=layout,
        expansion=expansion,
        zoom=zoom,
        rooted=rooted,
        unrooted=unrooted,
        rooting_type=rooting_type,
        transform=transform,
        order=order,
        background_color=background_color,
        foreground_color=foreground_color,
        selection_color=selection_color,
        branch_width=branch_width,
        branch_color_attribute=branch_color_attribute,
        tip_labels=tip_labels,
        tip_label_font_name=tip_label_font_name,
        tip_label_font_size=tip_label_font_size,
        tip_label_font_style=tip_label_font_style,
        label_color=label_color,
        align_tip_labels=align_tip_labels,
        node_labels=node_labels,
        node_display_attribute=node_display_attribute,
        branch_labels=branch_labels,
        branch_display_attribute=branch_display_attribute,
        scale_bar=scale_bar,
        scale_axis=scale_axis,
        scale_axis_reverse=scale_axis_reverse,
        scale_axis_font_size=scale_axis_font_size,
        scale_axis_significant_digits=scale_axis_significant_digits,
        root_age=root_age,
        scale_factor=scale_factor,
        polar_angular_range_degrees=polar_angular_range_degrees,
        polar_root_angle_degrees=polar_root_angle_degrees,
        radial_spread=radial_spread,
        curvature=curvature,
        root_length=root_length,
        legend=legend,
        legend_position=legend_position,
        auto_color_rank=auto_color_rank,
        collapse_rank=collapse_rank,
        collapse_style=collapse_style,
        operations=operations,
        additional_config=additional_config,
        multi_tree=multi_tree,
        tree_index=tree_index,
        seed=seed,
        run_name=run_name,
    ).validate()

    mapping = resolve_mapping_file(app, spec.taxonomy_mapping_file)
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    # Custom rank prefixes are module-global in figtreekit: keep them active
    # for the whole pipeline (load + taxonomy analysis), not just load.
    with temporary_rank_prefixes(spec.taxonomy_levels):
        sr = make_styler(
            content,
            taxonomy_levels=spec.taxonomy_levels,
            taxonomy_mapping_file=mapping,
            table_sep=spec.table_sep,
            taxonomy_delimiter_mode=spec.taxonomy_delimiter_mode,
            tree_index=spec.tree_index,
            multi_tree=spec.multi_tree,
            seed=spec.seed,
        )

        apply_mcp_styling(sr.styler, spec)

        annotation_ops, collapse_ops = split_operations(spec.operations)
        records: List[Dict[str, str]] = []
        if annotation_ops:
            progress(ctx, 1, 3, f"执行 {len(annotation_ops)} 条 clade 标注操作")
            records += apply_operations(sr.styler, annotation_ops)
        records += _auto_color_and_collapse(
            sr.styler,
            auto_color_rank=spec.auto_color_rank,
            collapse_rank=spec.collapse_rank,
            collapse_style=spec.collapse_style,
        )
        if collapse_ops:
            progress(ctx, 2, 3, f"执行 {len(collapse_ops)} 条折叠操作")
            records += apply_operations(sr.styler, collapse_ops)

        single_tree = sr.tree_count > 1 and spec.multi_tree in ("first", "last", "random")
        base = f"{spec.run_name or 'output'}.nex"
        return _export_with_command(
            ctx,
            sr,
            spec,
            run_name=spec.run_name,
            base_name=base,
            operations_records=records,
            content=content,
            node_format=node.format,
            single_tree=single_tree,
            extra_warnings=_reproducibility_warnings(sr, spec),
        )


# --------------------------------------------------------------------------- #
# T11 apply_config
# --------------------------------------------------------------------------- #
@tool("apply_config")
def apply_config(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    operations: Optional[List[Dict[str, Any]]] = None,
    auto_color_rank: Optional[str] = None,
    collapse_rank: Optional[str] = None,
    collapse_style: str = "collapse",
    taxonomy_levels: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    multi_tree: Optional[str] = None,
    tree_index: Optional[int] = None,
    seed: Optional[int] = None,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a FigTree JSON config (figtree-block keys) plus an ordered
    operations list and export Nexus.  Leaner than style_tree for agent-driven
    advanced tweaks.

    All accepted parameters are validated before execution (``collapse_style``,
    ``multi_tree``, ``auto_color_rank``/``collapse_rank`` and every operation
    field); the execution order is annotations → auto-color/collapse-rank →
    collapse operations, matching the CLI.

    Args:
        config: Any figtree-block key → value mapping (dot-separated keys).
        operations: Ordered clade operations (same schema as style_tree).
        taxonomy_levels: Custom rank prefixes (``prefix:rank,...``); active
            during both loading and taxonomy analysis.
        seed: Reproducible tree selection for ``multi_tree="random"``.
    """
    app = get_app(ctx)
    if config is not None and not isinstance(config, dict):
        raise ToolError(
            "invalid_argument",
            "config 必须是对象（figtree block 键值对）",
            error_key="bad_config_type",
        )
    spec = ParamSpec(
        auto_color_rank=auto_color_rank,
        collapse_rank=collapse_rank,
        collapse_style=collapse_style,
        additional_config=config or None,
        multi_tree=multi_tree,
        tree_index=tree_index,
        seed=seed,
        taxonomy_levels=taxonomy_levels,
        taxonomy_mapping_file=taxonomy_mapping_file,
        operations=operations,
        run_name=run_name,
    ).validate()
    mapping = resolve_mapping_file(app, spec.taxonomy_mapping_file)
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    with temporary_rank_prefixes(spec.taxonomy_levels):
        sr = make_styler(
            content,
            taxonomy_levels=spec.taxonomy_levels,
            taxonomy_mapping_file=mapping,
            tree_index=spec.tree_index,
            multi_tree=spec.multi_tree,
            seed=spec.seed,
        )
        if config:
            sr.styler.apply_dict({k: _coerce_value(v) for k, v in config.items()})

        annotation_ops, collapse_ops = split_operations(spec.operations)
        records: List[Dict[str, str]] = []
        if annotation_ops:
            records += apply_operations(sr.styler, annotation_ops)
        records += _auto_color_and_collapse(
            sr.styler,
            auto_color_rank=spec.auto_color_rank,
            collapse_rank=spec.collapse_rank,
            collapse_style=spec.collapse_style,
        )
        if collapse_ops:
            records += apply_operations(sr.styler, collapse_ops)

        single_tree = sr.tree_count > 1 and spec.multi_tree in ("first", "last", "random")
        base = f"{spec.run_name or 'output'}.nex"
        return _export_with_command(
            ctx,
            sr,
            spec,
            run_name=spec.run_name,
            base_name=base,
            operations_records=records,
            content=content,
            node_format=node.format,
            single_tree=single_tree,
            extra_warnings=_reproducibility_warnings(sr, spec),
        )


# --------------------------------------------------------------------------- #
# T12 export_nexus
# --------------------------------------------------------------------------- #
@tool("export_nexus")
def export_nexus(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    include_taxa_block: bool = True,
    run_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Low-level: load tree content and export a base FigTree-compatible Nexus
    (structural conversion only, Newick → Nexus; no styling).

    Args:
        include_taxa_block: Emit a TAXA block (default true).
        run_name: Optional artifact base name.
    """
    app = get_app(ctx)
    run = require_run(ctx)
    if run_name is not None:
        ParamSpec(run_name=run_name).validate()
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    sr = make_styler(content, multi_tree="first")

    base = f"{run_name or 'output'}.nex"
    out_path = run.file_path(base)
    sr.styler.export(str(out_path), include_taxa_block=include_taxa_block)
    artifact = nexus_artifact(run.register(out_path))

    in_path = run.run_dir / "input.tre"
    in_path.write_text(content, encoding="utf-8")
    cmd = cli_command.build_figtreekit_command(str(in_path), str(out_path), [], force=True)
    summary = tree_summary(sr.styler)
    summary["format"] = node.format
    return ok_envelope(
        nexus_file=artifact,
        cli_command=cmd,
        config_json="{}",
        summary=summary,
        operations_applied=[],
        run_dir=run.name,
    )


__all__ = ["style_tree", "apply_config", "export_nexus", "apply_operations"]
