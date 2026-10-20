# 示例一：验证与摘要

> [English](01_validate_and_summarize_EN.md) | **简体中文**


配套脚本：[`01_validate_and_summarize.py`](01_validate_and_summarize.py)

## 目标

对一个 Newick/Nexus 树做完整检查，并输出表格：

- 格式、末端数、树数；
- 结构问题（负分支、括号不平衡、重复末端等）；
- 分支长度范围、内部节点数、是否 rooted；
- 末端标签预览。

脚本直接调用与 MCP 服务器相同的工具处理器：

1. `validate_tree`；
2. `summarize_tree`。

## 前置条件

- Python 3.11+；
- 已运行 `bash scripts/setup_env.sh`（或手动安装 `figtreekit`、`mcp`）；
- 不需要 Java/JAR；
- 不需要网络；
- 默认使用内置的 12 末端树，不需要任何外部数据文件。

## 运行

```bash
# 内置树
python examples/01_validate_and_summarize.py

# 自己的树
python examples/01_validate_and_summarize.py --tree /absolute/path/to/tree.nwk

# 用环境变量
FIGTREEKIT_MCP_TREE=/absolute/path/to/tree.nwk \
  python examples/01_validate_and_summarize.py
```

Windows PowerShell：

```powershell
py -3.11 examples/01_validate_and_summarize.py --tree "C:\data\tree.nwk"
```

## 参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `--tree` | `FIGTREEKIT_MCP_TREE` | 内置 12 末端树 | Newick/Nexus 文件 |
| `--workspace` | `FIGTREEKIT_MCP_WORKSPACE` | 系统临时目录 | 工作目录 |

## 内置树

默认树有 12 个末端、5 个门、8 个纲，标签采用 GTDB 风格，例如：

```
T1_p__PhyA_c__Cls1
T7_p__PhyC_c__Cls4
```

每个示例都使用同一棵树，便于把三个示例串起来看。

## 预期输出

以下为默认内置树的实际输出（`<workspace>` 是脚本打印的临时目录）：

```text
== FigTreeKit-MCP example 01: validate + summarize ==
input     : built-in 12-tip Newick tree
workspace : <workspace>
== validate_tree ==
  [PASS] valid=True format=newick leaf_count=12 tree_count=1
== summarize_tree ==
  format=newick tree_count=1 tips=12
  internal_nodes=9 rooted=False
  branch_lengths min=0.1 max=0.5 negative=0 has_missing=False
  tip_labels_total=12 preview(first 20)=['T1_p__PhyA_c__Cls1', 'T2_p__PhyA_c__Cls1', 'T3_p__PhyA_c__Cls2', 'T4_p__PhyA_c__Cls2', 'T5_p__PhyB_c__Cls3', 'T6_p__PhyB_c__Cls3', 'T7_p__PhyC_c__Cls4', 'T8_p__PhyD_c__Cls5', 'T9_p__PhyC_c__Cls4', 'T10_p__PhyC_c__Cls6', 'T11_p__PhyE_c__Cls7', 'T12_p__PhyE_c__Cls8']

| format | tips | trees | issues | verdict |
|--------|------|-------|--------|---------|
| newick | 12 | 1 | none (ERROR) | PASS |

Result: validation and summary passed.
```

退出码为 `0`。

## 验证标准

- `validate_tree.valid=True`，没有 ERROR；
- `leaf_count` 与 `tip_labels_total` 一致（单树时）；
- `branch_lengths.negative=0`；
- 表格中的 `tips` 与摘要一致；
- 退出码为 0。

如果树包含负分支、括号不平衡等问题，`validate_tree` 会抛出结构化错误，
脚本以退出码 1 结束，并打印错误码与详情。

## 作为 MCP 客户端使用的提示词

把下面这段交给 Claude Desktop / Cursor / VS Code 中的 AI 助手，也能得到
同样的结果：

```text
请对指定树文件做完整检查：
1. 调用 validate_tree（tree_file: <绝对路径>），若失败则逐条列出 ERROR；
2. 调用 summarize_tree（include_tip_labels=true, tip_labels_limit=20），
   汇报末端数、分支长度、是否多树；
3. 若有序列文件，再调用 cross_validate 做树与序列比对。
最后用表格汇报：格式 / 末端数 / 树数 / 问题清单 / 结论。
```

## 相关文档

- 英文版：[01_validate_and_summarize_EN.md](01_validate_and_summarize_EN.md)
- 示例总览：[README_CN.md](README_CN.md)
