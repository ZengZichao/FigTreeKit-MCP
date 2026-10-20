# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Validation tools: T04 validate_tree, T05 summarize_tree, T06 cross_validate.

Deep-validation semantics mirror ``figtreekit --validate`` but
never write persistent artifacts: any temporary file used for content-direct
validation lives inside the call's ``run_<uuid>`` directory and is removed
before the handler returns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import figtreekit
from mcp.server.fastmcp import Context

from .._core import StyleResult, make_styler, resolve_tree_source
from .._errors import ToolError, ok_envelope
from .._logging import get_logger
from . import TOOLS, get_app, require_run, resolve_mapping_file, tool

_log = get_logger()

_MOL_TYPES = ("DNA", "RNA", "protein")
_TREE_FORMATS = ("newick", "nexus")
_SEQ_FORMATS = ("fasta", "fastq")


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _tip_labels(styler: Any, tree_content: str) -> Dict[str, Any]:
    """Resolve tip labels (with translate-block restoration) + block metadata."""
    labels = list(figtreekit.extract_taxa_from_newick(tree_content))
    translate: Dict[str, Any] = {"used": False, "entries": 0}
    if getattr(styler, "_translate_block", None):
        try:
            mapping = styler._parse_translate_block()  # name -> id
            id_to_name = {v: k for k, v in mapping.items()}
            labels = [id_to_name.get(t, t) for t in labels]
            translate = {"used": True, "entries": len(mapping)}
        except Exception:  # noqa: BLE001 - translate is advisory
            translate = {"used": False, "entries": 0}
    return {"labels": labels, "translate": translate}


def _tree_statistics(styler: Any) -> Dict[str, Any]:
    """Compact statistics from a loaded styler (T05 §2.2)."""
    tree = styler.parse_tree()
    stats: Dict[str, Any] = {
        "tips": 0,
        "internal_nodes": 0,
        "rooted": None,
        "branch_lengths": {"min": None, "max": None, "has_missing": False, "negative": 0},
    }
    if tree is None:
        return stats
    stats["tips"] = len(tree.get_terminals())
    stats["internal_nodes"] = len(tree.get_nonterminals())
    rooted = getattr(tree, "rooted", None)
    stats["rooted"] = bool(rooted) if rooted is not None else None
    bls: List[float] = []
    has_missing = False
    negative = 0
    for clade in tree.find_clades():
        if clade is tree.root:
            # The root has no branch (branch_length is None by definition);
            # counting it would mark every tree as having missing lengths.
            continue
        bl = clade.branch_length
        if bl is None:
            has_missing = True
        else:
            bls.append(float(bl))
            if bl < 0:
                negative += 1
    stats["branch_lengths"] = {
        "min": min(bls) if bls else None,
        "max": max(bls) if bls else None,
        "has_missing": has_missing,
        "negative": negative,
    }
    return stats


def _write_tmp(run: Any, content: str, suffix: str) -> Path:
    """Write validation-only content into the run dir and return its path."""
    path = run.run_dir / f"_mcp_validate_{abs(hash(content)) & 0xFFFFFF:x}{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# T04 validate_tree
# --------------------------------------------------------------------------- #
@tool("validate_tree")
def validate_tree(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    mol_type: Optional[str] = None,
    skip_length_check: bool = False,
) -> Dict[str, Any]:
    """Deep-validate a Newick/Nexus tree or FASTA/FASTQ sequence file.

    Returns structured errors, warnings, format and counts.  Semantics match
    ``figtreekit --validate`` but no persistent artifact is written.

    Args:
        tree_content: Newick/Nexus/FASTA/FASTQ content (direct paste).
        tree_file: Path to a tree/sequence file inside an allowed read root.
        mol_type: Expected alphabet for sequences (DNA|RNA|protein).
        skip_length_check: Skip alignment-length consistency check (FASTA).
    """
    app = get_app(ctx)
    run = require_run(ctx)
    if mol_type is not None and mol_type not in _MOL_TYPES:
        raise ToolError(
            "invalid_argument",
            f"mol_type 必须是 {_MOL_TYPES} 之一，得到 '{mol_type}'",
            error_key="bad_mol_type",
        )

    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    fmt = node.format
    if fmt not in _TREE_FORMATS + _SEQ_FORMATS:
        raise ToolError(
            "invalid_argument",
            f"无法识别的输入格式：'{fmt}'（仅支持 newick/nexus/fasta/fastq）",
            error_key="unsupported_format",
        )

    report = _report_for(content, fmt, label=tree_file or "content", run=run,
                         mol_type=mol_type, skip_length_check=skip_length_check)

    errors = report.pop("_errors", [])
    warnings = report.pop("_warnings", [])
    if errors:
        raise ToolError(
            "validation_failed",
            "输入验证未通过（存在 ERROR/CRITICAL 项）",
            error_key="validation_errors",
            error_detail="\n".join(errors),
            details=[{"level": "ERROR", "message": e} for e in errors],
        )
    return ok_envelope(
        valid=True,
        warnings=warnings,
        errors=[],
        size_bytes=node.size_bytes,
        run_dir=run.name,
        **report,
    )


def _report_for(
    content: str,
    fmt: str,
    *,
    label: str,
    run: Any,
    mol_type: Optional[str],
    skip_length_check: bool,
) -> Dict[str, Any]:
    """Dispatch deep validation by format; returns report keys + _errors/_warnings."""
    report: Dict[str, Any] = {"format": fmt}

    if fmt == "newick":
        dv = figtreekit.deep_validate_newick(content, label=label)
        report.update({
            "format": "newick",
            "leaf_count": dv["leaf_count"],
            "node_count": dv["node_count"],
            "tree_count": content.count(";") or 1,
        })
        report["_errors"] = list(dv["errors"])
        report["_warnings"] = list(dv["warnings"])
        return report

    if fmt == "nexus":
        tmp = _write_tmp(run, content, ".nex")
        try:
            vi = figtreekit.validate_input_file(str(tmp))
            summaries = figtreekit.summarize_nexus_trees(str(tmp))
        finally:
            tmp.unlink(missing_ok=True)
        errs: List[str] = [f"nexus: {e}" for e in vi.get("errors", [])]
        warns: List[str] = [f"nexus: {w}" for w in vi.get("warnings", [])]
        tree_count = len(summaries) or 1
        for ts in summaries:
            if ts.get("has_negative_bl"):
                errs.append(f"tree '{ts.get('name')}' 含负分支长度，FigTree 无法渲染")
        # Cross-tree consistency: all trees should have the same tip count.
        leaf_counts = {ts.get("leaf_count") for ts in summaries if ts.get("leaf_count")}
        if len(leaf_counts) > 1:
            warns.append(
                f"nexus: 树间末端数量不一致 {sorted(leaf_counts)} — 请确认是否代表同一组末端"
            )
        report.update({
            "format": "nexus",
            "leaf_count": summaries[0]["leaf_count"] if summaries else 0,
            "node_count": max(0, 2 * (summaries[0]["leaf_count"] if summaries else 0) - 1),
            "tree_count": tree_count,
        })
        report["_errors"] = errs
        report["_warnings"] = warns
        return report

    # FASTA / FASTQ
    suffix = ".fasta" if fmt == "fasta" else ".fastq"
    tmp = _write_tmp(run, content, suffix)
    try:
        if fmt == "fasta":
            dv = figtreekit.deep_validate_fasta(
                str(tmp), expected_alphabet=mol_type, check_alignment=not skip_length_check
            )
            report.update({
                "format": "fasta",
                "sequence_count": dv["sequence_count"],
                "alphabet": dv["alphabet"],
                "duplicate_ids": dv["duplicate_ids"],
                "length_mismatch": dv["length_mismatch"],
            })
        else:
            dv = figtreekit.deep_validate_fastq(
                str(tmp), expected_alphabet=mol_type
            )
            report.update({
                "format": "fastq",
                "sequence_count": dv["read_count"],
                "alphabet": dv["alphabet"],
                "duplicate_ids": dv["duplicate_ids"],
            })
    finally:
        tmp.unlink(missing_ok=True)

    if mol_type:
        # FastQ validation elevates alphabet violations to errors itself;
        # FASTA keeps alphabet as detection — the CLI-compatible contract is
        # an ERROR when an explicit mol_type contradicts the detected alphabet.
        detected = report.get("alphabet", "unknown")
        if detected not in ("unknown", mol_type):
            report["_errors"] = report.get("_errors", []) + [
                f"fasta: 检测到字母表 '{detected}'，与 mol_type='{mol_type}' 不一致"
            ]
    report["_errors"] = report.get("_errors", []) + list(dv.get("errors", []))
    report["_warnings"] = report.get("_warnings", []) + list(dv.get("warnings", []))
    return report


# --------------------------------------------------------------------------- #
# T05 summarize_tree
# --------------------------------------------------------------------------- #
@tool("summarize_tree")
def summarize_tree(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    include_tip_labels: bool = True,
    tip_labels_limit: int = 100,
    multi_tree: Optional[str] = None,
    tree_index: Optional[int] = None,
) -> Dict[str, Any]:
    """Parse and summarize a tree: format, counts, root state, branch stats.

    Never fails on validation issues (use validate_tree for that); a
    multi-tree file without an explicit selection yields a ``multi_tree_hint``
    instead of an error.

    Args:
        tree_content: Newick/Nexus content.
        tree_file: Path to a tree file inside an allowed read root.
        include_tip_labels: Include the tip-label preview.
        tip_labels_limit: Max number of preview labels (1..10000).
        multi_tree: first|last|random|split|all selection for multi-tree Nexus.
        tree_index: 0-based index into a multi-tree Nexus.
    """
    app = get_app(ctx)
    if not (1 <= tip_labels_limit <= 10000):
        raise ToolError(
            "invalid_argument",
            "tip_labels_limit 必须在 1..10000 之间",
            error_key="bad_tip_labels_limit",
        )
    content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
    if multi_tree is None and tree_index is None:
        # T05 semantics: multi-tree without selection → hint, never an error.
        multi_tree = "first"
    sr: StyleResult = make_styler(content, multi_tree=multi_tree, tree_index=tree_index)

    stats = _tree_statistics(sr.styler)
    tips = _tip_labels(sr.styler, sr.tree_content)
    total = len(tips["labels"])

    result: Dict[str, Any] = {
        "ok": True,
        "format": node.format or "newick",
        "tree_count": sr.tree_count,
        "selected_tree": sr.selected_index,
        "statistics": stats,
        "tip_labels_total": total,
        "tip_labels_preview": (
            tips["labels"][:tip_labels_limit] if include_tip_labels else []
        ),
        "translate_block": tips["translate"],
        "warnings": sr.warnings,
    }
    hint = next((w for w in sr.warnings if "multi_tree" in w.lower() or "棵树" in w), None)
    if sr.tree_count > 1:
        result["multi_tree_hint"] = hint or (
            f"文件含 {sr.tree_count} 棵树；可用 multi_tree=first|last|random|split|all "
            f"或 tree_index 指定。"
        )
    return result


# --------------------------------------------------------------------------- #
# T06 cross_validate
# --------------------------------------------------------------------------- #
@tool("cross_validate")
def cross_validate(
    ctx: Context,
    tree_content: Optional[str] = None,
    tree_file: Optional[str] = None,
    sequences_file: Optional[str] = None,
    strict: bool = True,
    low_memory: bool = False,
) -> Dict[str, Any]:
    """Cross-validate tree tip labels against sequence IDs (FASTA/FASTQ).

    Args:
        tree_content: Newick/Nexus content.
        tree_file: Path to a tree file inside an allowed read root.
        sequences_file: Path to the sequence file (must be whitelisted).
        strict: Raise ``validation_failed`` on any mismatch (default true).
        low_memory: Accepted for figtreekit parity; IDs are always read lazily.
    """
    app = get_app(ctx)
    if not sequences_file:
        raise ToolError(
            "invalid_argument",
            "cross_validate 必须提供 sequences_file",
            error_key="missing_sequences_file",
        )
    seq_path = resolve_mapping_file(app, sequences_file)
    content, _node = resolve_tree_source(tree_content, tree_file, app.workspace)
    sr = make_styler(content, multi_tree="first")

    tips = _tip_labels(sr.styler, sr.tree_content)
    labels = tips["labels"]
    if not labels:
        raise ToolError(
            "tree_parse_error",
            "无法从树中提取末端标签（translating block 解析失败或树为空）",
            error_key="no_tip_labels",
        )

    try:
        seq_ids = list(figtreekit.extract_sequence_ids(str(seq_path)))
    except (OSError, ValueError) as exc:
        raise ToolError(
            "tree_parse_error",
            f"无法读取序列文件：{exc}",
            error_key="seq_read_failed",
            error_detail=str(exc),
        ) from exc

    result = figtreekit.cross_validate_tree_sequence(
        labels, seq_ids, label=Path(seq_path).name
    )
    errors: List[str] = result.get("errors", [])
    if strict and errors:
        raise ToolError(
            "validation_failed",
            "树末端标签与序列 ID 交叉验证未通过",
            error_key="cross_validation_failed",
            error_detail="\n".join(errors),
            details=[{"level": "ERROR", "message": e} for e in errors],
        )
    return ok_envelope(
        valid=not errors,
        matched=result.get("matched", 0),
        tree_only=result.get("only_in_tree", []),
        seq_only=result.get("only_in_sequences", []),
        errors=errors,
        warnings=result.get("warnings", []),
        sequences_count=len(seq_ids),
    )


__all__ = ["validate_tree", "summarize_tree", "cross_validate"]
