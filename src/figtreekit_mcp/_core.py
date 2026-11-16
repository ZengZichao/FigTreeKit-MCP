# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Core services: tree-source resolution and styler factory.

``resolve_tree_source`` enforces the content/file duality and
runs the anomalous-content scan.  ``make_styler`` loads content,
applies taxonomy configuration and multi-tree selection, producing a
fully-configured :class:`figtreekit.FigTreeStyler` plus metadata used by the
tools to build summaries and provenance.
"""

from __future__ import annotations

import contextlib
import colorsys
import random
import threading
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import figtreekit
from figtreekit import FigTreeStyler
from figtreekit.taxonomy import extend_rank_prefixes, get_rank_prefixes, set_rank_prefixes

from ._errors import ToolError
from ._logging import get_logger
from ._workspace import Workspace

_log = get_logger()


# --------------------------------------------------------------------------- #
# Tree source
# --------------------------------------------------------------------------- #
@dataclass
class TreeNode:
    """Provenance description of where the tree text came from."""

    source: str  # "content" | "file"
    path: Optional[str] = None
    size_bytes: int = 0
    format: str = ""


def detect_format(content: str, filename: str = "") -> str:
    """Best-effort format detection on in-memory content."""
    stripped = content.lstrip()
    if stripped:
        head = stripped[: buffer_length(stripped)].upper()
        if head.startswith("#NEXUS"):
            return "nexus"
        if head.startswith(">"):
            return "fasta"
        if head.startswith("@"):
            return "fastq"
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in (".nex", ".nexus", ".nx"):
            return "nexus"
        if ext in (".fasta", ".fa", ".fas", ".fna", ".faa", ".ffn", ".frn"):
            return "fasta"
        if ext in (".fastq", ".fq"):
            return "fastq"
    if "(" in content and content.rstrip().endswith(";"):
        return "newick"
    return "unknown"


def buffer_length(s: str) -> int:
    return min(len(s), 8192)


def resolve_tree_source(
    tree_content: Optional[str],
    tree_file: Optional[str],
    workspace: Workspace,
) -> tuple[str, TreeNode]:
    """Resolve the tree source into content + provenance.

    Content and file are mutually exclusive and at least one is required;
    content never touches disk.  Both are scanned for anomalous
    content before any parsing happens.
    """
    if tree_content is not None and tree_file is not None:
        raise ToolError(
            "invalid_argument",
            "tree_content 与 tree_file 不能同时提供",
            error_key="mutually_exclusive_source",
        )
    if tree_content is None and tree_file is None:
        raise ToolError(
            "invalid_argument",
            "必须提供 tree_content（内容）或 tree_file（文件路径）之一",
            error_key="missing_tree_source",
        )

    if tree_content is not None:
        workspace.check_content_size(tree_content)
        _scan_anomalous(tree_content, label="tree_content")
        return tree_content, TreeNode(
            source="content",
            size_bytes=len(tree_content.encode("utf-8")),
            format=detect_format(tree_content),
        )

    path = workspace.assert_readable(tree_file)
    workspace.check_file_size(path)
    try:
        content, warns = figtreekit.read_text_with_fallback(str(path), label=path.name)
    except figtreekit.ValidationError as exc:
        raise ToolError(
            "tree_parse_error", f"无法读取树文件：{exc}", error_key="read_failed"
        ) from exc
    for w in warns:
        warnings.warn(w, figtreekit.CompatibilityWarning)
    _scan_anomalous(content, label=path.name)
    return content, TreeNode(
        source="file",
        path=str(path),
        size_bytes=path.stat().st_size,
        format=detect_format(content, path.name),
    )


def _scan_anomalous(content: str, label: str) -> None:
    errors = figtreekit.scan_for_anomalous_content(content, label=label, source="input")
    if errors:
        raise ToolError(
            "anomalous_content",
            "输入包含异常内容（控制字符 / Unicode 双向文本），已拒绝",
            error_key="anomalous_content_found",
            error_detail="\n".join(errors),
            details=[{"level": "CRITICAL", "message": e} for e in errors],
        )


# --------------------------------------------------------------------------- #
# Taxonomy rank-prefix injection (serialised: upstream state is global)
# --------------------------------------------------------------------------- #
# ``figtreekit.taxonomy`` keeps the rank-prefix map in module globals, so even
# a correct snapshot/restore is racy when two requests overlap.  A re-entrant
# lock serialises every taxonomy scope (nested scopes are supported).
_TAXONOMY_LOCK = threading.RLock()


@contextlib.contextmanager
def temporary_rank_prefixes(extra_spec: Optional[str] = None) -> Iterator[None]:
    """Temporarily extend taxonomy rank prefixes, restoring afterwards.

    The lock is held for the whole scope so concurrent requests cannot observe
    each other's prefixes.  ``extra_spec=None`` still locks: another thread may
    be mutating the globals while this caller reads them.
    """
    with _TAXONOMY_LOCK:
        if not extra_spec:
            yield
            return
        snapshot = get_rank_prefixes()
        try:
            mapped = _parse_rank_spec(extra_spec)
            extend_rank_prefixes(mapped)
            yield
        finally:
            set_rank_prefixes(snapshot)


def _parse_rank_spec(spec: str) -> Dict[str, str]:
    """Parse ``"d:domain,sp:superphylum,..."`` into ``{prefix: rank}``."""
    mapping: Dict[str, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ToolError(
                "invalid_argument",
                f"taxonomy_levels 条目缺少冒号分隔符：'{part}'（应为 prefix:rank 形式）",
                error_key="bad_taxonomy_spec",
            )
        prefix, rank = part.split(":", 1)
        prefix = prefix.strip()
        rank = rank.strip()
        if not prefix or not rank:
            raise ToolError(
                "invalid_argument",
                f"taxonomy_levels 条目为空：'{part}'",
                error_key="bad_taxonomy_spec",
            )
        mapping[prefix] = rank
    return mapping


# --------------------------------------------------------------------------- #
# Styler factory
# --------------------------------------------------------------------------- #
@dataclass
class StyleResult:
    """A configured styler plus derived metadata."""

    styler: FigTreeStyler
    tree_content: str
    tree_count: int
    selected_index: int
    taxonomy_config: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def select_tree_index(
    content: str,
    *,
    multi_tree: Optional[str] = None,
    tree_index: Optional[int] = None,
    seed: Optional[int] = None,
) -> tuple[int, int, str]:
    """Decide which tree of a multi-tree Nexus to process.

    Returns ``(tree_count, selected_index, hint)``.  ``multi_tree`` and
    ``tree_index`` follow the CLI semantics: ``first|last|random``
    select one tree; ``all|split`` preserves all; ``ask`` (or unspecified)
    on a multi-tree file raises ``invalid_argument``; single-tree files are
    unaffected.
    """
    if detect_format(content) != "nexus":
        return 1, 0, ""

    probe = FigTreeStyler().load_content(content)
    tree_count = len(probe._all_trees)
    if tree_count <= 1:
        return 1, 0, ""

    hint = (
        f"文件含 {tree_count} 棵树；可用 multi_tree=first|last|random|split|all "
        f"或 tree_index 指定要处理的树。"
    )

    modes = {"first", "last", "random", "split", "all", "ask"}
    if multi_tree not in modes and tree_index is None:
        raise ToolError(
            "invalid_argument",
            f"多树 Nexus 文件（{tree_count} 棵树）必须显式指定 multi_tree 或 tree_index；{hint}",
            error_key="multi_tree_required",
            error_detail=hint,
        )

    if tree_index is not None:
        if (
            not isinstance(tree_index, int)
            or isinstance(tree_index, bool)
            or tree_index < 0
            or tree_index >= tree_count
        ):
            raise ToolError(
                "invalid_argument",
                f"tree_index={tree_index} 超出范围 0..{tree_count - 1}",
                error_key="tree_index_out_of_range",
                error_detail=hint,
            )
        return tree_count, tree_index, hint

    mode = multi_tree or "ask"
    if mode == "first":
        return tree_count, 0, hint
    if mode == "last":
        return tree_count, tree_count - 1, hint
    if mode == "random":
        rng = random.Random(seed) if seed is not None else random
        return tree_count, rng.randrange(tree_count), hint
    if mode in ("split", "all"):
        # Preserve all trees (export keeps every tree; tree_index only shapes
        # the summary statistics shown to the caller).
        selected = tree_index if tree_index is not None else 0
        return tree_count, selected, hint
    # mode == "ask"
    raise ToolError(
        "invalid_argument",
        f"多树 Nexus 文件（{tree_count} 棵树）：按 ask 语义需显式指定 multi_tree 或 tree_index。{hint}",
        error_key="multi_tree_ask",
        error_detail=hint,
    )


def make_styler(
    content: str,
    *,
    taxonomy_levels: Optional[str] = None,
    taxonomy_mapping_file: Optional[str] = None,
    table_sep: Optional[str] = None,
    taxonomy_delimiter_mode: Optional[str] = None,
    taxonomy_source_priority: Optional[str] = None,
    ignore_malformed: Optional[bool] = None,
    tree_index: Optional[int] = None,
    multi_tree: Optional[str] = None,
    seed: Optional[int] = None,
) -> StyleResult:
    """Create a configured :class:`FigTreeStyler` from content.

    ``taxonomy_levels`` is a module-global rank-prefix injection in
    ``figtreekit``; it is always scoped inside ``temporary_rank_prefixes``
    and rolled back after the call (stateless model).  Callers that run
    taxonomy analysis **after** this function returns must re-enter
    :func:`temporary_rank_prefixes` so the custom prefixes are visible during
    analysis as well (see ``tools.style``).

    ``table_sep`` is the taxonomy *mapping file* column delimiter and is
    forwarded to ``configure_taxonomy(file_delimiter=...)``.

    Raises:
        ToolError: parse errors, multi-tree ambiguity, taxonomy conflicts.
    """
    with temporary_rank_prefixes(taxonomy_levels):
        return _make_styler_impl(
            content,
            taxonomy_mapping_file=taxonomy_mapping_file,
            table_sep=table_sep,
            taxonomy_delimiter_mode=taxonomy_delimiter_mode,
            taxonomy_source_priority=taxonomy_source_priority,
            ignore_malformed=ignore_malformed,
            tree_index=tree_index,
            multi_tree=multi_tree,
            seed=seed,
        )


def _make_styler_impl(
    content: str,
    *,
    taxonomy_mapping_file: Optional[str] = None,
    table_sep: Optional[str] = None,
    taxonomy_delimiter_mode: Optional[str] = None,
    taxonomy_source_priority: Optional[str] = None,
    ignore_malformed: Optional[bool] = None,
    tree_index: Optional[int] = None,
    multi_tree: Optional[str] = None,
    seed: Optional[int] = None,
) -> StyleResult:
    tree_count, selected, hint = select_tree_index(
        content, multi_tree=multi_tree, tree_index=tree_index, seed=seed
    )
    styler = FigTreeStyler(tree_index=selected)
    clade_warns: List[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        styler.load_content(content)

    tax_kwargs: Dict[str, Any] = {}
    if taxonomy_delimiter_mode is not None:
        if taxonomy_delimiter_mode not in ("reverse", "greedy", "segment"):
            raise ToolError(
                "invalid_argument",
                f"taxonomy_delimiter_mode 必须是 reverse|greedy|segment，得到 '{taxonomy_delimiter_mode}'",
                error_key="bad_delimiter_mode",
            )
        tax_kwargs["delimiter_mode"] = taxonomy_delimiter_mode

    if table_sep is not None:
        # MCP ``table_sep`` is the *mapping file* column delimiter, i.e. the
        # upstream ``configure_taxonomy(file_delimiter=...)`` argument (the
        # same flag the CLI exposes as ``--table-sep``).  It is NOT the
        # format-B taxonomy-string separator (``taxonomy_table_sep``).
        tax_kwargs["file_delimiter"] = table_sep
    if taxonomy_source_priority is not None:
        if taxonomy_source_priority not in ("embedded", "table"):
            raise ToolError(
                "invalid_argument",
                f"taxonomy_source_priority 必须是 embedded|table，得到 '{taxonomy_source_priority}'",
                error_key="bad_source_priority",
            )
        tax_kwargs["source_priority"] = taxonomy_source_priority
    if ignore_malformed is not None:
        tax_kwargs["ignore_malformed"] = ignore_malformed
    # NOTE: the caller is responsible for whitelist-checking
    # ``taxonomy_mapping_file`` (tool layer, via the workspace) before it
    # reaches configure_taxonomy; we propagate it unchanged here.
    if taxonomy_mapping_file is not None:
        tax_kwargs["mapping_file"] = taxonomy_mapping_file

    if tax_kwargs:
        styler.configure_taxonomy(**tax_kwargs)

    for w in caught:
        if issubclass(w.category, figtreekit.CompatibilityWarning):
            clade_warns.append(str(w.message))

    tree_text = styler.get_tree_content() or content
    return StyleResult(
        styler=styler,
        tree_content=tree_text,
        tree_count=tree_count,
        selected_index=selected,
        taxonomy_config=tax_kwargs,
        warnings=clade_warns + ([hint] if hint and tree_count > 1 else []),
    )


# --------------------------------------------------------------------------- #
# Group-coloring (CLI ``_color_groups_by_result`` equivalence)
# --------------------------------------------------------------------------- #
#: Palette used for taxonomy group colors (identical to the upstream
#: ``FigTreeStyler._generate_group_colors`` predefined list).  Kept locally so
#: the MCP does not depend on a private upstream method.
GROUP_PALETTE = (
    "#E91E63",  # Pink
    "#2196F3",  # Blue
    "#4CAF50",  # Green
    "#FF9800",  # Orange
    "#9C27B0",  # Purple
    "#00BCD4",  # Cyan
    "#795548",  # Brown
    "#607D8B",  # Blue Grey
    "#F44336",  # Red
    "#3F51B5",  # Indigo
)


def group_palette(n: int) -> List[str]:
    """Return *n* deterministic group colors (upstream-compatible).

    For ``n <= 10`` this is the upstream predefined palette; larger counts
    fall back to the same HSV formula the upstream private helper uses, so
    switching away from ``styler._generate_group_colors`` does not change a
    single emitted color.
    """
    if n <= 0:
        return []
    if n <= len(GROUP_PALETTE):
        return list(GROUP_PALETTE[:n])
    colors: List[str] = []
    for i in range(n):
        hue = i / n
        r, g, b = colorsys.hsv_to_rgb(hue, 0.7, 0.9)
        colors.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
    return colors


def color_groups_by_result(
    styler: FigTreeStyler,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Replicate ``figtreekit._cli._color_groups_by_result`` semantics.

    Monophyletic groups are colored across the whole clade
    (``set_clade_color_all``); non-monophyletic groups are colored
    terminal-by-terminal (``set_clade_color``).  Assigned colors are returned
    as ``{group: color}`` for reproducibility reporting.  Group colors come
    from :func:`group_palette`, which is byte-identical to the upstream
    private palette generator for every group count.
    """
    mono = result.get("monophyletic", {})
    non_mono = result.get("non_monophyletic", {})
    all_groups = list(mono.keys()) + list(non_mono.keys())
    colors = group_palette(len(all_groups))
    color_map = dict(zip(all_groups, colors))
    group_taxa: Dict[str, List[str]] = {}

    for group_name, entry in mono.items():
        taxa = entry.get("taxa", [])
        if not taxa:
            continue
        group_taxa[group_name] = list(taxa)
        try:
            styler.set_clade_color_all(taxon_names=taxa, color=color_map.get(group_name, "#999999"))
        except Exception as exc:  # noqa: BLE001 - per-group isolation
            _log.debug("cannot color mono group %r: %s", group_name, exc)

    for group_name, entry in non_mono.items():
        taxa = entry.get("taxa", [])
        if not taxa:
            continue
        group_taxa[group_name] = list(taxa)
        color = color_map.get(group_name, "#999999")
        for taxon in taxa:
            try:
                styler.set_clade_color(taxon_names=[taxon], color=color)
            except Exception as exc:  # noqa: BLE001 - per-taxon isolation
                _log.debug("cannot color taxon %r: %s", taxon, exc)

    return {"color_map": color_map, "group_taxa": group_taxa}


def collapse_monophyletic_groups(
    styler: FigTreeStyler,
    result: Dict[str, Any],
    *,
    collapse_style: str = "collapse",
    strict: bool = False,
    phylum_taxa_sets: Optional[Dict[str, Any]] = None,
    color_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """Collapse every monophyletic group at the analysed rank (CLI parity).

    Semantics match ``figtreekit._cli`` (--collapse-rank): only groups typed
    ``monophyletic`` are collapsed; a non-monophyletic / zero-taxa group emits
    a ``CompatibilityWarning`` and is skipped, unless ``strict`` in which case
    a ``monophyly_error`` envelope is raised.  Labels have leading/trailing
    underscores stripped for FigTree annotation compatibility.

    When ``phylum_taxa_sets`` and ``color_map`` are supplied (the phylum
    auto-color context captured by ``_auto_color_and_collapse``), each
    successfully collapsed group's MRCA is additionally painted with its
    parent phylum's colour — replicating the CLI ``--collapse-rank`` post-color
    step (``figtreekit._cli`` Step 3) so the collapsed triangle inherits the
    palette.
    """
    records: List[Dict[str, str]] = []
    for group_name, entry in result.get("monophyletic", {}).items():
        # CLI parity: figtreekit --collapse-rank attempts collapse_by_group on
        # EVERY monophyletic group, including single-taxon groups (collapse_by_group
        # itself decides whether a single taxon can be collapsed).  We must NOT
        # pre-skip single_taxon entries or the resulting .nex diverges from the CLI
        # by exactly those groups (byte-for-byte parity).
        taxa = entry.get("taxa", [])
        if not taxa:
            continue
        display_label = group_name.strip("_")
        label_arg = display_label if display_label != group_name else None
        fully_applied = False
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                styler.collapse_by_group(group_name, collapse_type=collapse_style, label=label_arg)
                fully_applied = True
            except figtreekit.ValidationError as exc:
                if strict:
                    raise ToolError(
                        "monophyly_error",
                        f"strict 模式下无法折叠类群 '{group_name}'：{exc}",
                        error_key="collapse_strict_failed",
                        error_detail=str(exc),
                    ) from exc
                fully_applied = False
                records.append(
                    {
                        "op": "collapse_rank",
                        "group": group_name,
                        "taxa_count": len(taxa),
                        "status": "skipped",
                        "reason": str(exc),
                    }
                )
            compat = [x for x in caught if issubclass(x.category, figtreekit.CompatibilityWarning)]
            if compat:
                msg = str(compat[0].message)
                if strict:
                    raise ToolError(
                        "monophyly_error",
                        f"strict 模式下类群 '{group_name}' 不满足折叠条件：{msg}",
                        error_key="collapse_strict_failed",
                        error_detail=msg,
                    )
                fully_applied = False
                records.append(
                    {
                        "op": "collapse_rank",
                        "group": group_name,
                        "taxa_count": len(taxa),
                        "status": "skipped",
                        "reason": msg,
                    }
                )
        if fully_applied:
            # CLI parity post-color (figtreekit._cli --collapse-rank Step 3):
            # read the ACTUAL target_taxa that collapse_by_group resolved and
            # paint the MRCA with the parent phylum's colour, so the collapsed
            # triangle inherits the palette.
            if phylum_taxa_sets and color_map and styler._settings._collapses:
                actual_taxa = styler._settings._collapses[-1].target_taxa
                if actual_taxa:
                    parent_phylum = _find_parent_phylum(actual_taxa, phylum_taxa_sets)
                    clade_color = (
                        color_map.get(parent_phylum, "#999999") if parent_phylum else "#999999"
                    )
                    try:
                        styler.set_clade_color_all(taxon_names=actual_taxa, color=clade_color)
                    except Exception:  # noqa: BLE001 - best-effort post-color
                        pass
            records.append(
                {
                    "op": "collapse_rank",
                    "group": group_name,
                    "taxa_count": len(taxa),
                    "status": "applied",
                }
            )
    return records


_ANALYSIS_RANKS = (
    "domain",
    "superphylum",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)


def resolve_group_taxa(styler: FigTreeStyler, group_name: str) -> List[str]:
    """Resolve a group name to tip labels through ``analyze_taxonomy``.

    ``check_monophyly_by_group`` only understands certain label dialects; for
    GTDB-style labels (especially with a superphylum segment) it can fail to
    build the domain hierarchy.  The taxonomy analysis path is more tolerant,
    so use it as a fallback before reporting ``group_not_found``.
    """
    wanted = group_name.strip("_")
    for rank in _ANALYSIS_RANKS:
        try:
            result = styler.analyze_taxonomy(rank=rank, style_monophyletic=False)
        except Exception:  # noqa: BLE001 - rank may be absent
            continue
        for bucket in ("monophyletic", "non_monophyletic"):
            for name, entry in (result.get(bucket) or {}).items():
                if name.strip("_") == wanted:
                    taxa = [t for t in (entry.get("taxa") or []) if t]
                    if taxa:
                        return taxa
    return []


def _find_parent_phylum(actual_taxa: List[str], phylum_taxa_sets: Dict[str, Any]) -> str:
    """Return the phylum whose member set is a superset of ``actual_taxa``.

    Mirrors ``figtreekit._cli`` --collapse-rank Step 3: first exact subset,
    then a fallback to the first phylum that intersects (matches the gold
    standard's "dominant phylum" behaviour).
    """
    actual_set = set(actual_taxa)
    for phylum_name, ptaxa in phylum_taxa_sets.items():
        if actual_set.issubset(set(ptaxa)):
            return phylum_name
    for phylum_name, ptaxa in phylum_taxa_sets.items():
        if actual_set & set(ptaxa):
            return phylum_name
    return ""
