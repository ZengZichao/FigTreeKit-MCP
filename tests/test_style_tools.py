# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Integration tests for style tools (T10-T12).

``style_tree`` is the core tool: it applies the full parameter surface and
exports a Nexus into the run dir, returning a reproducible ``cli_command`` and
``config_json``.  These tests verify the returned envelope, the exported
artifact, and the round-trip reproducibility contract.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from figtreekit_mcp._errors import ToolError

from conftest import SMALL_TREE, MULTI_TREE_NEXUS

# Custom rank prefix: family is only recognised with taxonomy_levels="x:family".
CUSTOM_PREFIX_TREE = (
    "(A_x__Fam1:1,B_x__Fam1:1,(C_x__Fam2:1,D_x__Fam2:1):1,E_x__Fam1:1);"
)
# Embedded taxonomy (format A) with phylum / class ranks.
BIG_PHYLUM_TREE = (
    "(A_p__Phy1_c__Cls1:1,(B_p__Phy1_c__Cls1:1,C_p__Phy1_c__Cls2:1):1,"
    "(D_p__Phy2_c__Cls3:1,E_p__Phy2_c__Cls3:1):1,F_p__Phy3_c__Cls4:1);"
)
# Two clean monophyletic groups (format A, group names include "_").
GROUP_TREE = "((A_p__Phy1:1,B_p__Phy1:1):1,(C_p__Phy2:1,D_p__Phy2:1):1);"
TIPS_TREE = "(A:1,(B:1,C:1):1,(D:1,E:1):1,F:1);"
PIPE_MAPPING = (
    "taxon|phylum|class\n"
    "A|Phy1|Cls1\nB|Phy1|Cls1\nC|Phy1|Cls2\n"
    "D|Phy2|Cls3\nE|Phy2|Cls3\nF|Phy3|Cls4\n"
)


def _mcp_nexus(res):
    """Read the .nex produced by an MCP tool call."""
    return Path(res["nexus_file"]["absolute"]).read_text(encoding="utf-8")


def _replay_cli(res, tmp_path: Path, name: str = "cli") -> str:
    """Run the returned ``cli_command`` and return the replayed .nex text."""
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
# T10 style_tree
# --------------------------------------------------------------------------- #
class TestStyleTree:
    def test_basic_style_and_export(self, call, app):
        res = call("style_tree", tree_content=SMALL_TREE)
        assert res["ok"] is True
        artifact = res["nexus_file"]
        assert artifact["relative"].endswith("output.nex")
        assert artifact["size_bytes"] > 0
        assert res["run_dir"].startswith("run_")

        # The exported file must exist under the workspace root.
        out = app.workspace.root / artifact["relative"]
        assert out.is_file()
        text = out.read_text(encoding="utf-8")
        assert "#NEXUS" in text

    def test_cli_command_reproducible(self, call, app):
        res = call("style_tree", tree_content=SMALL_TREE,
                   layout="rectilinear", tip_labels="show")
        cmd = res["cli_command"]
        # cli_command is a single whitespace-joined string (view-only).
        assert isinstance(cmd, str)
        assert "figtreekit" in cmd
        # The input tree is materialised in the run dir for reproducibility.
        run_dir = app.workspace.root / res["run_dir"]
        assert (run_dir / "input.tre").is_file()
        # INPUT/OUTPUT paths inside the run dir appear in the command.
        assert res["run_dir"] in cmd
        assert "--layout rectilinear" in cmd
        assert "--tip-labels-show" in cmd

    def test_config_json_valid(self, call):
        res = call("style_tree", tree_content=SMALL_TREE,
                   background_color="#ffffff", branch_width=2.0)
        cfg = json.loads(res["config_json"])
        assert cfg["appearance.backgroundColour"].lower() == "#ffffff"
        assert cfg["appearance.branchLineWidth"] == 2.0

    def test_angle_conversion_in_config(self, call):
        # (360-deg)*1000 mapping for angular-range params.
        res = call("style_tree", tree_content=SMALL_TREE,
                   polar_angular_range_degrees=360, polar_root_angle_degrees=180)
        cfg = json.loads(res["config_json"])
        assert cfg["polarLayout.angularRange"] == 0
        assert cfg["polarLayout.rootAngle"] == 0

    def test_operations_applied(self, call):
        res = call("style_tree", tree_content=SMALL_TREE,
                   operations=[{"op": "highlight", "taxa": ["A", "B"]}])
        assert res["ok"] is True
        records = res["operations_applied"]
        assert records[0]["op"] == "highlight"
        assert records[0]["status"] == "applied"

    def test_layout_enum(self, call):
        res = call("style_tree", tree_content=SMALL_TREE, layout="rectilinear")
        assert res["ok"] is True
        assert res["summary"]["layout"] == "rectilinear"

    def test_polar_layout(self, call):
        res = call("style_tree", tree_content=SMALL_TREE, layout="polar")
        assert res["ok"] is True
        assert res["summary"]["layout"] == "polar"

    def test_multi_tree_requires_selection(self, call):
        with pytest.raises(ToolError) as ei:
            call("style_tree", tree_content=MULTI_TREE_NEXUS)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "multi_tree_required"

    def test_multi_tree_selected(self, call):
        res = call("style_tree", tree_content=MULTI_TREE_NEXUS, multi_tree="last")
        assert res["ok"] is True
        assert res["summary"]["tree_count"] == 2

    def test_bad_color(self, call):
        with pytest.raises(ToolError) as ei:
            call("style_tree", tree_content=SMALL_TREE, background_color="notacolor")
        assert ei.value.code in ("invalid_argument",)

    def test_run_name(self, call):
        res = call("style_tree", tree_content=SMALL_TREE, run_name="my_style")
        assert res["nexus_file"]["relative"].endswith("my_style.nex")


# --------------------------------------------------------------------------- #
# CLI parity / reproducibility regressions
# --------------------------------------------------------------------------- #
class TestStyleParity:
    def test_taxonomy_levels_custom_prefix(self, call, tmp_path):
        without = call("style_tree", tree_content=CUSTOM_PREFIX_TREE,
                       auto_color_rank="family")
        # Read before the next call: both calls share one run directory.
        plain_text = _mcp_nexus(without)
        with_levels = call("style_tree", tree_content=CUSTOM_PREFIX_TREE,
                           taxonomy_levels="x:family", auto_color_rank="family")
        text = _mcp_nexus(with_levels)
        assert "[&!color=" not in plain_text
        assert "[&!color=" in text
        assert "--taxonomy-levels x:family" in with_levels["cli_command"]
        # The command replays the custom-prefix pipeline exactly.
        assert _replay_cli(with_levels, tmp_path) == text

    def test_apply_config_taxonomy_levels(self, call):
        plain = call("apply_config", tree_content=CUSTOM_PREFIX_TREE,
                     auto_color_rank="family")
        plain_text = _mcp_nexus(plain)
        res = call("apply_config", tree_content=CUSTOM_PREFIX_TREE,
                   taxonomy_levels="x:family", auto_color_rank="family")
        assert "[&!color=" not in plain_text
        assert "[&!color=#e91e63]" in _mcp_nexus(res)
        assert res["operations_applied"][0]["op"] == "auto_color"

    def test_table_sep_is_mapping_file_delimiter(self, call, app, tmp_path):
        mapping = app.workspace.root / "map.pipe"
        mapping.write_text(PIPE_MAPPING, encoding="utf-8")
        res = call("style_tree", tree_content=TIPS_TREE,
                   taxonomy_mapping_file=str(mapping), table_sep="|",
                   operations=[{"op": "collapse_group", "group": "Cls3"}])
        records = res["operations_applied"]
        assert records[0]["status"] == "applied"
        assert records[0]["group"] == "Cls3"
        text = _mcp_nexus(res)
        assert "!collapse={Cls3" in text
        assert "--table-sep '|'" in res["cli_command"]
        assert _replay_cli(res, tmp_path) == text

    def test_color_all_loses_to_auto_color_like_cli(self, call, tmp_path):
        res = call(
            "style_tree", tree_content=BIG_PHYLUM_TREE,
            auto_color_rank="phylum",
            operations=[{"op": "color_all",
                         "taxa": ["D_p__Phy2_c__Cls3", "E_p__Phy2_c__Cls3"],
                         "color": "#000000"}],
        )
        text = _mcp_nexus(res)
        # CLI order: annotations first, then auto-color → phylum palette wins.
        tree_line = next(l for l in text.splitlines() if "tree " in l)
        assert "#000000" not in tree_line
        assert "D_p__Phy2_c__Cls3:1[&!color=#e91e63]" in text
        ops = [r["op"] for r in res["operations_applied"]]
        assert ops[0] == "color_all"
        assert ops[1] == "auto_color"
        assert _replay_cli(res, tmp_path) == text

    def test_collapse_rank_post_color_uses_phylum_palette(self, call, tmp_path):
        res = call("style_tree", tree_content=BIG_PHYLUM_TREE,
                   auto_color_rank="class", collapse_rank="class")
        text = _mcp_nexus(res)
        # Cls3 receives the phylum (Phy2) palette colour, not the class one.
        assert "Cls3:1[&!collapse={Cls3,0.0},!color=#e91e63]" in text
        assert "Cls3:1[&!collapse={Cls3,0.0},!color=#2196f3]" not in text
        assert _replay_cli(res, tmp_path) == text

    def test_auto_color_non_phylum_rank_palette(self, call, tmp_path):
        res = call("style_tree", tree_content=BIG_PHYLUM_TREE,
                   auto_color_rank="class")
        text = _mcp_nexus(res)
        # 4 class groups → first three palette colours are used.
        for color in ("#e91e63", "#2196f3", "#4caf50"):
            assert color in text
        assert res["operations_applied"][0]["groups"] == "4"
        assert _replay_cli(res, tmp_path) == text

    def test_collapse_warning_recorded_not_error(self, call):
        res = call("style_tree", tree_content=SMALL_TREE,
                   operations=[{"op": "collapse", "taxa": ["A", "C"],
                                "label": "AC"}])
        rec = res["operations_applied"][0]
        assert rec["op"] == "collapse"
        assert rec["status"] == "skipped"
        assert "monophyletic" in rec["reason"].lower()
        assert rec["status"] != "error"

    def test_collapse_group_op_uses_clade_flag(self, call, tmp_path):
        res = call("style_tree", tree_content=GROUP_TREE,
                   operations=[{"op": "collapse_group", "group": "_Phy1"}])
        text = _mcp_nexus(res)
        assert "!collapse={_Phy1" in text
        assert "--clade _Phy1" in res["cli_command"]
        assert "--collapse-taxa" not in res["cli_command"]
        assert _replay_cli(res, tmp_path) == text

    def test_legend_hide_replay(self, call, tmp_path):
        res = call("style_tree", tree_content=CUSTOM_PREFIX_TREE,
                   legend="hide", legend_position="top")
        assert "--legend-hide" not in res["cli_command"]
        assert "--set legend.isShown=false" in res["cli_command"]
        cfg = json.loads(res["config_json"])
        assert cfg["legend.isShown"] is False
        assert cfg["legend.position"] == "Top"
        assert _replay_cli(res, tmp_path) == _mcp_nexus(res)

    def test_fractional_offset_rejected_at_tool_level(self, call):
        with pytest.raises(ToolError) as ei:
            call("style_tree", tree_content=SMALL_TREE,
                 operations=[{"op": "highlight", "taxa": ["A"], "offset": 0.5}])
        assert ei.value.code == "invalid_argument"
        assert "offset" in ei.value.error_detail

    def test_apply_config_validates_accepted_fields(self, call):
        with pytest.raises(ToolError) as ei:
            call("apply_config", tree_content=SMALL_TREE, collapse_style="bogus")
        assert ei.value.code == "invalid_argument"
        with pytest.raises(ToolError) as ei:
            call("apply_config", tree_content=SMALL_TREE, multi_tree="every")
        assert ei.value.code == "invalid_argument"


class TestMultiTreeReproducibility:
    def test_last_exports_only_selected_tree(self, call, tmp_path):
        res = call("style_tree", tree_content=MULTI_TREE_NEXUS, multi_tree="last")
        text = _mcp_nexus(res)
        assert "tree t2" in text
        assert "tree t1" not in text
        assert "--multi-tree last" in res["cli_command"]
        assert _replay_cli(res, tmp_path) == text

    def test_first_exports_only_selected_tree(self, call, tmp_path):
        res = call("style_tree", tree_content=MULTI_TREE_NEXUS, multi_tree="first")
        text = _mcp_nexus(res)
        assert "tree t1" in text
        assert "tree t2" not in text
        assert "--multi-tree first" in res["cli_command"]
        assert _replay_cli(res, tmp_path) == text

    def test_random_with_seed_is_reproducible(self, call, tmp_path):
        res = call("style_tree", tree_content=MULTI_TREE_NEXUS,
                   multi_tree="random", seed=7)
        text = _mcp_nexus(res)
        # random.Random(7).randrange(2) == random.seed(7); randint(0, 1) == 1
        assert "tree t2" in text and "tree t1" not in text
        assert ["--seed", "7"] == res["cli_command"].split()[-2:]
        assert _replay_cli(res, tmp_path) == text

    def test_split_and_all_keep_trees_and_warn(self, call):
        for mode in ("split", "all"):
            res = call("style_tree", tree_content=MULTI_TREE_NEXUS,
                       multi_tree=mode)
            text = _mcp_nexus(res)
            assert "tree t1" in text and "tree t2" in text
            assert any("multi_tree=split/all" in w for w in res["warnings"])


# --------------------------------------------------------------------------- #
# T11 apply_config
# --------------------------------------------------------------------------- #
class TestApplyConfig:
    def test_apply_dict(self, call):
        res = call("apply_config", tree_content=SMALL_TREE,
                   config={"background.color": "#FF0000"})
        assert res["ok"] is True
        cfg = json.loads(res["config_json"])
        assert cfg["background.color"].lower() == "#ff0000"

    def test_bad_config_type(self, call):
        with pytest.raises(ToolError) as ei:
            call("apply_config", tree_content=SMALL_TREE, config="not-a-dict")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_config_type"

    def test_operations_with_config(self, call):
        res = call("apply_config", tree_content=SMALL_TREE,
                   operations=[{"op": "color", "taxa": ["C"], "color": "#2196F3"}])
        assert res["ok"] is True
        records = res["operations_applied"]
        assert any(r["op"] == "color" and r["status"] == "applied" for r in records)


# --------------------------------------------------------------------------- #
# T12 export_nexus
# --------------------------------------------------------------------------- #
class TestExportNexus:
    def test_structural_conversion(self, call):
        res = call("export_nexus", tree_content=SMALL_TREE)
        assert res["ok"] is True
        assert res["nexus_file"]["relative"].endswith("output.nex")
        # No styling → operations_applied is empty.
        assert res["operations_applied"] == []
        assert res["config_json"] == "{}"

    def test_no_taxa_block(self, call, app):
        res = call("export_nexus", tree_content=SMALL_TREE, include_taxa_block=False)
        out = app.workspace.root / res["nexus_file"]["relative"]
        text = out.read_text(encoding="utf-8")
        assert "TAXA" not in text

    def test_run_name(self, call):
        res = call("export_nexus", tree_content=SMALL_TREE, run_name="plain")
        assert res["nexus_file"]["relative"].endswith("plain.nex")


# --------------------------------------------------------------------------- #
# Real-data integration
# --------------------------------------------------------------------------- #
class TestRealDataStyle:
    def test_style_showcase_tree(self, call_app_data, showcase_tree):
        res = call_app_data("style_tree", tree_file=str(showcase_tree),
                            layout="rectilinear", tip_labels="show")
        assert res["ok"] is True
        assert res["summary"]["tips"] == 700

    def test_style_gtdb_phylum(self, call_app_data, ar53_phylum_tree, gtdb_dir):
        res = call_app_data("style_tree", tree_file=str(ar53_phylum_tree),
                            collapse_rank="phylum", collapse_style="collapse")
        assert res["ok"] is True
