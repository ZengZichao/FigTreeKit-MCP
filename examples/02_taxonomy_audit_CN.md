# 示例二：分类学审计与着色

> [English](02_taxonomy_audit_EN.md) | **简体中文**


配套脚本：[`02_taxonomy_audit.py`](02_taxonomy_audit.py)

## 目标

对一个树做门级（可改为任意等级）单系性审计，并导出一张真正带颜色的
Nexus 图：

1. `analyze_taxonomy(rank=phylum)`：统计单系/非单系类群；
2. `taxonomy_completeness`：统计分类覆盖度；
3. `style_tree`：`auto_color_rank=phylum` 着色，并对非单系门逐末端覆盖颜色；
4. 读取导出的 `.nex`，确认其中确实包含 `!color` 注释。

## 前置条件

- Python 3.11+；
- 已运行 `bash scripts/setup_env.sh`；
- 不需要 Java/JAR；
- 不需要网络；
- 默认使用内置的 12 末端树，分类信息内嵌在末端标签中；
- 如果使用自己的数据：树末端没有内嵌分类时，需要 `--mapping` 提供
  TSV/CSV 映射表。

## 运行

```bash
# 内置树（分类标签已内嵌）
python examples/02_taxonomy_audit.py

# 自己的树 + 映射表
python examples/02_taxonomy_audit.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv

# 审计 class 等级
python examples/02_taxonomy_audit.py --rank class
```

## 参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `--tree` | `FIGTREEKIT_MCP_TREE` | 内置 12 末端树 | Newick/Nexus 文件 |
| `--mapping` | `FIGTREEKIT_MCP_MAPPING` | 无 | 分类映射表（TSV/CSV） |
| `--rank` | — | `phylum` | 审计的分类等级 |
| `--workspace` | `FIGTREEKIT_MCP_WORKSPACE` | 系统临时目录 | 工作目录 |

## 关键修复：不要把门名当作末端名单

FigTreeKit 的 `color` / `color_all` 操作把 `taxa` 解析为**末端标签**。
之前的示例把门名（例如 `"PhyC"`）直接传给 `color_all`，而门名不是任何一个
末端标签，因此 FigTreeKit 找不到目标，着色静默地变成空操作。

本示例采用两条正确路径：

1. **`auto_color_rank="phylum"`**：这是 `style_tree` 的公开参数，内部调用
   `figtreekit_mcp._core.color_groups_by_result()`：
   - 单系类群：`set_clade_color_all(该组全部真实末端)`；
   - 非单系类群：对每个真实末端分别调用 `set_clade_color`。
2. **显式逐末端 `color`**：先从 `check_monophyly` 得到
   `resolved_taxa_preview`（真实末端名单），再为每个末端生成一条
   `{"op": "color", "taxa": [<单末端>], "color": "#..."}`。
   非单系类群必须逐末端操作；若把整组末端一次性传给 `color`，只会给它们的
   MRCA 分支上色，而不是每个末端。

注意：

- `analyze_taxonomy` 的 MCP 返回值只有类群名和计数，不包含完整末端名单；
  需要末端名单时使用 `check_monophyly`；
- `check_monophyly` 的预览最多 10 个末端。超过 10 个末端的类群，脚本不会
  生成显式逐末端操作，但仍由 `auto_color_rank` 在内部用完整名单着色；
- 使用 `--mapping` 时，`check_monophyly` 不接受映射表参数，因此脚本跳过
  显式逐末端覆盖，完全依赖 `auto_color_rank`（它支持映射表）；
- 门名可能带前导下划线（例如 `_PhyC`），这是 FigTreeKit 的解析结果；
  脚本显示时会去掉下划线，但传回工具时保留原名。

## 内置树

内置树有 12 个末端、5 个门：

- `PhyA`：4 个末端，单系；
- `PhyB`：2 个末端，单系；
- `PhyD`：1 个末端，单系；
- `PhyE`：2 个末端，单系；
- `PhyC`：3 个末端，**非单系**（与 `PhyD` 的末端混在一起）。

因此默认输出中 `non_monophyletic=1`。

## 预期输出

以下为默认内置树的实际输出（`<workspace>` 为脚本打印的临时目录）：

```text
== FigTreeKit-MCP example 02: taxonomy audit ==
tree      : built-in 12-tip tree (embedded taxonomy)
mapping   : none (taxonomy parsed from tip labels)
rank      : phylum
workspace : <workspace>
== analyze_taxonomy(rank=phylum) ==
  total_labels=12 mapped=12 unmapped=0
  groups=5 monophyletic=4 non_monophyletic=1 monophyly_rate=75.0%
  monophyletic    : PhyA(4), PhyB(2), PhyE(2), PhyD(1)
  non-monophyletic: PhyC(3)
== taxonomy_completeness ==
  coverage=100.0% complete=12 incomplete=0 missing=0
  rank_coverage={'phylum': 100.0, 'class': 100.0}
== style_tree (phylum auto-color + explicit non-monophyletic tips) ==
  nexus_file=<workspace>\run_<uuid8>\output.nex
  cli_command=python -m figtreekit '<workspace>\run_<uuid8>\input.tre' -o '<workspace>\run_<uuid8>\output.nex' --force --layout rectilinear --tip-labels-show --color-clade 'T7_p__PhyC_c__Cls4:#E53935' --color-clade 'T9_p__PhyC_c__Cls4:#E53935' --color-clade 'T10_p__PhyC_c__Cls6:#E53935' --auto-color phylum --taxonomy-levels d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus
  operations_applied:
    - auto_color: applied (rank=phylum, groups=5)
    - color: applied
    - color: applied
    - color: applied
[PASS] exported Nexus contains 17 !color annotation(s)
[PASS] PhyC: 3/3 non-monophyletic tips carry !color

Audit result:
| group | monophyletic | taxa_count |
|-------|--------------|------------|
| PhyA | yes | 4 |
| PhyC | no | 3 |
| PhyB | yes | 2 |
| PhyE | yes | 2 |
| PhyD | yes | 1 |

Result: taxonomy audit completed; Nexus coloring verified.
```

退出码为 `0`。

`!color` 注释数量会随树和等级变化，关键是**不是 0**，并且每个被显式覆盖的
非单系末端都带 `!color`。

## 验证标准

- 汇总行给出：总末端数（total labels）、mapped、coverage、
  monophyly_rate、问题类群数；
- 导出的 `.nex` 至少包含一个 `!color` 注释；
- 非单系类群的每个末端都带 `!color`（当完整末端名单可用时）；
- 审计表中单系/非单系标记与 `analyze_taxonomy` 一致；
- 退出码为 0。

## 常见问题

### 为什么不能用 `color_all` 直接传门名？

因为 `taxa` 只匹配末端标签。门名不是末端，`color_all` 会找不到目标，
既不报错也不着色。正确做法是传该门下的真实末端名单（单系门可用
`color_all` 整族上色；非单系门应逐末端用 `color`）。

### 为什么 `analyze_taxonomy` 不直接返回末端名单？

MCP 工具返回精简的审计摘要（类群名 + 计数），避免大树上返回数百个末端
导致响应过大。需要完整名单时，使用 `check_monophyly` 或
`auto_color_rank` 内部解析。

## 作为 MCP 客户端使用的提示词

```text
先调用 analyze_taxonomy(rank=phylum) 得到单系/非单系门，再调用
taxonomy_completeness 报告覆盖度。着色时不要直接把门名作为 taxa：
使用 style_tree(auto_color_rank="phylum")，或先用 check_monophyly 解析出
真实末端名单，再逐末端调用 color；单系门可以用 color_all 传完整末端名单。
最后读取导出的 .nex，确认包含 !color 注释，并汇报每个门的着色情况。
```

## 相关文档

- 英文版：[02_taxonomy_audit_EN.md](02_taxonomy_audit_EN.md)
- 示例总览：[README_CN.md](README_CN.md)
