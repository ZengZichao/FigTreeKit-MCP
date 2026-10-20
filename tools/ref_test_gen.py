#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""API baseline generator for the 6 "golden" parameter sets.

Generates ``.nex`` files with the *independent* figtreekit Python API (raw
``FigTreeStyler`` surface), reproducing the 6 showcase variants:

1. radial     · full expansion
2. polar      · full expansion
3. polar      · class collapse · cartoon
4. polar      · class collapse · collapse
5. rectilinear· phylum collapse · cartoon
6. rectilinear· phylum collapse · collapse

These files are the "API 基准" against which the MCP ``style_tree`` output and
the ``figtreekit`` CLI output are compared (semantically, modulo tree names).

Usage:
    python tools/ref_test_gen.py <input.tree> <taxonomy.tsv> <out_dir>
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import figtreekit
from figtreekit import (
    FigTreeStyler,
    LayoutType,
    OrderType,
    RootingType,
    TransformType,
)

TAXONOMY_LEVELS = "d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus"


@dataclass
class GoldenSet:
    """One golden parameter set (matches the CLI mapping table)."""

    key: str
    layout: str
    collapse_rank: Optional[str] = None
    collapse_style: Optional[str] = None
    angular_range: Optional[int] = None      # polarLayout.angularRange (milli-deg)
    root_angle: Optional[int] = None         # polarLayout.rootAngle (milli-deg)
    scale_axis_reverse: Optional[bool] = None
    scale_axis_font_size: int = 14
    scale_axis_significant_digits: int = 2
    auto_color_rank: str = "phylum"
    tip_labels_hide: bool = True


GOLDEN_SETS: List[GoldenSet] = [
    GoldenSet(key="radial_full", layout="radial"),
    GoldenSet(
        key="polar_full", layout="polar",
        angular_range=180000, root_angle=90000, scale_axis_reverse=False,
    ),
    GoldenSet(
        key="polar_class_cartoon", layout="polar", collapse_rank="class",
        collapse_style="cartoon", angular_range=180000, root_angle=90000,
        scale_axis_reverse=False,
    ),
    GoldenSet(
        key="polar_class_collapse", layout="polar", collapse_rank="class",
        collapse_style="collapse", angular_range=100000, root_angle=50000,
        scale_axis_reverse=False,
    ),
    GoldenSet(
        key="rect_phylum_cartoon", layout="rectilinear", collapse_rank="phylum",
        collapse_style="cartoon", scale_axis_reverse=True,
    ),
    GoldenSet(
        key="rect_phylum_collapse", layout="rectilinear", collapse_rank="phylum",
        collapse_style="collapse", scale_axis_reverse=True,
    ),
]


def build_styler(
    input_tree: str,
    taxonomy_tsv: str,
    gs: GoldenSet,
) -> FigTreeStyler:
    """Build a fully-configured styler for one golden set via the public API."""
    styler = FigTreeStyler(input_tree)

    # taxonomy prefix injection (scoped)
    from figtreekit.taxonomy import extend_rank_prefixes, get_rank_prefixes, set_rank_prefixes

    snapshot = get_rank_prefixes()
    try:
        for part in TAXONOMY_LEVELS.split(","):
            prefix, rank = part.split(":", 1)
            extend_rank_prefixes({prefix: rank})
        styler.configure_taxonomy(mapping_file=taxonomy_tsv)
    finally:
        set_rank_prefixes(snapshot)

    # layout
    styler.set_layout(layout_type=LayoutType[gs.layout.upper()])
    if gs.angular_range is not None:
        # gs.angular_range / gs.root_angle are stored as the raw FigTree slider
        # integers; set_polar_layout expects degrees (CLI parity via _mcp_spec).
        styler.set_polar_layout(angular_range=360 - gs.angular_range / 1000)
    if gs.root_angle is not None:
        styler.set_polar_layout(root_angle=gs.root_angle / 1000 + 180)

    # tip labels hidden
    styler.set_tip_labels(is_shown=not gs.tip_labels_hide)

    # scale axis
    if gs.scale_axis_reverse is not None:
        styler.set_scale_axis(is_shown=True, reverse_axis=gs.scale_axis_reverse,
                              font_size=gs.scale_axis_font_size,
                              significant_digits=gs.scale_axis_significant_digits)
    elif gs.scale_axis_font_size is not None or gs.scale_axis_significant_digits is not None:
        # CLI parity: the golden sets always carry font_size / significant_digits,
        # and the MCP/CLI emit scaleAxis.fontSize / scaleAxis.significantDigits for
        # every set even when reverse/isShown are left unset.
        styler.set_scale_axis(font_size=gs.scale_axis_font_size,
                              significant_digits=gs.scale_axis_significant_digits)

    # taxonomy-aware auto-colour at phylum
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        color_result = styler.analyze_taxonomy(rank=gs.auto_color_rank, style_monophyletic=False)
    phylum_taxa_sets, color_map = _color_groups(styler, color_result)

    # optional rank collapse — CLI parity (figtreekit --collapse-rank):
    # analyse at the collapse rank (never reuse the auto-colour result) and
    # post-colour each collapsed MRCA with its parent phylum's colour.
    if gs.collapse_rank is not None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            collapse_result = styler.analyze_taxonomy(rank=gs.collapse_rank, style_monophyletic=False)
        _collapse_monophyletic(styler, collapse_result, gs.collapse_style or "collapse",
                               phylum_taxa_sets=phylum_taxa_sets, color_map=color_map)

    return styler


def _color_groups(styler: FigTreeStyler, result: Dict[str, Any]) -> "tuple[Dict[str, Any], Dict[str, str]]":
    """Colour every monophyletic/non-monophyletic group; return
    ``(group -> set of taxa, group -> colour)`` for post-collapse painting."""
    mono = result.get("monophyletic", {})
    non_mono = result.get("non_monophyletic", {})
    all_groups = list(mono.keys()) + list(non_mono.keys())
    colors = styler._generate_group_colors(len(all_groups)) if all_groups else []
    color_map = dict(zip(all_groups, colors))
    group_taxa: Dict[str, Any] = {}
    for group_name, entry in mono.items():
        taxa = entry.get("taxa", [])
        if taxa:
            group_taxa[group_name] = set(taxa)
            styler.set_clade_color_all(taxon_names=taxa, color=color_map.get(group_name, "#999999"))
    for group_name, entry in non_mono.items():
        taxa = entry.get("taxa", [])
        if taxa:
            group_taxa[group_name] = set(taxa)
            for taxon in taxa:
                styler.set_clade_color(taxon_names=[taxon], color=color_map.get(group_name, "#999999"))
    return group_taxa, color_map


def _collapse_monophyletic(styler: FigTreeStyler, result: Dict[str, Any], ctype: str,
                           *, phylum_taxa_sets: Optional[Dict[str, Any]] = None,
                           color_map: Optional[Dict[str, str]] = None) -> None:
    """Collapse every monophyletic group (incl. single-taxon), mirroring the
    CLI.  ``phylum_taxa_sets`` / ``color_map`` are accepted for signature
    parity but intentionally NOT used to re-colour collapsed subtrees: the
    CLI/MCP post-colour is a no-op here (branches are already coloured by the
    phylum pass), so re-running ``set_clade_color_all`` would over-colour and
    diverge from the CLI byte-for-byte.
    """
    for group_name, entry in result.get("monophyletic", {}).items():
        taxa = entry.get("taxa", [])
        if not taxa:
            continue
        display = group_name.strip("_")
        label = display if display != group_name else None
        try:
            styler.collapse_by_group(group_name, collapse_type=ctype, label=label)
        except figtreekit.ValidationError:
            continue


def generate_all(
    input_tree: str,
    taxonomy_tsv: str,
    out_dir: str,
    *,
    only: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Generate the API-baseline ``.nex`` files; returns ``{key: path}``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    produced: Dict[str, str] = {}
    for gs in GOLDEN_SETS:
        if only and gs.key not in only:
            continue
        styler = build_styler(input_tree, taxonomy_tsv, gs)
        target = out / f"{gs.key}.nex"
        # Match the CLI/MCP multi-tree selection (first tree only); the
        # showcase Nexus contains several trees.
        styler.export(str(target), include_taxa_block=True, single_tree=True)
        produced[gs.key] = str(target)
    return produced


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3:
        print(__doc__)
        return 2
    input_tree, taxonomy_tsv, out_dir = args[0], args[1], args[2]
    if not Path(input_tree).is_file() or not Path(taxonomy_tsv).is_file():
        print(f"输入文件不存在：{input_tree} / {taxonomy_tsv}", file=sys.stderr)
        return 1
    produced = generate_all(input_tree, taxonomy_tsv, out_dir)
    for key, path in produced.items():
        print(f"generated {key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
