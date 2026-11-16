# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Integration tests for clade tools (T13-T19).

Each clade tool mutates the styler through the figtreekit public API and
exports a Nexus into the run dir.  These tests verify the operation records,
the returned artifact, and error envelopes on invalid input.

Group-by-name tools (``collapse_group``) resolve taxonomic group names through
figtreekit's taxonomy parser; synthetic fixtures use ``p__X``-only labels
(matching the real GTDB rank-tag format) so that resolution succeeds.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from figtreekit_mcp._errors import ToolError

from conftest import SMALL_TREE

# p__X-only labels: figtreekit auto-detects the phylum rank tag.
PHY_TREE = "(p__Phy1:1,(p__Phy1:1,p__Phy1:1):1,(p__Phy2:1,(p__Phy2:1,p__Phy3:1):1):1);"

# Format-A embedded taxonomy whose group names keep the leading "_" prefix
# (unique tip names → collapses are actually emitted).
GROUP_TREE = "((A_p__Phy1:1,B_p__Phy1:1):1,(C_p__Phy2:1,D_p__Phy2:1):1);"
EMBEDDED_ANNOTATIONS = (
    "#NEXUS\nbegin trees;\n"
    "  tree t1 = [&R] ((A:1,B:1)[&!hilight={2,0.5,#ff0000}]:1,C:2)"
    "[&!collapse={AB,0.3}];\nend;\n"
)


def _mcp_nexus(res):
    return Path(res["nexus_file"]["absolute"]).read_text(encoding="utf-8")


def _replay_cli(res, tmp_path: Path, name: str = "cli") -> str:
    argv = shlex.split(res["cli_command"])
    argv[0] = sys.executable
    out = tmp_path / f"{name}.nex"
    out_idx = argv.index("-o")
    argv[out_idx + 1] = str(out)
    if "--force" not in argv:
        argv.insert(out_idx + 2, "--force")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return out.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# T13 highlight_clade
# --------------------------------------------------------------------------- #
class TestHighlightClade:
    def test_highlight(self, call, app):
        res = call(
            "highlight_clade",
            tree_content=SMALL_TREE,
            highlights=[{"taxa": ["A", "B"], "color": "#804548"}],
        )
        assert res["ok"] is True
        assert res["highlights_applied"] == 1
        records = res["operations_applied"]
        assert records[0]["op"] == "highlight"
        assert records[0]["status"] == "applied"

    def test_clear_existing(self, call):
        res = call(
            "highlight_clade",
            tree_content=SMALL_TREE,
            highlights=[{"taxa": ["C"]}],
            clear_existing=True,
        )
        assert res["ok"] is True
        ops = [r["op"] for r in res["operations_applied"]]
        assert "clear_hilights" in ops

    def test_missing_highlights(self, call):
        with pytest.raises(ToolError) as ei:
            call("highlight_clade", tree_content=SMALL_TREE)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_highlights"

    def test_bad_taxa(self, call):
        with pytest.raises(ToolError) as ei:
            call("highlight_clade", tree_content=SMALL_TREE, highlights=[{"taxa": "notalist"}])
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_taxa"

    def test_bad_color(self, call):
        with pytest.raises(ToolError) as ei:
            call(
                "highlight_clade",
                tree_content=SMALL_TREE,
                highlights=[{"taxa": ["A"], "color": "red"}],
            )
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_color"

    def test_fractional_offset_rejected(self, call):
        with pytest.raises(ToolError) as ei:
            call(
                "highlight_clade",
                tree_content=SMALL_TREE,
                highlights=[{"taxa": ["A"], "offset": 0.5}],
            )
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_offset"

    def test_clear_existing_removes_embedded_hilights(self, call):
        res = call(
            "highlight_clade",
            tree_content=EMBEDDED_ANNOTATIONS,
            clear_existing=True,
            highlights=[{"taxa": ["C"], "color": "#00FF00"}],
        )
        text = _mcp_nexus(res)
        # The embedded band from the input is gone; the new one is present.
        assert "#ff0000" not in text
        assert "!hilight=" in text
        assert "#00ff00" in text


# --------------------------------------------------------------------------- #
# T14 color_clade
# --------------------------------------------------------------------------- #
class TestColorClade:
    def test_color(self, call):
        res = call(
            "color_clade",
            tree_content=SMALL_TREE,
            colors=[{"taxa": ["A", "B"], "color": "#2196F3"}],
        )
        assert res["ok"] is True
        assert res["colors_applied"] == 1
        assert res["operations_applied"][0]["op"] == "color"

    def test_color_all(self, call):
        res = call(
            "color_clade",
            tree_content=SMALL_TREE,
            colors=[{"taxa": ["C"], "color": "#2196F3", "all": True}],
        )
        assert res["ok"] is True
        assert res["operations_applied"][0]["op"] == "color_all"

    def test_missing_colors(self, call):
        with pytest.raises(ToolError) as ei:
            call("color_clade", tree_content=SMALL_TREE)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_colors"


# --------------------------------------------------------------------------- #
# T15 set_clade_font
# --------------------------------------------------------------------------- #
class TestSetCladeFont:
    def test_font(self, call):
        res = call(
            "set_clade_font",
            tree_content=SMALL_TREE,
            fonts=[{"taxa": ["A"], "font_name": "Arial", "font_style": 1, "font_size": 14}],
        )
        assert res["ok"] is True
        assert res["fonts_applied"] == 1
        assert res["operations_applied"][0]["op"] == "font"

    def test_bad_font(self, call):
        with pytest.raises(ToolError) as ei:
            call(
                "set_clade_font", tree_content=SMALL_TREE, fonts=[{"taxa": ["A"], "font_style": 9}]
            )
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_font"


# --------------------------------------------------------------------------- #
# T16 collapse_clade
# --------------------------------------------------------------------------- #
class TestCollapseClade:
    def test_collapse(self, call):
        res = call(
            "collapse_clade",
            tree_content=SMALL_TREE,
            collapses=[{"taxa": ["A", "B"], "label": "Clade1"}],
        )
        assert res["ok"] is True
        assert res["collapses_applied"] == 1
        assert res["operations_applied"][0]["op"] == "collapse"

    def test_cartoon_style(self, call):
        res = call(
            "collapse_clade",
            tree_content=SMALL_TREE,
            collapses=[{"taxa": ["A", "B"], "collapse_type": "cartoon"}],
        )
        assert res["ok"] is True
        # The cartoon style is reflected in the reproducible cli_command.
        assert "type=cartoon" in res["cli_command"]

    def test_bad_collapse_type(self, call):
        with pytest.raises(ToolError) as ei:
            call(
                "collapse_clade",
                tree_content=SMALL_TREE,
                collapses=[{"taxa": ["A"], "collapse_type": "bogus"}],
            )
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_collapse_type"


# --------------------------------------------------------------------------- #
# T17 collapse_group
# --------------------------------------------------------------------------- #
class TestCollapseGroup:
    def test_collapse_monophyletic_group(self, call):
        res = call("collapse_group", tree_content=PHY_TREE, groups=[{"group": "Phy1"}])
        assert res["ok"] is True
        assert res["groups_applied"] == 1
        assert res["operations_applied"][0]["op"] == "collapse_group"
        assert res["operations_applied"][0]["taxa_count"] == "3"

    def test_bad_group(self, call):
        with pytest.raises(ToolError) as ei:
            call("collapse_group", tree_content=SMALL_TREE, groups=[{"group": ""}])
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_group"

    def test_missing_groups(self, call):
        with pytest.raises(ToolError) as ei:
            call("collapse_group", tree_content=SMALL_TREE)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_groups"

    def test_unknown_group_does_not_abort_others(self, call):
        res = call(
            "collapse_group",
            tree_content=GROUP_TREE,
            groups=[
                {"group": "_Phy1"},
                {"group": "NoSuchGroup"},
                {"group": "_Phy2"},
            ],
        )
        records = res["operations_applied"]
        assert [r["status"] for r in records] == ["applied", "skipped", "applied"]
        assert records[1]["group"] == "NoSuchGroup"
        assert records[1]["reason"]
        assert res["groups_applied"] == 2
        text = _mcp_nexus(res)
        assert "!collapse={_Phy1" in text
        assert "!collapse={_Phy2" in text

    def test_unknown_group_strict_raises_monophyly_error(self, call):
        with pytest.raises(ToolError) as ei:
            call(
                "collapse_group",
                tree_content=GROUP_TREE,
                groups=[{"group": "NoSuchGroup"}],
                strict=True,
            )
        assert ei.value.code == "monophyly_error"

    def test_cli_command_uses_clade(self, call, tmp_path):
        res = call("collapse_group", tree_content=GROUP_TREE, groups=[{"group": "_Phy1"}])
        assert "--clade _Phy1" in res["cli_command"]
        assert "--collapse-taxa" not in res["cli_command"]
        assert _replay_cli(res, tmp_path) == _mcp_nexus(res)

    def test_label_and_type_reproduced_via_collapse_taxa(self, call, tmp_path):
        res = call(
            "collapse_group",
            tree_content=GROUP_TREE,
            groups=[
                {"group": "_Phy1", "label": "X", "collapse_type": "cartoon"},
            ],
        )
        text = _mcp_nexus(res)
        assert "[&!cartoon=" in text
        assert "label=X" in res["cli_command"]
        assert "type=cartoon" in res["cli_command"]
        assert _replay_cli(res, tmp_path) == text

    def test_taxonomy_mapping_file(self, call, app, tmp_path):
        mapping = app.workspace.root / "group_map.tsv"
        mapping.write_text(
            "taxon\tphylum\tclass\n"
            "A\tPhy1\tCls1\nB\tPhy1\tCls1\nC\tPhy1\tCls2\n"
            "D\tPhy2\tCls3\nE\tPhy2\tCls3\nF\tPhy3\tCls4\n",
            encoding="utf-8",
        )
        res = call(
            "collapse_group",
            tree_content="(A:1,(B:1,C:1):1,(D:1,E:1):1,F:1);",
            groups=[{"group": "Cls3"}],
            taxonomy_mapping_file=str(mapping),
        )
        assert res["operations_applied"][0]["status"] == "applied"
        assert res["operations_applied"][0]["taxa_count"] == "2"
        assert "--taxonomy-mapping-file" in res["cli_command"]
        assert _replay_cli(res, tmp_path) == _mcp_nexus(res)


# --------------------------------------------------------------------------- #
# T18 collapse_rank
# --------------------------------------------------------------------------- #
class TestCollapseRank:
    def test_collapse_rank(self, call):
        res = call("collapse_rank", tree_content=PHY_TREE, rank="phylum")
        assert res["ok"] is True
        ops = [r["op"] for r in res["operations_applied"]]
        assert ops[0] == "auto_color"
        assert "collapse_rank" in ops

    def test_bad_rank(self, call):
        with pytest.raises(ToolError) as ei:
            call("collapse_rank", tree_content=SMALL_TREE, rank="bogus")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_rank"

    def test_bad_collapse_style(self, call):
        with pytest.raises(ToolError) as ei:
            call("collapse_rank", tree_content=SMALL_TREE, rank="class", collapse_style="bogus")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_collapse_style"


# --------------------------------------------------------------------------- #
# T19 clear_annotations
# --------------------------------------------------------------------------- #
class TestClearAnnotations:
    def test_clear(self, call):
        res = call("clear_annotations", tree_content=SMALL_TREE)
        assert res["ok"] is True
        ops = [r["op"] for r in res["operations_applied"]]
        assert "clear_hilights" in ops
        assert "clear_collapses" in ops

    def test_strip_annotations(self, call):
        annotated = "((A:1,B:1)[&foo=1]:1,C:2);"
        res = call("clear_annotations", tree_content=annotated, strip_annotations=True)
        assert res["ok"] is True
        assert any(r["op"] == "strip_annotations" for r in res["operations_applied"])

    def test_nothing_to_clear(self, call):
        res = call(
            "clear_annotations",
            tree_content=SMALL_TREE,
            clear_hilights=False,
            clear_collapses=False,
        )
        assert res["ok"] is True
        assert res["operations_applied"] == []

    def test_embedded_annotations_removed(self, call):
        res = call("clear_annotations", tree_content=EMBEDDED_ANNOTATIONS)
        text = _mcp_nexus(res)
        assert "!hilight=" not in text
        assert "!collapse=" not in text
        # Root marker survives so the tree stays rooted.
        assert "[&R]" in text

    def test_strip_annotations_keeps_root_marker(self, call):
        res = call(
            "clear_annotations",
            tree_content="[&R] ((A:1,B:1)[&foo=1]:1,C:2);",
            clear_hilights=False,
            clear_collapses=False,
            strip_annotations=True,
        )
        text = _mcp_nexus(res)
        assert "[&foo=1]" not in text
        assert "[&R]" in text
        # Rooting marker handling matches the CLI on the same input: the
        # exported tree keeps the root marker (at the root suffix).
        assert ":0[&R]" in text

    def test_strip_annotations_matches_cli_rooting(self, call, tmp_path):
        content = "[&R] ((A:1,B:1)[&foo=1]:1,C:2);"
        res = call(
            "clear_annotations",
            tree_content=content,
            clear_hilights=False,
            clear_collapses=False,
            strip_annotations=True,
        )
        # A plain CLI run over the same input also keeps the [&R] root marker.
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        src = probe_dir / "in.tre"
        src.write_text(content, encoding="utf-8")
        out = probe_dir / "out.nex"
        proc = subprocess.run(
            [sys.executable, "-m", "figtreekit", str(src), "-o", str(out), "--force"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr[-1000:]
        cli_tree = [
            line for line in out.read_text(encoding="utf-8").splitlines() if "tree " in line
        ]
        mcp_tree = [line for line in _mcp_nexus(res).splitlines() if "tree " in line]
        assert cli_tree and mcp_tree
        assert "[&R]" in cli_tree[0]
        assert "[&R]" in mcp_tree[0]


# --------------------------------------------------------------------------- #
# Real-data integration
# --------------------------------------------------------------------------- #
class TestRealDataClade:
    def test_collapse_group_gtdb(self, call_app_data, ar53_phylum_tree, gtdb_dir):
        res = call_app_data(
            "collapse_group", tree_file=str(ar53_phylum_tree), groups=[{"group": "Undinarchaeota"}]
        )
        assert res["ok"] is True
        assert res["groups_applied"] == 1

    def test_collapse_rank_gtdb(self, call_app_data, ar53_phylum_tree, gtdb_dir):
        res = call_app_data("collapse_rank", tree_file=str(ar53_phylum_tree), rank="phylum")
        assert res["ok"] is True
