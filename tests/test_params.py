# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Unit tests for ``ParamSpec`` validation and CLI/config mapping.

Each ``to_cli_args`` / ``to_config_dict`` assertion follows the CLI
mapping table, including the angular conversions ``(360-deg)*1000`` and
``(deg-180)*1000`` for the stored polar layout values.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from figtreekit_mcp._errors import ERROR_CODES, ToolError
from figtreekit_mcp.params import (
    COLLAPSE_STYLES,
    LAYOUTS,
    MULTI_TREE_MODES,
    ORDERS,
    ROOTING_TYPES,
    TRANSFORMS,
    FONT_STYLE_NAMES,
    ParamSpec,
)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_default_is_valid(self) -> None:
        assert ParamSpec().validate() is not None

    def test_layout_enum(self) -> None:
        with pytest.raises(ToolError) as ei:
            ParamSpec(layout="tree").validate()
        assert ei.value.code == "invalid_argument"
        assert "layout" in ei.value.error_detail
        for good in LAYOUTS:
            ParamSpec(layout=good).validate()

    @pytest.mark.parametrize(
        "kwargs,field",
        [
            ({"rooting_type": "auto"}, "rooting_type"),
            ({"transform": "bogus"}, "transform"),
            ({"order": "asc"}, "order"),
            ({"tip_labels": "yes"}, "tip_labels"),
            ({"node_labels": "on"}, "node_labels"),
            ({"branch_labels": "on"}, "branch_labels"),
            ({"scale_bar": "on"}, "scale_bar"),
            ({"scale_axis": "on"}, "scale_axis"),
            ({"legend": "on"}, "legend"),
            ({"legend_position": "center"}, "legend_position"),
            ({"collapse_style": "circle"}, "collapse_style"),
            ({"multi_tree": "every"}, "multi_tree"),
        ],
    )
    def test_enum_fields(self, kwargs: Dict[str, Any], field: str) -> None:
        with pytest.raises(ToolError) as ei:
            ParamSpec(**kwargs).validate()
        assert ei.value.code == "invalid_argument"
        assert field in ei.value.error_detail

    @pytest.mark.parametrize(
        "bad_color",
        ["red", "#GGGGGG", "#FFF", "FF0000", "rgb(1,2,3)"],
    )
    def test_bad_hex_colors(self, bad_color: str) -> None:
        for field in ("background_color", "foreground_color", "selection_color", "label_color"):
            with pytest.raises(ToolError) as ei:
                ParamSpec(**{field: bad_color}).validate()
            assert ei.value.error_key == "param_validation_failed"

    def test_good_hex_colors_case_insensitive(self) -> None:
        for field in ("background_color", "foreground_color", "selection_color", "label_color"):
            spec = ParamSpec(**{field: "#AaBbCc"}).validate()
            assert spec is not None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"tip_label_font_style": 7},
            {"tip_label_font_size": 0},
            {"branch_width": -1},
            {"zoom": 0},
            {"expansion": -1},
            {"root_age": -1},
            {"scale_factor": 0},
            {"polar_angular_range_degrees": 361},
            {"polar_root_angle_degrees": -1},
            {"radial_spread": -1},
            {"curvature": -1},
            {"root_length": -1},
            {"scale_axis_font_size": 0},
            {"scale_axis_significant_digits": 0},
        ],
    )
    def test_numeric_bounds(self, kwargs: Dict[str, Any]) -> None:
        with pytest.raises(ToolError):
            ParamSpec(**kwargs).validate()

    def test_run_name_regex(self) -> None:
        for bad in ("../evil", "a/b", "a b", "", "x" * 65, "a$b"):
            with pytest.raises(ToolError) as ei:
                ParamSpec(run_name=bad).validate()
            assert ei.value.code == "invalid_argument"
        for good in ("output", "run_1", "my-tree-v2", "A_B-c", "x" * 64):
            ParamSpec(run_name=good).validate()

    def test_operations_must_be_list(self) -> None:
        with pytest.raises(ToolError):
            ParamSpec(operations={"op": "collapse"}).validate()

    def test_operations_unknown_op(self) -> None:
        with pytest.raises(ToolError) as ei:
            ParamSpec(operations=[{"op": "explode", "taxa": ["A"]}]).validate()
        assert "explode" in ei.value.error_detail

    def test_operations_missing_taxa(self) -> None:
        for op_name in ("highlight", "color", "color_all", "font", "collapse"):
            with pytest.raises(ToolError) as ei:
                ParamSpec(operations=[{"op": op_name}]).validate()
            assert "taxa" in ei.value.error_detail

    def test_operations_bad_color(self) -> None:
        with pytest.raises(ToolError):
            ParamSpec(operations=[{"op": "highlight", "taxa": ["A"], "color": "#00"}]).validate()

    def test_operations_bad_collapse_type(self) -> None:
        with pytest.raises(ToolError):
            ParamSpec(operations=[{"op": "collapse", "taxa": ["A"], "collapse_type": "fan"}]).validate()

    def test_operations_bad_font_style(self) -> None:
        with pytest.raises(ToolError):
            ParamSpec(operations=[{"op": "font", "taxa": ["A"], "font_style": 9}]).validate()
        # 0..3 ok
        ParamSpec(operations=[{"op": "font", "taxa": ["A"], "font_style": 3}]).validate()

    @pytest.mark.parametrize(
        "taxa",
        ["AB", [], [1], ["A", 2], [""], {"A": 1}, None],
    )
    def test_operations_taxa_must_be_non_empty_list_of_str(self, taxa: Any) -> None:
        with pytest.raises(ToolError) as ei:
            ParamSpec(operations=[{"op": "color", "taxa": taxa, "color": "#2196F3"}]).validate()
        assert ei.value.error_key == "param_validation_failed"
        assert "taxa" in ei.value.error_detail

    @pytest.mark.parametrize(
        "op",
        [
            {"op": "highlight", "taxa": ["A"], "width": 0},
            {"op": "highlight", "taxa": ["A"], "width": "2"},
            {"op": "highlight", "taxa": ["A"], "offset": 0.5},
            {"op": "highlight", "taxa": ["A"], "offset": "1"},
            {"op": "font", "taxa": ["A"], "font_size": 0},
            {"op": "font", "taxa": ["A"], "font_size": 1.5},
            {"op": "font", "taxa": ["A"], "font_name": ""},
            {"op": "font", "taxa": ["A"], "label": 3},
            {"op": "collapse_group", "group": ""},
            {"op": "collapse_group", "group": 3},
            {"op": "collapse_rank", "rank": "bogus"},
            {"op": "collapse_rank", "rank": "class", "auto_color_rank": "bogus"},
            {"op": "collapse_rank", "rank": "class", "collapse_style": "circle"},
        ],
    )
    def test_operations_field_validation(self, op: Dict[str, Any]) -> None:
        with pytest.raises(ToolError) as ei:
            ParamSpec(operations=[op]).validate()
        assert ei.value.code == "invalid_argument"

    def test_rank_fields_validated(self) -> None:
        for field in ("auto_color_rank", "collapse_rank"):
            with pytest.raises(ToolError) as ei:
                ParamSpec(**{field: "bogus"}).validate()
            assert field in ei.value.error_detail
        ParamSpec(auto_color_rank="phylum", collapse_rank="class").validate()

    def test_table_sep_single_char(self) -> None:
        ParamSpec(table_sep="|").validate()
        for bad in ("||", "", 3):
            with pytest.raises(ToolError) as ei:
                ParamSpec(table_sep=bad).validate()
            assert "table_sep" in ei.value.error_detail

    def test_seed_must_be_int(self) -> None:
        ParamSpec(seed=42).validate()
        for bad in ("42", 1.5, True):
            with pytest.raises(ToolError) as ei:
                ParamSpec(seed=bad).validate()
            assert "seed" in ei.value.error_detail


# --------------------------------------------------------------------------- #
# to_cli_args — CLI mapping table
# --------------------------------------------------------------------------- #
class TestToCliArgs:
    def test_layout_zoom_expansion(self) -> None:
        args = ParamSpec(layout="polar", zoom=1.5, expansion=2).to_cli_args()
        assert "--layout" in args and args[args.index("--layout") + 1] == "polar"
        assert "--zoom" in args and args[args.index("--zoom") + 1] == "1.5"
        assert "--expansion" in args and args[args.index("--expansion") + 1] == "2"

    def test_colors_lowercased(self) -> None:
        args = ParamSpec(
            background_color="#FAFAFA", foreground_color="#212121", selection_color="#FF0000"
        ).to_cli_args()
        assert ["--background-color", "#fafafa"] in _pairs(args)
        assert ["--foreground-color", "#212121"] in _pairs(args)
        assert ["--selection-color", "#ff0000"] in _pairs(args)

    def test_rooting_transform_order(self) -> None:
        args = ParamSpec(rooted=True, rooting_type="midpoint", transform="cladogram",
                         order="increasing").to_cli_args()
        assert "--rooted" in args
        assert ["--rooting-type", "midpoint"] in _pairs(args)
        assert ["--transform", "cladogram"] in _pairs(args)
        assert ["--order", "increasing"] in _pairs(args)

    def test_tip_labels_flags(self) -> None:
        show = ParamSpec(tip_labels="show").to_cli_args()
        hide = ParamSpec(tip_labels="hide").to_cli_args()
        assert "--tip-labels-show" in show
        assert "--tip-labels-hide" in hide

    def test_font_flags(self) -> None:
        args = ParamSpec(tip_label_font_name="Helvetica", tip_label_font_size=14,
                         tip_label_font_style=2).to_cli_args()
        assert ["--font-name", "Helvetica"] in _pairs(args)
        assert ["--font-size", "14"] in _pairs(args)
        assert ["--font-style", "2"] in _pairs(args)
        assert ["--label-color", "#ff0000"] in _pairs(ParamSpec(label_color="#FF0000").to_cli_args())

    def test_scale_axis_set_pairs(self) -> None:
        args = ParamSpec(scale_axis="show", scale_axis_reverse=True,
                         scale_axis_font_size=14, scale_axis_significant_digits=2).to_cli_args()
        assert "--scale-axis-show" in args
        assert "--set" in args
        assert "scaleAxis.reverseAxis=true" in args
        assert "scaleAxis.fontSize=14" in args
        assert "scaleAxis.significantDigits=2" in args

    def test_polar_angular(self) -> None:
        args = ParamSpec(polar_angular_range_degrees=180,
                         polar_root_angle_degrees=270).to_cli_args()
        assert ["--angular-range", "180"] in _pairs(args)
        assert ["--root-angle", "270"] in _pairs(args)

    def test_align_tip_labels_false_set(self) -> None:
        args = ParamSpec(align_tip_labels=False).to_cli_args()
        assert "--set" in args
        assert args[-1] == "rectilinearLayout.alignTipLabels=false"

    def test_additional_config_sets(self) -> None:
        args = ParamSpec(additional_config={"tipLabels.fontSize": 18}).to_cli_args()
        assert ["--set", "tipLabels.fontSize=18"] in _pairs(args)

    def test_auto_color_and_collapse(self) -> None:
        args = ParamSpec(auto_color_rank="phylum").to_cli_args()
        assert ["--auto-color", "phylum"] in _pairs(args)
        # CLI --collapse-rank implies internal phylum auto-color when none given
        args = ParamSpec(collapse_rank="class", collapse_style="cartoon").to_cli_args()
        assert ["--collapse-rank", "class"] in _pairs(args)
        assert ["--collapse-style", "cartoon"] in _pairs(args)
        assert ["--auto-color", "phylum"] in _pairs(args)

    def test_collapse_rank_with_auto_color(self) -> None:
        args = ParamSpec(collapse_rank="class", auto_color_rank="phylum").to_cli_args()
        assert ["--auto-color", "phylum"] in _pairs(args)
        assert ["--collapse-rank", "class"] in _pairs(args)

    def test_taxonomy_context(self) -> None:
        args = ParamSpec(taxonomy_levels="d:domain,p:phylum",
                         taxonomy_mapping_file="/m/x.tsv",
                         table_sep="\t").to_cli_args()
        assert ["--taxonomy-levels", "d:domain,p:phylum"] in _pairs(args)
        assert ["--taxonomy-mapping-file", "/m/x.tsv"] in _pairs(args)
        assert ["--table-sep", "\t"] in _pairs(args)

    # ---- operations -----------------------------------------------------
    def test_op_highlight(self) -> None:
        args = ParamSpec(
            operations=[{"op": "highlight", "taxa": ["A", "B"], "color": "#FF0000", "width": 3}]
        ).to_cli_args()
        assert ["--highlight", "A,B:#FF0000:3"] in _pairs(args)

    def test_op_color(self) -> None:
        args = ParamSpec(operations=[{"op": "color", "taxa": ["C"], "color": "#2196F3"}]).to_cli_args()
        assert ["--color-clade", "C:#2196F3"] in _pairs(args)

    def test_op_color_all(self) -> None:
        args = ParamSpec(
            operations=[{"op": "color_all", "taxa": ["D"], "color": "#00FF00"}]
        ).to_cli_args()
        assert ["--color-clade", "D:#00FF00"] in _pairs(args)
        assert args.count("--color-all") == 1

    def test_op_color_all_global_flag_emitted_once(self) -> None:
        # --color-all is a global CLI switch: never one flag per operation.
        args = ParamSpec(operations=[
            {"op": "color_all", "taxa": ["D"], "color": "#00FF00"},
            {"op": "color_all", "taxa": ["E"], "color": "#0000FF"},
        ]).to_cli_args()
        assert args.count("--color-all") == 1
        assert ["--color-clade", "D:#00FF00"] in _pairs(args)
        assert ["--color-clade", "E:#0000FF"] in _pairs(args)
        # The flag must precede the specs it applies to when re-parsed by hand
        # (argparse itself is order-independent).
        assert args.index("--color-all") < args.index("--color-clade")

    def test_op_collapse_group_uses_clade(self) -> None:
        args = ParamSpec(operations=[{"op": "collapse_group", "group": "Phy1"}]).to_cli_args()
        assert ["--clade", "Phy1"] in _pairs(args)
        assert "--collapse-taxa" not in args

    def test_op_collapse_group_extras_use_resolved_taxa(self) -> None:
        args = ParamSpec(operations=[{
            "op": "collapse_group", "group": "Phy1", "taxa": ["A", "B"],
            "label": "X", "collapse_type": "cartoon",
        }]).to_cli_args()
        assert ["--collapse-taxa", "A,B,label=X,type=cartoon"] in _pairs(args)
        assert "--clade" not in args

    def test_op_highlight_offset_is_int_and_keeps_width_slot(self) -> None:
        args = ParamSpec(operations=[{
            "op": "highlight", "taxa": ["A", "B"], "offset": 2,
        }]).to_cli_args()
        # color + width slots are mandatory before the offset slot.
        assert ["--highlight", "A,B:#804548:4:2"] in _pairs(args)
        args = ParamSpec(operations=[{
            "op": "highlight", "taxa": ["A"], "width": 1.5,
        }]).to_cli_args()
        assert ["--highlight", "A:#804548:1.5"] in _pairs(args)

    def test_legend_hide_uses_set(self) -> None:
        args = ParamSpec(legend="hide").to_cli_args()
        assert ["--set", "legend.isShown=false"] in _pairs(args)
        assert "--legend-hide" not in args
        show = ParamSpec(legend="show").to_cli_args()
        assert "--legend-show" in show

    def test_multi_tree_and_seed(self) -> None:
        args = ParamSpec(multi_tree="last").to_cli_args()
        assert ["--multi-tree", "last"] in _pairs(args)
        args = ParamSpec(multi_tree="random", seed=7).to_cli_args()
        assert ["--multi-tree", "random"] in _pairs(args)
        assert ["--seed", "7"] in _pairs(args)
        assert "--seed" not in ParamSpec(multi_tree="first").to_cli_args()

    def test_op_font(self) -> None:
        args = ParamSpec(
            operations=[{"op": "font", "taxa": ["E"], "font_name": "Arial",
                         "font_style": 1, "font_size": 14}]
        ).to_cli_args()
        assert ["--font-clade", "E:Arial-BOLD-14"] in _pairs(args)

    def test_op_collapse(self) -> None:
        args = ParamSpec(operations=[{"op": "collapse", "taxa": ["A", "B"],
                                      "label": "AB", "collapse_type": "cartoon"}]).to_cli_args()
        assert ["--collapse-taxa", "A,B,label=AB,type=cartoon"] in _pairs(args)

    def test_op_collapse_rank(self) -> None:
        args = ParamSpec(operations=[{"op": "collapse_rank", "rank": "class",
                                      "collapse_style": "cartoon"}]).to_cli_args()
        assert ["--collapse-rank", "class"] in _pairs(args)
        assert ["--collapse-style", "cartoon"] in _pairs(args)

    def test_op_clear_hilights(self) -> None:
        args = ParamSpec(operations=[{"op": "clear_hilights"}]).to_cli_args()
        assert "--clear-hilights" in args

    def test_number_formatting_matches_cli(self) -> None:
        # CLI renders int-valued floats without trailing '.0'
        assert ["--branch-width", "4"] in _pairs(ParamSpec(branch_width=4.0).to_cli_args())
        assert ["--branch-width", "4.5"] in _pairs(ParamSpec(branch_width=4.5).to_cli_args())
        assert ["--root-age", "2"] in _pairs(ParamSpec(root_age=2.0).to_cli_args())


# --------------------------------------------------------------------------- #
# to_config_dict — figtree-block keys（含角度换算）
# --------------------------------------------------------------------------- #
class TestToConfigDict:
    def test_layout_keys(self) -> None:
        cfg = ParamSpec(layout="rectilinear", expansion=2, zoom=1.25).to_config_dict()
        assert cfg["layout.layoutType"] == "RECTILINEAR"
        assert cfg["layout.expansion"] == 2
        assert cfg["layout.zoom"] == 1.25

    def test_angular_conversion(self) -> None:
        # (360 - deg) * 1000
        cfg = ParamSpec(polar_angular_range_degrees=180).to_config_dict()
        assert cfg["polarLayout.angularRange"] == 180000
        cfg = ParamSpec(polar_angular_range_degrees=280).to_config_dict()
        assert cfg["polarLayout.angularRange"] == 80000
        # (deg - 180) * 1000
        cfg = ParamSpec(polar_root_angle_degrees=270).to_config_dict()
        assert cfg["polarLayout.rootAngle"] == 90000
        cfg = ParamSpec(polar_root_angle_degrees=230).to_config_dict()
        assert cfg["polarLayout.rootAngle"] == 50000
        cfg = ParamSpec(polar_root_angle_degrees=180).to_config_dict()
        assert cfg["polarLayout.rootAngle"] == 0

    def test_rooting_type(self) -> None:
        cfg = ParamSpec(rooting_type="user").to_config_dict()
        assert cfg["trees.rooting"] is True
        assert cfg["trees.rootingType"] == "User Selection"
        cfg = ParamSpec(rooting_type="midpoint").to_config_dict()
        assert cfg["trees.rootingType"] == "Mid-point"

    def test_transform_order(self) -> None:
        cfg = ParamSpec(transform="cladogram").to_config_dict()
        assert cfg["trees.transformType"] == "Cladogram"
        cfg = ParamSpec(order="decreasing").to_config_dict()
        assert cfg["trees.orderType"] == "Decreasing Node Density"

    def test_appearance(self) -> None:
        cfg = ParamSpec(background_color="#FAFAFA", branch_width=3.0,
                        branch_color_attribute="!color").to_config_dict()
        assert cfg["appearance.backgroundColour"] == "#fafafa"
        assert cfg["appearance.branchLineWidth"] == 3.0
        assert cfg["appearance.branchColorAttribute"] == "!color"

    def test_tip_labels(self) -> None:
        cfg = ParamSpec(tip_labels="hide", tip_label_font_size=14,
                        label_color="#212121").to_config_dict()
        assert cfg["tipLabels.isShown"] is False
        assert cfg["tipLabels.fontSize"] == 14
        assert cfg["tipLabels.colorAttribute"] == "#212121"

    def test_align_tip_labels_keyed_by_layout(self) -> None:
        cfg = ParamSpec(align_tip_labels=False, layout="polar").to_config_dict()
        assert cfg["polarLayout.alignTipLabels"] is False
        cfg = ParamSpec(align_tip_labels=True).to_config_dict()
        assert cfg["rectilinearLayout.alignTipLabels"] is True

    def test_scale_axis(self) -> None:
        cfg = ParamSpec(scale_axis_reverse=True, scale_axis_font_size=14,
                        scale_axis_significant_digits=2, root_age=10.0).to_config_dict()
        assert cfg["scaleAxis.reverseAxis"] is True
        assert cfg["scaleAxis.fontSize"] == 14
        assert cfg["scaleAxis.significantDigits"] == 2
        assert cfg["scale.rootAge"] == 10.0

    def test_legend(self) -> None:
        cfg = ParamSpec(legend="show", legend_position="top").to_config_dict()
        assert cfg["legend.isShown"] is True
        # set_legend() capitalises the position ("Top"), not "TOP".
        assert cfg["legend.position"] == "Top"

    def test_legend_position_without_toggle(self) -> None:
        cfg = ParamSpec(legend_position="bottom").to_config_dict()
        assert cfg["legend.position"] == "Bottom"
        assert "legend.isShown" not in cfg

    def test_rooting_only_emitted_when_true(self) -> None:
        # rooted=False / unrooted=False are no-ops and must not be emitted.
        assert "trees.rooting" not in ParamSpec(rooted=False).to_config_dict()
        assert "trees.rooting" not in ParamSpec(unrooted=False).to_config_dict()
        assert ParamSpec(rooted=True).to_config_dict()["trees.rooting"] is True
        assert ParamSpec(unrooted=True).to_config_dict()["trees.rooting"] is False
        # unrooted wins when both are requested (CLI parity).
        assert ParamSpec(rooted=True, unrooted=True).to_config_dict()["trees.rooting"] is False

    def test_additional_config_merged(self) -> None:
        cfg = ParamSpec(additional_config={"tipLabels.fontSize": 22}).to_config_dict()
        assert cfg["tipLabels.fontSize"] == 22


# --------------------------------------------------------------------------- #
# misc guarantees
# --------------------------------------------------------------------------- #
def _pairs(args: List[str]) -> List[List[str]]:
    return [args[i : i + 2] for i in range(0, len(args) - 1)]


class TestMisc:
    def test_font_style_names(self) -> None:
        assert FONT_STYLE_NAMES == {0: "PLAIN", 1: "BOLD", 2: "ITALIC", 3: "BOLD_ITALIC"}

    def test_stable_enums(self) -> None:
        assert LAYOUTS == ("rectilinear", "polar", "radial")
        assert ROOTING_TYPES == ("user", "midpoint")
        assert TRANSFORMS == ("cladogram", "phylogram")
        assert ORDERS == ("increasing", "decreasing")
        assert COLLAPSE_STYLES == ("collapse", "cartoon")
        assert MULTI_TREE_MODES == ("first", "last", "random", "split", "all", "ask")

    def test_error_codes_include_used_ones(self) -> None:
        for code in ("invalid_argument", "access_denied", "validation_failed",
                     "monophyly_error", "render_timeout", "java_missing", "jar_missing"):
            assert code in ERROR_CODES

    def test_config_json_serialisable(self) -> None:
        cfg = ParamSpec(layout="polar", polar_angular_range_degrees=180).to_config_dict()
        parsed = json.loads(json.dumps(cfg))
        assert parsed["polarLayout.angularRange"] == 180000
