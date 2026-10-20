# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Integration tests for validation tools (T04-T06).

These invoke handlers through the shared ``TOOLS`` registry against synthetic
trees / sequence fixtures and (when present) the real GTDB / showcase data.
"""

from __future__ import annotations

import pytest

from figtreekit_mcp._errors import ToolError

from conftest import (
    SMALL_TREE,
    NEGATIVE_BRANCH_TREE,
    MULTI_TREE_NEXUS,
    TAX_TREE,
    FASTA_DNA,
    FASTQ_DNA,
    CROSS_TREE,
    MISMATCH_FASTA,
)


# --------------------------------------------------------------------------- #
# T04 validate_tree
# --------------------------------------------------------------------------- #
class TestValidateTree:
    def test_valid_newick(self, call):
        res = call("validate_tree", tree_content=SMALL_TREE)
        assert res["ok"] is True
        assert res["valid"] is True
        assert res["format"] == "newick"
        assert res["leaf_count"] == 5
        assert res["node_count"] > res["leaf_count"]
        assert res["tree_count"] == 1
        assert res["errors"] == []

    def test_negative_branch_fails(self, call):
        with pytest.raises(ToolError) as ei:
            call("validate_tree", tree_content=NEGATIVE_BRANCH_TREE)
        assert ei.value.code == "validation_failed"
        assert ei.value.error_key == "validation_errors"

    def test_missing_source_raises(self, call):
        with pytest.raises(ToolError) as ei:
            call("validate_tree")
        assert ei.value.code == "invalid_argument"

    def test_bad_mol_type(self, call):
        with pytest.raises(ToolError) as ei:
            call("validate_tree", tree_content=SMALL_TREE, mol_type="bogus")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_mol_type"

    def test_fasta_dna(self, call):
        res = call("validate_tree", tree_content=FASTA_DNA, mol_type="DNA")
        assert res["ok"] is True
        assert res["format"] == "fasta"
        assert res["sequence_count"] == 2
        assert res["alphabet"] == "DNA"
        assert res["valid"] is True

    def test_fasta_length_mismatch(self, call):
        bad = ">s1\nACGT\n>s2\nACGTACGT\n"
        res = call("validate_tree", tree_content=bad, mol_type="DNA")
        assert res["ok"] is True
        assert res["length_mismatch"] is True

    def test_fastq(self, call):
        res = call("validate_tree", tree_content=FASTQ_DNA, mol_type="DNA")
        assert res["ok"] is True
        assert res["format"] == "fastq"
        assert res["sequence_count"] == 2
        # Internal validation details must never leak into the MCP response.
        assert "_tmp_dv" not in res
        assert not any(key.startswith("_") for key in res)

    def test_file_source(self, call, app, reads_dir):
        p = reads_dir / "t.tre"
        p.write_text(SMALL_TREE, encoding="utf-8")
        res = call("validate_tree", tree_file=str(p))
        assert res["ok"] is True
        assert res["valid"] is True
        assert res["size_bytes"] == p.stat().st_size

    def test_run_dir_assigned(self, call):
        res = call("validate_tree", tree_content=SMALL_TREE)
        assert res["run_dir"].startswith("run_")

    def test_taxonomy_levels_removed_from_validation(self, call):
        # ``taxonomy_levels`` never influenced deep validation (no taxonomy
        # parsing happens there), so it is no longer part of the T04 contract.
        with pytest.raises(TypeError):
            call("validate_tree", tree_content=SMALL_TREE,
                 taxonomy_levels="p:phylum")


# --------------------------------------------------------------------------- #
# T05 summarize_tree
# --------------------------------------------------------------------------- #
class TestSummarizeTree:
    def test_basic_summary(self, call):
        res = call("summarize_tree", tree_content=SMALL_TREE)
        assert res["ok"] is True
        assert res["format"] == "newick"
        assert res["tree_count"] == 1
        stats = res["statistics"]
        assert stats["tips"] == 5
        assert stats["internal_nodes"] >= 1
        assert res["tip_labels_total"] == 5
        assert res["tip_labels_preview"][:5] == ["A", "B", "C", "D", "E"]

    def test_tip_label_limit(self, call):
        res = call("summarize_tree", tree_content=SMALL_TREE, tip_labels_limit=2)
        assert len(res["tip_labels_preview"]) == 2

    def test_include_tip_labels_false(self, call):
        res = call("summarize_tree", tree_content=SMALL_TREE, include_tip_labels=False)
        assert res["tip_labels_preview"] == []

    def test_bad_limit(self, call):
        with pytest.raises(ToolError) as ei:
            call("summarize_tree", tree_content=SMALL_TREE, tip_labels_limit=0)
        assert ei.value.code == "invalid_argument"

    def test_multi_tree_hint_not_error(self, call):
        # Multi-tree without selection → hint, never an error (T05 semantics).
        res = call("summarize_tree", tree_content=MULTI_TREE_NEXUS)
        assert res["ok"] is True
        assert res["tree_count"] == 2
        assert "multi_tree_hint" in res

    def test_multi_tree_explicit_selection(self, call):
        res = call("summarize_tree", tree_content=MULTI_TREE_NEXUS, multi_tree="last")
        assert res["ok"] is True
        assert res["selected_tree"] == 1
        assert res["tree_count"] == 2

    def test_rank_sensitive_tax_tree(self, call):
        # A GTDB-style taxonomy tree should summarise without error.
        res = call("summarize_tree", tree_content=TAX_TREE)
        assert res["ok"] is True
        assert res["tip_labels_total"] == 5

    def test_fully_specified_tree_has_no_missing_branch_lengths(self, call):
        # The root clade has no branch length by definition; it must not be
        # reported as a missing length.
        res = call("summarize_tree", tree_content=SMALL_TREE)
        bl = res["statistics"]["branch_lengths"]
        assert bl["has_missing"] is False
        assert bl["min"] == 1.0
        assert bl["max"] == 3.0
        assert bl["negative"] == 0

    def test_missing_branch_lengths_reported(self, call):
        res = call("summarize_tree", tree_content="((A,B):1,C:2);")
        assert res["statistics"]["branch_lengths"]["has_missing"] is True


# --------------------------------------------------------------------------- #
# T06 cross_validate
# --------------------------------------------------------------------------- #
class TestCrossValidate:
    def test_matching(self, call, reads_dir):
        seq = reads_dir / "seq.fasta"
        seq.write_text(FASTA_DNA, encoding="utf-8")
        res = call("cross_validate", tree_content=CROSS_TREE, sequences_file=str(seq))
        assert res["ok"] is True
        assert res["valid"] is True
        assert res["matched"] == 2
        assert res["tree_only"] == []
        assert res["seq_only"] == []
        assert res["errors"] == []
        assert res["sequences_count"] == 2

    def test_mismatch_strict_fails(self, call, reads_dir):
        seq = reads_dir / "seq.fasta"
        seq.write_text(MISMATCH_FASTA, encoding="utf-8")
        with pytest.raises(ToolError) as ei:
            call("cross_validate", tree_content=CROSS_TREE, sequences_file=str(seq))
        assert ei.value.code == "validation_failed"
        assert ei.value.error_key == "cross_validation_failed"

    def test_mismatch_non_strict_ok(self, call, reads_dir):
        seq = reads_dir / "seq.fasta"
        seq.write_text(MISMATCH_FASTA, encoding="utf-8")
        res = call("cross_validate", tree_content=CROSS_TREE,
                   sequences_file=str(seq), strict=False)
        assert res["ok"] is True
        assert res["valid"] is False
        assert res["matched"] == 0
        assert "other1" in res["seq_only"]

    def test_missing_sequences_file(self, call):
        with pytest.raises(ToolError) as ei:
            call("cross_validate", tree_content=CROSS_TREE)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_sequences_file"

    def test_cross_validate_fastq(self, call, reads_dir):
        seq = reads_dir / "seq.fastq"
        seq.write_text(FASTQ_DNA, encoding="utf-8")
        # FASTQ ids are read1/read2.
        res = call("cross_validate", tree_content="(read1:1,read2:1);",
                   sequences_file=str(seq))
        assert res["ok"] is True
        assert res["matched"] == 2


# --------------------------------------------------------------------------- #
# Real-data integration (skipped when reference data absent)
# --------------------------------------------------------------------------- #
class TestRealData:
    def test_validate_showcase_tree(self, call_app_data, showcase_tree):
        res = call_app_data("validate_tree", tree_file=str(showcase_tree))
        assert res["ok"] is True
        assert res["format"] == "nexus"
        assert res["leaf_count"] == 700

    def test_summarize_showcase_tree(self, call_app_data, showcase_tree):
        res = call_app_data("summarize_tree", tree_file=str(showcase_tree))
        assert res["ok"] is True
        assert res["statistics"]["tips"] == 700
