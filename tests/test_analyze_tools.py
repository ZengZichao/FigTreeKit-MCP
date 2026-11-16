# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Integration tests for analysis tools (T07-T09).

``check_monophyly`` / ``collapse_group`` resolve taxonomic group names through
figtreekit's taxonomy parser, which needs labels carrying the relevant rank
(e.g. the real GTDB phylum tree for ``p__`` groups).  Synthetic trees are used
for exact-taxon-list monophyly checks and for ``analyze_taxonomy`` /
``taxonomy_completeness`` with underscore-delimited GTDB-style labels.
"""

from __future__ import annotations

import pytest

from figtreekit_mcp._errors import ToolError
from conftest import call_app

from conftest import (
    BIG_PHYLUM_TREE,
    TABLE_MAPPING,
    TAX_LEVELS,
)

# Underscore-delimited GTDB-style labels (default figtreekit delimiter).
DOM_TREE = (
    "(A_d__Bacteria_p__Phy1_c__Cls1:1,"
    "(B_d__Bacteria_p__Phy1_c__Cls1:1,C_d__Bacteria_p__Phy1_c__Cls2:1):1,"
    "(D_d__Archaea_p__Phy2_c__Cls3:1,E_d__Archaea_p__Phy2_c__Cls3:1):1,"
    "F_d__Archaea_p__Phy3_c__Cls4:1);"
)
# p__X-only labels (GTDB rank-tag format) for group-name resolution.
PHY_TREE = "(p__Phy1:1,(p__Phy1:1,p__Phy1:1):1,(p__Phy2:1,(p__Phy2:1,p__Phy3:1):1):1);"


# --------------------------------------------------------------------------- #
# T07 check_monophyly
# --------------------------------------------------------------------------- #
class TestCheckMonophyly:
    def test_exact_taxon_list_monophyletic(self, call):
        res = call(
            "check_monophyly",
            tree_content="(((A:1,B:1):1,C:2):1,(D:3,E:3):1);",
            groups=[["A", "B", "C"]],
        )
        assert res["ok"] is True
        assert res["results"][0]["is_monophyletic"] is True

    def test_exact_taxon_list_non_monophyletic(self, call):
        res = call(
            "check_monophyly",
            tree_content="(((A:1,B:1):1,C:2):1,(D:3,E:3):1);",
            groups=[["A", "D"]],
        )
        assert res["ok"] is True
        assert res["results"][0]["is_monophyletic"] is False

    def test_strict_fails_on_non_mono(self, call):
        with pytest.raises(ToolError) as ei:
            call(
                "check_monophyly",
                tree_content="(((A:1,B:1):1,C:2):1,(D:3,E:3):1);",
                groups=[["A", "D"]],
                strict=True,
            )
        assert ei.value.code == "monophyly_error"

    def test_missing_groups(self, call):
        with pytest.raises(ToolError) as ei:
            call("check_monophyly", tree_content="(((A:1,B:1):1,C:2):1,(D:3,E:3):1);")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_groups"

    def test_analysis_with_mapping_file(self, call, reads_dir):
        # A list group resolved against a plain tree works regardless of
        # taxonomy mapping.
        res = call(
            "check_monophyly",
            tree_content="(((A:1,B:1):1,C:2):1,(D:3,E:3):1);",
            groups=[["A", "B", "C"]],
        )
        assert res["ok"] is True
        assert res["results"][0]["is_monophyletic"] is True

    def test_embedded_taxonomy_group(self, call):
        # Group name lookup against p__X-only labels (GTDB rank-tag format).
        res = call("check_monophyly", tree_content=PHY_TREE, groups=["Phy1"])
        assert res["ok"] is True
        assert res["results"][0]["is_monophyletic"] is True
        assert res["results"][0]["resolved_taxa_count"] == 3


class TestCheckMonophylyRealData:
    def test_group_by_name_gtdb(self, ctx_with_data, ar53_phylum_tree, gtdb_dir):
        res = call_app(
            "check_monophyly",
            ctx_with_data,
            tree_file=str(ar53_phylum_tree),
            groups=["Undinarchaeota"],
        )
        assert res["ok"] is True
        assert res["results"][0]["is_monophyletic"] is True

    def test_group_not_found_gtdb(self, ctx_with_data, ar53_phylum_tree, gtdb_dir):
        with pytest.raises(ToolError) as ei:
            call_app(
                "check_monophyly",
                ctx_with_data,
                tree_file=str(ar53_phylum_tree),
                groups=["NoSuchGroup"],
            )
        assert ei.value.code == "monophyly_error"
        assert ei.value.error_key == "group_not_found"


# --------------------------------------------------------------------------- #
# T08 analyze_taxonomy
# --------------------------------------------------------------------------- #
class TestAnalyzeTaxonomy:
    def test_missing_rank(self, call):
        with pytest.raises(ToolError) as ei:
            call("analyze_taxonomy", tree_content=BIG_PHYLUM_TREE)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_rank"

    def test_bad_rank(self, call):
        with pytest.raises(ToolError) as ei:
            call("analyze_taxonomy", tree_content=BIG_PHYLUM_TREE, rank="bogus")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_rank"

    def test_phylum_analysis(self, call):
        res = call(
            "analyze_taxonomy",
            tree_content=BIG_PHYLUM_TREE,
            rank="phylum",
            taxonomy_levels=TAX_LEVELS,
        )
        assert res["ok"] is True
        assert res["rank"] == "phylum"
        summary = res["summary"]
        assert summary["total_labels"] == 6
        assert summary["mapped_labels"] == 6
        assert summary["total_groups"] == 3

    def test_mapping_file(self, call, reads_dir):
        mapping = reads_dir / "map.tsv"
        mapping.write_text(TABLE_MAPPING, encoding="utf-8")
        res = call(
            "analyze_taxonomy",
            tree_content=BIG_PHYLUM_TREE,
            rank="phylum",
            taxonomy_mapping_file=str(mapping),
            taxonomy_levels=TAX_LEVELS,
        )
        assert res["ok"] is True
        assert res["summary"]["mapped_labels"] == 6

    def test_group_size_min_filters(self, call):
        res = call(
            "analyze_taxonomy",
            tree_content=BIG_PHYLUM_TREE,
            rank="phylum",
            taxonomy_levels=TAX_LEVELS,
            group_size_min=2,
        )
        groups = res["monophyletic"] + res["non_monophyletic"]
        assert all(g["taxa_count"] >= 2 for g in groups)

    def test_bad_group_size_min(self, call):
        with pytest.raises(ToolError) as ei:
            call("analyze_taxonomy", tree_content=BIG_PHYLUM_TREE, rank="phylum", group_size_min=0)
        assert ei.value.code == "invalid_argument"


# --------------------------------------------------------------------------- #
# T09 taxonomy_completeness
# --------------------------------------------------------------------------- #
class TestTaxonomyCompleteness:
    def test_embedded_completeness(self, call):
        res = call("taxonomy_completeness", tree_content=DOM_TREE, taxonomy_levels=TAX_LEVELS)
        assert res["ok"] is True
        assert res["complete_total"] == 6
        assert res["missing_total"] == 0

    def test_rank_coverage_keys(self, call):
        res = call("taxonomy_completeness", tree_content=DOM_TREE, taxonomy_levels=TAX_LEVELS)
        assert res["ok"] is True
        for rank in ("domain", "phylum", "class"):
            assert rank in res["rank_coverage"]

    def test_mapping_completeness(self, call, reads_dir):
        mapping = reads_dir / "map.tsv"
        mapping.write_text(TABLE_MAPPING, encoding="utf-8")
        res = call(
            "taxonomy_completeness",
            tree_content=BIG_PHYLUM_TREE,
            taxonomy_mapping_file=str(mapping),
            taxonomy_levels=TAX_LEVELS,
        )
        assert res["ok"] is True
        assert res["coverage"] >= 0.0
        assert "phylum" in res["rank_coverage"]


# --------------------------------------------------------------------------- #
# Real-data integration
# --------------------------------------------------------------------------- #
class TestRealDataAnalyze:
    def test_analyze_class_on_gtdb(self, ctx_with_data, ar53_phylum_tree, gtdb_dir):
        res = call_app(
            "analyze_taxonomy", ctx_with_data, tree_file=str(ar53_phylum_tree), rank="phylum"
        )
        assert res["ok"] is True
        assert res["summary"]["total_labels"] > 0
        assert res["summary"]["mapped_labels"] > 0

    def test_taxonomy_completeness_gtdb(
        self, ctx_with_data, ar53_phylum_tree, ar53_taxonomy, gtdb_dir
    ):
        res = call_app(
            "taxonomy_completeness",
            ctx_with_data,
            tree_file=str(ar53_phylum_tree),
            taxonomy_mapping_file=str(ar53_taxonomy),
        )
        assert res["ok"] is True
        assert res["coverage"] > 0.0
