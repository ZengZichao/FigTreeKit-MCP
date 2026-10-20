# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""MCP prompts: create-publication-figure / taxonomy-audit.

Both prompts are bilingual (Chinese first, English quick reference at the
end) and guide the AI through the FigTreeKit tool sequence; arguments map to
the underlying tool parameters.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

_PUBLICATION_PIPELINE = """\
# 出版级系统发育图制作流程（create-publication-figure）
# Publication-grade phylogenetic figure pipeline

请按以下固定顺序调用 FigTreeKit-MCP 工具，生成并交付一张可复用的出版级树图：
Follow this fixed tool order to produce a reproducible, publication-grade tree figure.

## ① 验证（T04 validate_tree）
- 输入：`tree_file={tree_file}`；{tree_content_note}
- 目的：确认树文件无负分支、括号平衡、重复末端等 FigTree 无法渲染的问题。
  若报错，将 `details` 中的 ERROR 项原样反馈给用户，不要继续。

## ② 摘要（T05 summarize_tree）
- 输入：同一树源
- 目的：获取 tips / internal_nodes / branch_lengths / tip_labels 预览，为样式决策
  提供依据。多树文件务必先明确 `multi_tree` 或 `tree_index`。

## ③ 分类学分析（可选，仅当末端标签含分类信息时）
- 调用 T08 `analyze_taxonomy`（rank=taxonomy_levels 中最细可用的门/纲级），
  了解群体单系性，作为配色/折叠方案依据。

## ④ 样式化（T10 style_tree）
- 布局：`layout={layout}`；常用极坐标组合
  `polar_angular_range_degrees=180, polar_root_angle_degrees=270`。
- 配色：`auto_color_rank={auto_color_rank}`（自动按门级统一调色板）。
- 折叠：`collapse_rank={collapse_rank_hint}`、`collapse_style=collapse`。
- 刻度：`scale_axis=show`、`scale_axis_reverse=false`、`scale_axis_font_size=12`。
- 建议同时请求 `tip_labels` 显隐与 `legend`，保证可读性。
- 必须把返回的 `cli_command` 与 `config_json` 原样保留（可复现性红线）。

## ⑤ 渲染（T20 render_tree）
- 使用 ④ 返回的 `nexus_file.absolute`，按 `render_formats={render_formats}`
  依次渲染：`format="PNG"`（预览，附 data_uri）与 `format="PDF"`（出版用矢量）。
- 尺寸建议 2400×1600；如需要可 `background_color="#FFFFFF"`。

## ⑥ 交付
- 汇报产物绝对路径（`run_dir/` 下）、`cli_command`、`config_json` 摘要说明。
- 若某步失败，返回错误信封的关键字段（code/error_key）与修复建议。

## English quick reference
1. T04 validate_tree → 2. T05 summarize_tree → 3. T08 analyze_taxonomy (optional)
   → 4. T10 style_tree → 5. T20 render_tree → 6. report artifacts.
- Keep the returned `cli_command` and `config_json` verbatim (reproducibility).
- Report absolute artifact paths under `run_dir/` and the CLI command.
- On failure, return the error-envelope fields (code / error_key) plus a fix.
"""

_TAXONOMY_AUDIT = """\
# 分类学单系性审计（taxonomy-audit）
# Taxonomic monophyly audit

请依据树源与目标等级 `rank={rank}` 执行结构化审计：
Run a structured audit for the tree source below, targeting `rank={rank}`.

树源 / Tree source: `tree_file={tree_file}`；{tree_content_note}

## 1. 数据就绪（T04 validate_tree → T05 summarize_tree）
- 验证 + 摘要，确认 tips 数量、是否存在 translate block。
- 若需要映射文件：要求用户提供 whitelisted 的 `taxonomy_mapping_file`。

## 2. 批量单系性分析（T08 analyze_taxonomy）
- `rank=<目标等级>`；记录 summary.monophyly_rate 与
  monophyletic/non_monophyletic 两类清单（含 taxa_count）。

## 3. 完整性核查（T09 taxonomy_completeness）
- 记录 coverage 与缺失标签清单，与 T08 的 unmapped_labels 交叉核对。

## 4. 单项深查（T07 check_monophyly，按需）
- 对用户点名的类群做深查；支持 LUCA / LACA / LBCA / root 特殊标识。

## 5. 输出结构化审计表（中文表格）
```
| 类群 | monophyletic | taxa_count | 备注 |
|------|--------------|------------|------|
| ...  | ✓/✗          | N          | ...  |
```
- 汇总行给出：总 taxa、mapped、coverage、monophyly_rate、问题类群数。

## 6. 可视化建议（可选）
- 用 T10 style_tree 的 `operations` 给非单系群逐末端着色
  （op=color_all / color），生成差异可视化 `.nex`。

## English quick reference
1. T04 validate_tree → 2. T05 summarize_tree → 3. T08 analyze_taxonomy →
   4. T09 taxonomy_completeness → 5. T07 check_monophyly (on demand) →
   6. optional T10 style_tree highlight of non-monophyletic groups.
- Report a table with group / monophyletic / taxa_count, plus coverage,
  monophyly_rate and the list of problematic groups.
"""


def _tree_source_note(tree_file: Optional[str], tree_content: Optional[str]) -> str:
    """Describe which tree source the caller supplied (bilingual)."""
    if tree_content:
        return "已内联 tree_content（优先使用）/ inline tree_content provided"
    if tree_file:
        return "使用 tree_file（见上）/ using the tree_file above"
    return "未提供树源，请向用户索取 / no tree source supplied, ask the user"


def register(mcp: FastMCP) -> None:
    """Register the two prompts on the server."""

    @mcp.prompt(name="create-publication-figure")
    def create_publication_figure(
        tree_file: Optional[str] = None,
        tree_content: Optional[str] = None,
        layout: Optional[str] = "polar",
        collapse_rank: Optional[str] = "class",
        render_formats: Optional[str] = "PNG,PDF",
    ) -> str:
        """引导 AI 完成 验证→摘要→分析→样式化→渲染 的出版级出图流程。

        Guide the AI through validate → summarize → analyze → style → render
        for a publication-grade figure.
        """
        return _PUBLICATION_PIPELINE.format(
            tree_file=tree_file or "<请提供树文件路径 / provide a tree file>",
            tree_content_note=_tree_source_note(tree_file, tree_content),
            layout=layout or "polar",
            auto_color_rank=collapse_rank or "phylum",
            collapse_rank_hint=collapse_rank or "class",
            render_formats=render_formats or "PNG,PDF",
        )

    @mcp.prompt(name="taxonomy-audit")
    def taxonomy_audit(
        tree_file: Optional[str] = None,
        tree_content: Optional[str] = None,
        rank: Optional[str] = "phylum",
    ) -> str:
        """引导 AI 输出分类学单系性审计表（批量分析 + 完整性 + 可视化）。

        Guide the AI to produce a taxonomic monophyly audit table (batch
        analysis + completeness + optional visualisation).
        """
        return _TAXONOMY_AUDIT.format(
            rank=rank or "phylum",
            tree_file=tree_file or "<请提供树文件路径 / provide a tree file>",
            tree_content_note=_tree_source_note(tree_file, tree_content),
        )


__all__ = ["register"]
