# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Single source of truth for style parameters.

``ParamSpec`` mirrors the MCP ``style_tree`` parameter surface; the three
derived views are guaranteed to stay in sync:

- :meth:`ParamSpec.to_cli_args` — argv for ``figtreekit`` (byte-equivalent
  re-run, matching the CLI mapping table);
- :meth:`ParamSpec.to_config_dict` — FigTree block keys for ``--config``;
- :meth:`ParamSpec.apply_to_styler` — in-process styling (the actual path
  taken by MCP tool handlers).

Clade operations (``operations``) are also rendered here so that
``cli_command``, ``config_json`` and the executed result never diverge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ._errors import ToolError
from ._logging import get_logger

_log = get_logger()

# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
LAYOUTS = ("rectilinear", "polar", "radial")
TAXONOMY_RANKS = ("domain", "superphylum", "phylum", "class", "order", "family", "genus", "species")
COLLAPSE_STYLES = ("collapse", "cartoon")
ROOTING_TYPES = ("user", "midpoint")
TRANSFORMS = ("cladogram", "phylogram")
ORDERS = ("increasing", "decreasing")
FONT_STYLE_NAMES = {0: "PLAIN", 1: "BOLD", 2: "ITALIC", 3: "BOLD_ITALIC"}
LEGEND_POSITIONS = ("top", "bottom", "left", "right")
MULTI_TREE_MODES = ("first", "last", "random", "split", "all", "ask")

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _is_num_le0(value: float) -> bool:
    """True when *value* is a number ≤ 0 (strictly-positive bound)."""
    return value <= 0


def _is_num_lt0(value: float) -> bool:
    """True when *value* is a number < 0 (non-negative bound)."""
    return value < 0


# --------------------------------------------------------------------------- #
# ParamSpec
# --------------------------------------------------------------------------- #
@dataclass
class ParamSpec:
    """Full MCP ``style_tree`` parameter surface (all optional)."""

    # tree source / taxonomy context
    tree_content: Optional[str] = None
    tree_file: Optional[str] = None
    taxonomy_levels: Optional[str] = None
    taxonomy_mapping_file: Optional[str] = None
    table_sep: Optional[str] = None
    taxonomy_delimiter_mode: Optional[str] = None

    # layout / tree properties
    layout: Optional[str] = None
    expansion: Optional[int] = None
    zoom: Optional[float] = None
    rooted: Optional[bool] = None
    unrooted: Optional[bool] = None
    rooting_type: Optional[str] = None
    transform: Optional[str] = None
    order: Optional[str] = None

    # appearance
    background_color: Optional[str] = None
    foreground_color: Optional[str] = None
    selection_color: Optional[str] = None
    branch_width: Optional[float] = None
    branch_color_attribute: Optional[str] = None

    # labels
    tip_labels: Optional[str] = None
    tip_label_font_name: Optional[str] = None
    tip_label_font_size: Optional[int] = None
    tip_label_font_style: Optional[int] = None
    label_color: Optional[str] = None
    align_tip_labels: Optional[bool] = None
    node_labels: Optional[str] = None
    node_display_attribute: Optional[str] = None
    branch_labels: Optional[str] = None
    branch_display_attribute: Optional[str] = None

    # scale
    scale_bar: Optional[str] = None
    scale_axis: Optional[str] = None
    scale_axis_reverse: Optional[bool] = None
    scale_axis_font_size: Optional[int] = None
    scale_axis_significant_digits: Optional[int] = None
    root_age: Optional[float] = None
    scale_factor: Optional[float] = None

    # layout-specific
    polar_angular_range_degrees: Optional[float] = None
    polar_root_angle_degrees: Optional[float] = None
    radial_spread: Optional[float] = None
    curvature: Optional[int] = None
    root_length: Optional[int] = None

    # legend
    legend: Optional[str] = None
    legend_position: Optional[str] = None

    # taxonomy-driven styling
    auto_color_rank: Optional[str] = None
    collapse_rank: Optional[str] = None
    collapse_style: str = "collapse"

    # ordered clade operations / advanced
    operations: Optional[List[Dict[str, Any]]] = None
    additional_config: Optional[Dict[str, Any]] = None

    # multi-tree / misc
    multi_tree: Optional[str] = None
    tree_index: Optional[int] = None
    seed: Optional[int] = None
    run_name: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self) -> "ParamSpec":
        """Field-level validation; raises ``ToolError(invalid_argument)``."""
        errs: List[Dict[str, str]] = []

        def _err(field_name: str, message: str) -> None:
            errs.append({"level": "ERROR", "field": field_name, "message": message})

        if self.layout is not None and self.layout not in LAYOUTS:
            _err("layout", f"layout 必须是 {LAYOUTS} 之一，得到 '{self.layout}'")
        if self.rooting_type is not None and self.rooting_type not in ROOTING_TYPES:
            _err("rooting_type", f"rooting_type 必须是 {ROOTING_TYPES} 之一")
        if self.transform is not None and self.transform not in TRANSFORMS:
            _err("transform", f"transform 必须是 {TRANSFORMS} 之一")
        if self.order is not None and self.order not in ORDERS:
            _err("order", f"order 必须是 {ORDERS} 之一")
        if self.tip_labels is not None and self.tip_labels not in ("show", "hide"):
            _err("tip_labels", "tip_labels 必须是 show|hide")
        if self.node_labels is not None and self.node_labels not in ("show", "hide"):
            _err("node_labels", "node_labels 必须是 show|hide")
        if self.branch_labels is not None and self.branch_labels not in ("show", "hide"):
            _err("branch_labels", "branch_labels 必须是 show|hide")
        if self.scale_bar is not None and self.scale_bar not in ("show", "hide"):
            _err("scale_bar", "scale_bar 必须是 show|hide")
        if self.scale_axis is not None and self.scale_axis not in ("show", "hide"):
            _err("scale_axis", "scale_axis 必须是 show|hide")
        if self.legend is not None and self.legend not in ("show", "hide"):
            _err("legend", "legend 必须是 show|hide")
        if self.legend_position is not None and self.legend_position not in LEGEND_POSITIONS:
            _err("legend_position", f"legend_position 必须是 {LEGEND_POSITIONS} 之一")
        if self.collapse_style not in COLLAPSE_STYLES:
            _err("collapse_style", f"collapse_style 必须是 {COLLAPSE_STYLES} 之一")
        if self.multi_tree is not None and self.multi_tree not in MULTI_TREE_MODES:
            _err("multi_tree", f"multi_tree 必须是 {MULTI_TREE_MODES} 之一")
        if self.tree_index is not None:
            if not isinstance(self.tree_index, int) or isinstance(self.tree_index, bool):
                _err("tree_index", "tree_index 必须是整数")
            elif self.tree_index < 0:
                _err("tree_index", "tree_index 必须 >= 0")
        if self.seed is not None:
            if not isinstance(self.seed, int) or isinstance(self.seed, bool):
                _err("seed", "seed 必须是整数（用于 multi_tree=random 复现）")
        if self.auto_color_rank is not None and self.auto_color_rank not in TAXONOMY_RANKS:
            _err("auto_color_rank", f"auto_color_rank 必须是 {TAXONOMY_RANKS} 之一")
        if self.collapse_rank is not None and self.collapse_rank not in TAXONOMY_RANKS:
            _err("collapse_rank", f"collapse_rank 必须是 {TAXONOMY_RANKS} 之一")
        if self.taxonomy_delimiter_mode is not None and self.taxonomy_delimiter_mode not in (
            "reverse",
            "greedy",
            "segment",
        ):
            _err(
                "taxonomy_delimiter_mode",
                "taxonomy_delimiter_mode 必须是 reverse|greedy|segment 之一",
            )
        if self.table_sep is not None:
            if not isinstance(self.table_sep, str) or len(self.table_sep) != 1:
                _err("table_sep", "table_sep 必须是单个字符（映射文件列分隔符）")

        for name, value in (
            ("background_color", self.background_color),
            ("foreground_color", self.foreground_color),
            ("selection_color", self.selection_color),
            ("label_color", self.label_color),
        ):
            if value is not None:
                if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
                    _err(name, f"颜色必须是 #RRGGBB 形式（16 进制），得到 '{value}'")

        # Numeric fields: enforce a numeric type before comparing, so adversarial
        # values (strings, bools, lists) become clean invalid_argument instead of
        # a bare TypeError.
        for fname, val, bound in (
            ("tip_label_font_size", self.tip_label_font_size, _is_num_le0),
            ("branch_width", self.branch_width, _is_num_le0),
            ("zoom", self.zoom, _is_num_le0),
            ("scale_factor", self.scale_factor, _is_num_le0),
            ("scale_axis_font_size", self.scale_axis_font_size, _is_num_le0),
            ("scale_axis_significant_digits", self.scale_axis_significant_digits, _is_num_le0),
            ("expansion", self.expansion, _is_num_lt0),
            ("root_age", self.root_age, _is_num_lt0),
            ("radial_spread", self.radial_spread, _is_num_lt0),
            ("curvature", self.curvature, _is_num_lt0),
            ("root_length", self.root_length, _is_num_lt0),
        ):
            if val is not None:
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    _err(fname, f"{fname} 必须是数值（int/float），得到 {type(val).__name__}")
                elif bound(val):
                    _err(fname, f"{fname} 数值越界")

        for fname, val in (
            ("polar_angular_range_degrees", self.polar_angular_range_degrees),
            ("polar_root_angle_degrees", self.polar_root_angle_degrees),
        ):
            if val is not None:
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    _err(fname, f"{fname} 必须是数值（int/float），得到 {type(val).__name__}")
                elif not (0 <= val <= 360):
                    _err(fname, f"{fname} 必须在 [0, 360] 度")

        if self.tip_label_font_style is not None:
            if not isinstance(self.tip_label_font_style, int) or isinstance(
                self.tip_label_font_style, bool
            ):
                _err(
                    "tip_label_font_style",
                    "tip_label_font_style 必须是整数 0(plain)/1(bold)/2(italic)/3(bold-italic)",
                )
            elif self.tip_label_font_style not in (0, 1, 2, 3):
                _err(
                    "tip_label_font_style",
                    "tip_label_font_style 必须是 0(plain)/1(bold)/2(italic)/3(bold-italic)",
                )
        if self.run_name is not None:
            if not isinstance(self.run_name, str) or not _RUN_NAME_RE.match(self.run_name):
                _err("run_name", "run_name 必须是字符串，且仅允许字母/数字/_/-，长度 1-64")

        if self.operations is not None:
            if not isinstance(self.operations, list):
                _err("operations", "operations 必须是数组")
            else:
                for i, op in enumerate(self.operations):
                    self._validate_operation(i, op, errs)

        if errs:
            raise ToolError(
                "invalid_argument",
                "style_tree 参数校验失败",
                error_key="param_validation_failed",
                error_detail="\n".join(f"{e['field']}: {e['message']}" for e in errs),
                details=errs,
            )
        return self

    @staticmethod
    def _validate_operation(index: int, op: Any, errs: List[Dict[str, str]]) -> None:
        if not isinstance(op, dict):
            errs.append(
                {"level": "ERROR", "field": f"operations[{index}]", "message": "操作必须是对象"}
            )
            return
        field_prefix = f"operations[{index}]"
        op_name = op.get("op")
        known = {
            "highlight",
            "color",
            "color_all",
            "font",
            "collapse",
            "collapse_group",
            "collapse_rank",
            "clear_hilights",
        }
        if op_name not in known:
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.op",
                    "message": f"op 必须是 {sorted(known)} 之一，得到 {op_name!r}",
                }
            )
            return

        # --- taxa: strictly a non-empty list of non-empty strings ----------
        taxa = op.get("taxa")
        if op_name in ("highlight", "color", "color_all", "font", "collapse"):
            if not isinstance(taxa, list) or not taxa:
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.taxa",
                        "message": 'taxa 必须是非空字符串数组 list[str]（如 ["A", "B"]）',
                    }
                )
            elif not all(isinstance(t, str) and t.strip() for t in taxa):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.taxa",
                        "message": "taxa 数组元素必须是非空字符串",
                    }
                )
        elif taxa is not None and (
            not isinstance(taxa, list) or not all(isinstance(t, str) and t.strip() for t in taxa)
        ):
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.taxa",
                    "message": "taxa 若提供必须是非空字符串数组 list[str]",
                }
            )

        # --- group ----------------------------------------------------------
        if op_name == "collapse_group":
            group = op.get("group")
            if not isinstance(group, str) or not group.strip():
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.group",
                        "message": "collapse_group 需要非空 group 类群名",
                    }
                )
        elif op.get("group") is not None and not isinstance(op.get("group"), str):
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.group",
                    "message": "group 必须是字符串",
                }
            )

        # --- colors ---------------------------------------------------------
        color = op.get("color")
        if color is not None:
            if not isinstance(color, str) or not _HEX_COLOR_RE.match(color):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.color",
                        "message": f"颜色必须是 #RRGGBB 形式，得到 '{color}'",
                    }
                )

        # --- collapse style -------------------------------------------------
        ctype = op.get("collapse_type")
        if ctype is not None and (not isinstance(ctype, str) or ctype not in COLLAPSE_STYLES):
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.collapse_type",
                    "message": f"collapse_type 必须是 {COLLAPSE_STYLES} 之一",
                }
            )
        cstyle = op.get("collapse_style")
        if cstyle is not None and (not isinstance(cstyle, str) or cstyle not in COLLAPSE_STYLES):
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.collapse_style",
                    "message": f"collapse_style 必须是 {COLLAPSE_STYLES} 之一",
                }
            )

        # --- ranks ----------------------------------------------------------
        for rank_key in ("rank", "auto_color_rank"):
            rank = op.get(rank_key)
            if rank is not None and (not isinstance(rank, str) or rank not in TAXONOMY_RANKS):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.{rank_key}",
                        "message": f"{rank_key} 必须是 {TAXONOMY_RANKS} 之一，得到 '{rank}'",
                    }
                )

        # --- label / font ---------------------------------------------------
        label = op.get("label")
        if label is not None and not isinstance(label, str):
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.label",
                    "message": "label 必须是字符串",
                }
            )
        font_name = op.get("font_name")
        if font_name is not None and (not isinstance(font_name, str) or not font_name.strip()):
            errs.append(
                {
                    "level": "ERROR",
                    "field": f"{field_prefix}.font_name",
                    "message": "font_name 必须是非空字符串",
                }
            )
        fstyle = op.get("font_style")
        if fstyle is not None:
            if not isinstance(fstyle, int) or isinstance(fstyle, bool):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.font_style",
                        "message": "font_style 必须是 0-3",
                    }
                )
            elif fstyle not in (0, 1, 2, 3):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.font_style",
                        "message": "font_style 必须是 0-3",
                    }
                )

        # --- numeric fields -------------------------------------------------
        width = op.get("width")
        if width is not None:
            if not isinstance(width, (int, float)) or isinstance(width, bool):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.width",
                        "message": "width 必须是数值",
                    }
                )
            elif width <= 0:
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.width",
                        "message": "width 必须 > 0",
                    }
                )
        offset = op.get("offset")
        if offset is not None:
            if not isinstance(offset, (int, float)) or isinstance(offset, bool):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.offset",
                        "message": "offset 必须是整数（CLI 仅接受整数偏移）",
                    }
                )
            elif float(offset) != int(offset):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.offset",
                        "message": "offset 必须是整数（CLI 的 --highlight 偏移按 int 解析）",
                    }
                )
        font_size = op.get("font_size")
        if font_size is not None:
            if not isinstance(font_size, (int, float)) or isinstance(font_size, bool):
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.font_size",
                        "message": "font_size 必须是正整数",
                    }
                )
            elif float(font_size) != int(font_size) or int(font_size) <= 0:
                errs.append(
                    {
                        "level": "ERROR",
                        "field": f"{field_prefix}.font_size",
                        "message": "font_size 必须是正整数",
                    }
                )

    # ------------------------------------------------------------------ #
    # to_cli_args — exact argv for `python -m figtreekit`
    # ------------------------------------------------------------------ #
    def to_cli_args(self) -> List[str]:
        """Build the ``figtreekit`` argv equivalent of these parameters.

        The ordering follows ``figtreekit._cli.apply_cli_args`` + the CLI main
        flow (custom params → clade annotations → auto-color → collapses) so
        that re-running the returned command reproduces byte-identical output.
        """
        args: List[str] = []

        # --- appearance (CLI order: width, attribute, colors) ---
        if self.branch_width is not None:
            args += ["--branch-width", _fmt_num(self.branch_width)]
        if self.branch_color_attribute is not None:
            args += ["--branch-color-attribute", self.branch_color_attribute]
        if self.background_color is not None:
            args += ["--background-color", self.background_color.lower()]
        if self.foreground_color is not None:
            args += ["--foreground-color", self.foreground_color.lower()]
        if self.selection_color is not None:
            args += ["--selection-color", self.selection_color.lower()]

        # --- layout ---
        if self.layout is not None:
            args += ["--layout", self.layout]
        if self.expansion is not None:
            args += ["--expansion", str(self.expansion)]
        if self.zoom is not None:
            args += ["--zoom", _fmt_num(self.zoom)]

        # --- trees ---
        if self.unrooted:
            args += ["--unrooted"]
        if self.rooted:
            args += ["--rooted"]
        if self.rooting_type is not None:
            args += ["--rooting-type", self.rooting_type]
        if self.transform is not None:
            args += ["--transform", self.transform]
        if self.order is not None:
            args += ["--order", self.order]

        # --- tip labels ---
        if self.tip_labels == "show":
            args += ["--tip-labels-show"]
        elif self.tip_labels == "hide":
            args += ["--tip-labels-hide"]
        if self.tip_label_font_name is not None:
            args += ["--font-name", self.tip_label_font_name]
        if self.tip_label_font_size is not None:
            args += ["--font-size", str(self.tip_label_font_size)]
        if self.tip_label_font_style is not None:
            args += ["--font-style", str(self.tip_label_font_style)]
        if self.label_color is not None:
            args += ["--label-color", self.label_color.lower()]

        # --- node / branch labels ---
        if self.node_labels == "show":
            args += ["--node-labels-show"]
        elif self.node_labels == "hide":
            args += ["--node-labels-hide"]
        if self.node_display_attribute is not None:
            args += ["--node-display-attribute", self.node_display_attribute]
        if self.branch_labels == "show":
            args += ["--branch-labels-show"]
        elif self.branch_labels == "hide":
            args += ["--branch-labels-hide"]
        if self.branch_display_attribute is not None:
            args += ["--branch-display-attribute", self.branch_display_attribute]

        # --- scale bar / axis / scale ---
        if self.scale_bar == "show":
            args += ["--scale-bar-show"]
        elif self.scale_bar == "hide":
            args += ["--scale-bar-hide"]
        if self.scale_axis == "show":
            args += ["--scale-axis-show"]
        elif self.scale_axis == "hide":
            args += ["--scale-axis-hide"]
        if self.root_age is not None:
            args += ["--root-age", _fmt_num(self.root_age)]
        if self.scale_factor is not None:
            args += ["--scale-factor", _fmt_num(self.scale_factor)]

        # --- polar ---
        if self.polar_angular_range_degrees is not None:
            args += ["--angular-range", str(int(self.polar_angular_range_degrees))]
        if self.polar_root_angle_degrees is not None:
            args += ["--root-angle", str(int(self.polar_root_angle_degrees))]

        # --- align tip labels (default True in figtreekit → explicit off) ---
        if self.align_tip_labels:
            args += ["--align-tip-labels"]
        elif self.align_tip_labels is False:
            layout = self.layout or "rectilinear"
            args += ["--set", f"{layout}Layout.alignTipLabels=false"]

        # --- radial / rectilinear ---
        if self.radial_spread is not None:
            args += ["--radial-spread", _fmt_num(self.radial_spread)]
        if self.curvature is not None:
            args += ["--curvature", str(self.curvature)]
        if self.root_length is not None:
            args += ["--root-length", str(self.root_length)]

        # --- legend ---
        if self.legend == "show":
            args += ["--legend-show"]
        elif self.legend == "hide":
            # The CLI has no --legend-hide flag; hide through --set.
            args += ["--set", "legend.isShown=false"]
        if self.legend_position is not None:
            args += ["--legend-position", self.legend_position]

        # --- scale axis extras (--set, CLI) ---
        if self.scale_axis_reverse is not None:
            args += ["--set", f"scaleAxis.reverseAxis={str(self.scale_axis_reverse).lower()}"]
        if self.scale_axis_font_size is not None:
            args += ["--set", f"scaleAxis.fontSize={self.scale_axis_font_size}"]
        if self.scale_axis_significant_digits is not None:
            args += ["--set", f"scaleAxis.significantDigits={self.scale_axis_significant_digits}"]

        # --- additional config (--set, applied after base styling in CLI) ---
        if self.additional_config:
            for key, value in self.additional_config.items():
                args += ["--set", _to_set_pair(key, value)]

        # --- clade operations ---
        if self.operations:
            args += self._operations_to_cli_args(self.operations)

        # --- auto-color / collapse-rank ---
        if self.auto_color_rank is not None and not self.collapse_rank:
            args += ["--auto-color", self.auto_color_rank]
        if self.collapse_rank is not None:
            # CLI --collapse-rank performs an internal phylum auto-color when
            # no explicit palette rank was requested.
            if self.auto_color_rank is None:
                args += ["--auto-color", "phylum", "--collapse-rank", self.collapse_rank]
            else:
                args += [
                    "--auto-color",
                    self.auto_color_rank,
                    "--collapse-rank",
                    self.collapse_rank,
                ]
            if self.collapse_style != "collapse":
                args += ["--collapse-style", self.collapse_style]

        # --- taxonomy context ---
        if self.taxonomy_levels is not None:
            args += ["--taxonomy-levels", self.taxonomy_levels]
        if self.taxonomy_mapping_file is not None:
            args += ["--taxonomy-mapping-file", self.taxonomy_mapping_file]
        if self.table_sep is not None:
            args += ["--table-sep", self.table_sep]
        if self.taxonomy_delimiter_mode is not None:
            args += ["--taxonomy-delimiter-mode", self.taxonomy_delimiter_mode]

        # --- multi-tree selection (and reproducible random seed) ---
        if self.multi_tree is not None:
            args += ["--multi-tree", self.multi_tree]
        if self.seed is not None:
            args += ["--seed", str(self.seed)]

        return args

    @staticmethod
    def _operations_to_cli_args(operations: List[Dict[str, Any]]) -> List[str]:
        """Render operations as CLI argv.

        ``--color-all`` is a **global** CLI switch (it affects every
        ``--color-clade`` spec in the command), so it is emitted at most once
        instead of per operation.  Group-name collapses use ``--clade``;
        ``--collapse-taxa`` is only used when a label / non-default collapse
        style has to be carried and the resolved taxon list is available.
        """
        args: List[str] = []
        color_all_emitted = False
        # ``--color-all`` is a global switch; emit it once, before the specs.
        if any(op.get("op") == "color_all" for op in operations):
            args += ["--color-all"]
            color_all_emitted = True
        for op in operations:
            op_name = op.get("op")
            taxa_list = op.get("taxa") if isinstance(op.get("taxa"), list) else []
            taxa = ",".join(str(t) for t in taxa_list)
            if op_name == "highlight":
                spec = taxa
                color = op.get("color")
                width = op.get("width")
                offset = op.get("offset")
                # CLI format: TAXA[:#RRGGBB[:width[:offset]]] — a width or
                # offset requires the colour slot to be present, so fall back
                # to the same default colour the MCP applies.
                if color or width is not None or offset is not None:
                    spec += f":{color or '#804548'}"
                if width is not None or offset is not None:
                    # Positional slots: the offset can only be emitted when
                    # the width slot is present too (CLI default width = 4).
                    spec += f":{_fmt_num(width if width is not None else 4)}"
                if offset is not None:
                    # CLI parses the offset with int(); emit an integer.
                    spec += f":{int(offset)}"
                args += ["--highlight", spec]
            elif op_name in ("color", "color_all"):
                spec = f"{taxa}:{op.get('color', '#999999')}"
                args += ["--color-clade", spec]
                if op_name == "color_all" and not color_all_emitted:
                    args += ["--color-all"]
                    color_all_emitted = True
            elif op_name == "font":
                style = FONT_STYLE_NAMES.get(int(op.get("font_style", 0)), "PLAIN")
                spec = f"{taxa}:{op.get('font_name', 'Arial')}-{style}"
                if op.get("font_size") is not None:
                    spec += f"-{int(op['font_size'])}"
                args += ["--font-clade", spec]
            elif op_name == "collapse":
                spec = taxa
                if op.get("label"):
                    spec += f",label={op['label']}"
                if op.get("collapse_type") and op["collapse_type"] != "collapse":
                    spec += f",type={op['collapse_type']}"
                args += ["--collapse-taxa", spec]
            elif op_name == "collapse_group":
                group = str(op.get("group", ""))
                label = op.get("label") or None
                ctype = op.get("collapse_type") or "collapse"
                needs_extras = (label and label != group) or ctype != "collapse"
                if needs_extras and taxa_list:
                    # The CLI group-name flag (--clade) carries neither a
                    # label nor a collapse style; reproduce the exact collapse
                    # through the resolved taxon list instead.
                    spec = taxa
                    spec += f",label={label or group}"
                    if ctype != "collapse":
                        spec += f",type={ctype}"
                    args += ["--collapse-taxa", spec]
                else:
                    args += ["--clade", group]
            elif op_name == "collapse_rank":
                args += ["--collapse-rank", str(op.get("rank", "class"))]
                ctype = op.get("collapse_style") or op.get("collapse_type") or "collapse"
                if ctype != "collapse":
                    args += ["--collapse-style", ctype]
                if op.get("auto_color_rank"):
                    args += ["--auto-color", str(op["auto_color_rank"])]
            elif op_name == "clear_hilights":
                args += ["--clear-hilights"]
            elif op_name == "strip_annotations":
                args += ["--strip-annotations"]
        return args

    # ------------------------------------------------------------------ #
    # to_config_dict — FigTree block keys
    # ------------------------------------------------------------------ #
    def to_config_dict(self) -> Dict[str, Any]:
        """FigTree-block JSON config, excluding CLI-only flags."""
        cfg: Dict[str, Any] = {}

        if self.layout is not None:
            cfg["layout.layoutType"] = self.layout.upper()
        if self.expansion is not None:
            cfg["layout.expansion"] = self.expansion
        if self.zoom is not None:
            cfg["layout.zoom"] = self.zoom

        # Rooting: only emit when it actually changes the default (True for
        # rooted, False for unrooted); "rooted=False" / "unrooted=False" are
        # no-ops and must not appear in the config.  ``unrooted`` wins when
        # both are set, matching apply_mcp_styling / the CLI.
        if self.unrooted:
            cfg["trees.rooting"] = False
        elif self.rooted:
            cfg["trees.rooting"] = True
        if self.rooting_type is not None:
            cfg["trees.rooting"] = True
            cfg["trees.rootingType"] = (
                "User Selection" if self.rooting_type == "user" else "Mid-point"
            )
        if self.transform is not None:
            cfg["trees.transformType"] = self.transform.capitalize()
        if self.order is not None:
            cfg["trees.orderType"] = (
                "Increasing Node Density"
                if self.order == "increasing"
                else "Decreasing Node Density"
            )

        if self.background_color is not None:
            cfg["appearance.backgroundColour"] = self.background_color.lower()
        if self.foreground_color is not None:
            cfg["appearance.foregroundColour"] = self.foreground_color.lower()
        if self.selection_color is not None:
            cfg["appearance.selectionColour"] = self.selection_color.lower()
        if self.branch_width is not None:
            cfg["appearance.branchLineWidth"] = self.branch_width
        if self.branch_color_attribute is not None:
            cfg["appearance.branchColorAttribute"] = self.branch_color_attribute

        if self.tip_labels in ("show", "hide"):
            cfg["tipLabels.isShown"] = self.tip_labels == "show"
        if self.tip_label_font_name is not None:
            cfg["tipLabels.fontName"] = self.tip_label_font_name
        if self.tip_label_font_size is not None:
            cfg["tipLabels.fontSize"] = int(self.tip_label_font_size)
        if self.tip_label_font_style is not None:
            cfg["tipLabels.fontStyle"] = int(self.tip_label_font_style)
        if self.label_color is not None:
            cfg["tipLabels.colorAttribute"] = self.label_color.lower()

        layout_key = {
            "rectilinear": "rectilinearLayout.alignTipLabels",
            "polar": "polarLayout.alignTipLabels",
            "radial": "radialLayout.alignTipLabels",
        }.get(self.layout or "rectilinear")
        if self.align_tip_labels is not None:
            cfg[layout_key] = bool(self.align_tip_labels)

        if self.node_labels in ("show", "hide"):
            cfg["nodeLabels.isShown"] = self.node_labels == "show"
        if self.node_display_attribute is not None:
            cfg["nodeLabels.displayAttribute"] = self.node_display_attribute
        if self.branch_labels in ("show", "hide"):
            cfg["branchLabels.isShown"] = self.branch_labels == "show"
        if self.branch_display_attribute is not None:
            cfg["branchLabels.displayAttribute"] = self.branch_display_attribute

        if self.scale_bar in ("show", "hide"):
            cfg["scaleBar.isShown"] = self.scale_bar == "show"
        if self.scale_axis in ("show", "hide"):
            cfg["scaleAxis.isShown"] = self.scale_axis == "show"
        if self.scale_axis_reverse is not None:
            cfg["scaleAxis.reverseAxis"] = bool(self.scale_axis_reverse)
        if self.scale_axis_font_size is not None:
            cfg["scaleAxis.fontSize"] = self.scale_axis_font_size
        if self.scale_axis_significant_digits is not None:
            cfg["scaleAxis.significantDigits"] = self.scale_axis_significant_digits
        if self.root_age is not None:
            cfg["scale.rootAge"] = self.root_age
        if self.scale_factor is not None:
            cfg["scale.scaleFactor"] = self.scale_factor

        if self.polar_angular_range_degrees is not None:
            cfg["polarLayout.angularRange"] = int((360 - self.polar_angular_range_degrees) * 1000)
        if self.polar_root_angle_degrees is not None:
            cfg["polarLayout.rootAngle"] = int((self.polar_root_angle_degrees - 180) * 1000)
        if self.radial_spread is not None:
            cfg["radialLayout.spread"] = self.radial_spread
        if self.curvature is not None:
            cfg["rectilinearLayout.curvature"] = self.curvature
        if self.root_length is not None:
            cfg["rectilinearLayout.rootLength"] = self.root_length

        if self.legend in ("show", "hide"):
            cfg["legend.isShown"] = self.legend == "show"
        if self.legend_position is not None:
            # ``set_legend`` capitalises the position ("Top"), so the config
            # view must use exactly the same value even when no show/hide
            # switch was requested.
            cfg["legend.position"] = self.legend_position.capitalize()

        if self.additional_config:
            cfg.update(self.additional_config)

        return cfg


def _fmt_num(value: Any) -> str:
    """Render a number like the CLI does (int without trailing '.0')."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _to_set_pair(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return f"{key}={str(value).lower()}"
    if isinstance(value, float) and value.is_integer():
        return f"{key}={int(value)}"
    return f"{key}={value.decode() if isinstance(value, bytes) else value}"
