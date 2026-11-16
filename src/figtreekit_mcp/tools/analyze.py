# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Analysis tools: T07 check_monophyly, T08 analyze_taxonomy, T09 taxonomy_completeness.

All three delegate to the figtreekit public API (``check_monophyly_by_group``,
``analyze_taxonomy``, ``check_taxonomy_completeness``) so figures-of-merit are
traceable to the core kernel.  ``taxonomy_levels`` rank-prefix injection is
scoped per call and rolled back afterwards (stateless model).
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Union

import figtreekit
from mcp.server.fastmcp import Context

from .._core import (
    make_styler,
    resolve_group_taxa,
    resolve_tree_source,
    temporary_rank_prefixes,
)
from .._errors import ToolError, ok_envelope
from .._logging import get_logger
from . import get_app, require_run, resolve_mapping_file, tool

_log = get_logger()

RANKS = ("domain", "superphylum", "phylum", "class", "order", "family", "genus", "species")
_PREVIEW_LIMIT = 10
_TIP_PREVIEW_LIMIT = 200


def _special_note(group: str) -> Optional[str]:
    spec = figtreekit.SPECIAL_IDENTIFIERS.get(group)
    if not spec:
        return None
    domains = spec.get("domains")
    if domains:
        return f"{group} 解析为全部 {'+'.join(domains)} 末端"
    return f"{group} 解析为整棵树（全部末端）"


def _resolve_groups(styler: Any, groups: List[Union[str, List[str]]]) -> List[Dict[str, Any]]:
    """Resolve each group entry (name or exact taxa list) to a result dict."""
    resolved: List[Dict[str, Any]] = []
    for entry in groups:
        if isinstance(entry, str):
            special = entry in figtreekit.SPECIAL_IDENTIFIERS
            fallback_note = ""
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    res = styler.check_monophyly_by_group(entry)
            except figtreekit.ValidationError as exc:
                # Fallback for label dialects the group resolver cannot parse
                # (e.g. GTDB labels with a superphylum level).
                taxa = resolve_group_taxa(styler, entry)
                if not taxa:
                    raise ToolError(
                        "monophyly_error",
                        f"类群 '{entry}' 无法解析：{exc}",
                        error_key="group_not_found",
                        error_detail=str(exc),
                    ) from exc
                fallback_note = "通过 taxonomy 分析回退解析类群成员"
                try:
                    res = styler.check_monophyly(taxa)
                except figtreekit.ValidationError as exc2:
                    raise ToolError(
                        "monophyly_error",
                        f"类群 '{entry}' 校验失败：{exc2}",
                        error_key="taxa_check_failed",
                        error_detail=str(exc2),
                    ) from exc2
                res["resolved_taxa"] = taxa
                caught = []
            taxa = res.get("resolved_taxa") or []
            warns = [
                str(w.message)
                for w in caught
                if issubclass(w.category, figtreekit.CompatibilityWarning)
            ]
            if res.get("warning"):
                warns.append(str(res["warning"]))
            resolved.append(
                {
                    "group": entry,
                    "is_monophyletic": bool(res.get("is_monophyletic", False)),
                    "resolved_taxa_count": len(taxa),
                    "resolved_taxa_preview": list(taxa)[:_PREVIEW_LIMIT],
                    "special_identifier": special,
                    "warnings": warns,
                    "mrca_terminals": res.get("mrca_terminals") or [],
                    "note": fallback_note or _special_note(entry),
                }
            )
        elif isinstance(entry, list):
            if not entry or not all(isinstance(t, str) for t in entry):
                raise ToolError(
                    "invalid_argument",
                    "groups 中的名单必须是字符串列表",
                    error_key="bad_group_taxa",
                )
            try:
                res = styler.check_monophyly(entry)
            except figtreekit.ValidationError as exc:
                raise ToolError(
                    "monophyly_error",
                    f"名单 {entry} 校验失败：{exc}",
                    error_key="taxa_check_failed",
                    error_detail=str(exc),
                ) from exc
            resolved.append(
                {
                    "group": ", ".join(entry)
                    if len(entry) <= _PREVIEW_LIMIT
                    else f"{len(entry)} taxa",
                    "is_monophyletic": bool(res.get("is_monophyletic", False)),
                    "resolved_taxa_count": len(entry),
                    "resolved_taxa_preview": list(entry)[:_PREVIEW_LIMIT],
                    "special_identifier": False,
                    "warnings": []
                    if res.get("mrca_found")
                    else [f"MRCA 未找到（{len(res.get('extra_taxa', []))} 个末端不在树中）"],
                    "mrca_terminals": res.get("mrca_terminals") or [],
                    "note": None,
                }
            )
        else:
            raise ToolError(
                "invalid_argument",
                "groups 元素必须是类群名字符串或末端名单列表",
                error_key="bad_group_entry",
            )
    return resolved


# --------------------------------------------------------------------------- #
# T07 check_monophyly
# --------------------------------------------------------------------------- #
@tool("check_monophyly")
def check_monophyly(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    groups: Optional[List[Union[str, List[str]]]] = None,
    taxonomy_levels: Optional[str] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """Check whether one or more taxonomic groups are monophyletic.

    Supports special identifiers LUCA / LACA / LBCA / root, and exact taxon
    lists.  ``strict=True`` raises ``monophyly_error`` as soon as any group is
    not monophyletic.

    Args:
        tree_content: Newick/Nexus content.
        tree_file: Path to a tree file inside an allowed read root.
        groups: List of group names (str) or exact taxon lists (list[str]).
        taxonomy_levels: prefix:rank list (e.g. "d:domain,p:phylum").
        strict: Fail on any non-monophyletic group.
    """
    app = get_app(ctx)
    if not groups:
        raise ToolError(
            "invalid_argument",
            "check_monophyly 必须提供 groups（类群名或末端名单）",
            error_key="missing_groups",
        )
    content, _node = resolve_tree_source(tree_content, tree_file, app.workspace)

    with temporary_rank_prefixes(taxonomy_levels):
        sr = make_styler(content, multi_tree="first")
        results = _resolve_groups(sr.styler, groups)

    non_mono = [r for r in results if not r["is_monophyletic"]]
    if strict and non_mono:
        raise ToolError(
            "monophyly_error",
            "strict 模式下存在非单系类群",
            error_key="non_monophyletic_groups",
            error_detail="\n".join(r["group"] for r in non_mono),
            details=[
                {"level": "ERROR", "group": r["group"], "message": "类群非单系"} for r in non_mono
            ],
        )
    notes = [r["note"] for r in results if r.get("note")]
    return ok_envelope(
        results=results,
        notes="；".join(notes) if notes else "",
    )


# --------------------------------------------------------------------------- #
# T08 analyze_taxonomy
# --------------------------------------------------------------------------- #
@tool("analyze_taxonomy")
def analyze_taxonomy(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    rank: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    taxonomy_levels: Optional[str] = None,
    group_size_min: int = 1,
) -> Dict[str, Any]:
    """Analyze monophyly of all groups at a given taxonomic rank.

    Equivalent to ``figtreekit --analyze-taxonomy RANK``.  Requires terminal
    labels carrying taxonomy info, or a whitelisted mapping file.

    Args:
        tree_content: Newick/Nexus content.
        tree_file: Path to a tree file inside an allowed read root.
        rank: Taxonomic rank to analyze (domain..species).
        taxonomy_mapping_file: Optional CSV/TSV mapping (whitelisted).
        taxonomy_levels: prefix:rank list.
        group_size_min: Only report groups with at least this many taxa.
    """
    app = get_app(ctx)
    run = require_run(ctx)
    if rank is None:
        raise ToolError(
            "invalid_argument",
            "analyze_taxonomy 必须提供 rank（domain|superphylum|phylum|class|order|family|genus|species）",
            error_key="missing_rank",
        )
    if rank not in RANKS:
        raise ToolError(
            "invalid_argument",
            f"rank 必须是 {RANKS} 之一，得到 '{rank}'",
            error_key="bad_rank",
        )
    if not isinstance(group_size_min, int) or group_size_min < 1:
        raise ToolError(
            "invalid_argument",
            "group_size_min 必须是 >= 1 的整数",
            error_key="bad_group_size_min",
        )
    mapping = resolve_mapping_file(app, taxonomy_mapping_file)
    content, _node = resolve_tree_source(tree_content, tree_file, app.workspace)

    with temporary_rank_prefixes(taxonomy_levels):
        sr = make_styler(content, taxonomy_mapping_file=mapping, multi_tree="first")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = sr.styler.analyze_taxonomy(rank=rank, style_monophyletic=False)

    warn_list = [
        str(w.message) for w in caught if issubclass(w.category, figtreekit.CompatibilityWarning)
    ]
    summary = result.get("summary", {})

    def _groups(d: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for g, info in sorted(d.items(), key=lambda kv: (-len(kv[1].get("taxa", [])), kv[0])):
            count = len(info.get("taxa", []))
            if count < group_size_min:
                continue
            out.append({"group": g, "taxa_count": count})
        return out

    mono = _groups(result.get("monophyletic", {}))
    non_mono = _groups(result.get("non_monophyletic", {}))
    return ok_envelope(
        rank=rank,
        summary={
            "total_labels": summary.get("total_labels", 0),
            "mapped_labels": summary.get("mapped_labels", 0),
            "unmapped_labels": summary.get("unmapped_labels", 0),
            "total_groups": summary.get("total_groups", 0),
            "single_taxon_groups": summary.get("single_taxon_groups", 0),
            "monophyletic": summary.get("monophyletic", 0),
            "non_monophyletic": summary.get("non_monophyletic", 0),
            "monophyly_rate": round(summary.get("monophyly_rate", 0.0), 1),
        },
        monophyletic=mono,
        non_monophyletic=non_mono,
        unmapped=result.get("unmapped", [])[:_TIP_PREVIEW_LIMIT],
        unmapped_total=len(result.get("unmapped", [])),
        warnings=warn_list,
        run_dir=run.name,
    )


# --------------------------------------------------------------------------- #
# T09 taxonomy_completeness
# --------------------------------------------------------------------------- #
@tool("taxonomy_completeness")
def taxonomy_completeness(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    taxonomy_levels: Optional[str] = None,
) -> Dict[str, Any]:
    """Report taxonomy completeness per rank; list complete/incomplete/missing tips.

    Equivalent to ``figtreekit --check-taxonomy``.  Lists are truncated to the
    first 200 entries; totals are always returned.

    Args:
        tree_content: Newick/Nexus content.
        tree_file: Path to a tree file inside an allowed read root.
        taxonomy_mapping_file: Optional CSV/TSV mapping (whitelisted).
        taxonomy_levels: prefix:rank list.
    """
    app = get_app(ctx)
    mapping = resolve_mapping_file(app, taxonomy_mapping_file)
    content, _node = resolve_tree_source(tree_content, tree_file, app.workspace)

    with temporary_rank_prefixes(taxonomy_levels):
        sr = make_styler(content, taxonomy_mapping_file=mapping, multi_tree="first")
        result = sr.styler.check_taxonomy_completeness(mapping_file=mapping)

    def _trunc(key: str) -> List[str]:
        return list(result.get(key, []))[:_TIP_PREVIEW_LIMIT]

    return ok_envelope(
        coverage=round(float(result.get("coverage", 0.0)), 2),
        complete=_trunc("complete"),
        complete_total=len(result.get("complete", [])),
        incomplete=_trunc("incomplete"),
        incomplete_total=len(result.get("incomplete", [])),
        missing=_trunc("missing"),
        missing_total=len(result.get("missing", [])),
        rank_coverage={k: round(float(v), 2) for k, v in result.get("rank_coverage", {}).items()},
    )


__all__ = ["check_monophyly", "analyze_taxonomy", "taxonomy_completeness"]
