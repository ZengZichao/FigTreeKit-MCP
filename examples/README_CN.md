# FigTreeKit-MCP 示例

> [English](README_EN.md) | **简体中文**


本目录包含三个可以直接运行的示例，演示如何在没有 AI 客户端的情况下，用
Python 调用 FigTreeKit-MCP 的同一套 MCP 工具处理器，完成
**校验 → 分析 → 样式化 → 导出 → 渲染** 全流程。

| 示例 | 用途 | 需要 Java / JAR | 需要外部数据 |
|------|------|------------------|--------------|
| `01_validate_and_summarize.py` | 树校验 + 结构摘要 | 否 | 否（内置 12 末端树） |
| `02_taxonomy_audit.py` | 分类学单系性审计 + 着色 Nexus | 否 | 否（内置嵌入分类标签） |
| `03_publication_figure.py` | 极坐标出版级图 + PNG/PDF | 默认模式需要；`--style-only` 不需要 | 否（内置树） |

三个示例默认使用同一棵内置的 12 末端树：树中嵌入了 GTDB 风格的
`p__` / `c__` 分类标签，并且特意让 `PhyC` 成为非单系门，用于演示示例二的
着色逻辑。因此无需网络、无需 GTDB 数据即可运行。

## 前置条件

- Python 3.11 或更高版本；
- 已安装运行依赖：
  ```bash
  bash scripts/setup_env.sh
  ```
  该脚本会检查 `figtreekit`（也可用 `FIGTREEKIT_SRC` 安装本地源码）、安装
  `mcp`、测试依赖与 Pillow，并以 editable 方式安装本项目；
- 仅示例三的默认渲染模式需要 Java 8+ 和 `figtree_patched.jar`。
  `figtreekit` 通常自带 `figtree_patched.jar`；可用
  `python -m figtreekit_mcp --self-test` 检查 Java/JAR；
- 不需要网络。

## 快速开始

在仓库根目录执行：

```bash
# 示例一：校验与摘要
python examples/01_validate_and_summarize.py

# 示例二：分类学审计（默认内嵌分类标签）
python examples/02_taxonomy_audit.py

# 示例三：只导出样式化 Nexus（不需要 Java）
python examples/03_publication_figure.py --style-only

# 示例三：完整渲染 PNG + PDF（需要 Java/JAR）
python examples/03_publication_figure.py
```

Windows 上如果没有 `python` 命令，请使用 `py -3.11` 或虚拟环境中的
`python.exe`。如果控制台中文显示乱码，可先设置：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

```cmd
set PYTHONIOENCODING=utf-8
```

## 使用自己的数据

三个示例都接受 `--tree` 和（可选的）`--mapping`：

```bash
python examples/01_validate_and_summarize.py --tree /absolute/path/to/tree.nwk

python examples/02_taxonomy_audit.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv

python examples/03_publication_figure.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv \
  --style-only
```

- `--tree`：Newick 或 Nexus 树文件；
- `--mapping`：当末端标签没有内嵌分类信息时使用的 TSV/CSV 映射表；
- `--rank`（示例二）：审计的分类等级，默认 `phylum`；
- `--workspace`：输出目录；不指定时使用系统临时目录。

也可以用环境变量代替命令行参数：

| 环境变量 | 含义 |
|----------|------|
| `FIGTREEKIT_MCP_TREE` | 默认树文件路径 |
| `FIGTREEKIT_MCP_MAPPING` | 默认分类映射表路径 |
| `FIGTREEKIT_MCP_WORKSPACE` | 默认输出工作目录 |

命令行参数的优先级高于环境变量。

## 输出位置与清理

示例默认在系统临时目录下创建
`figtreekit-mcp-example-<随机后缀>` 工作目录，并在启动时打印它的绝对路径。
每次工具调用会再创建 `run_<uuid8>` 子目录，产物（`.nex`、`.png`、`.pdf`）
都保存在那里，绝对路径会打印到标准输出。

如果希望保留产物，可指定固定目录：

```bash
python examples/03_publication_figure.py --workspace ./figtreekit-mcp-example-output
```

示例不会写仓库根目录下的 `figtreekit-mcp-workspace`（除非你显式把
`--workspace` 指到那里）。临时目录可以随时删除。

## 退出码

| 退出码 | 含义 |
|--------|------|
| `0` | 成功（示例三的 `--style-only` 也算成功） |
| `1` | 工具返回错误、验证失败、着色无效、或请求渲染但 Java/JAR 不可用 |
| `2` | 命令行用法错误、输入文件不存在、缺少 Python 依赖 |

示例三在请求渲染但环境缺少 Java/JAR 时会返回非零，并提示安装 Java/JAR
或改用 `--style-only`，不会静默地以 0 退出。

## 在干净 checkout 中运行

三个示例在导入包之前都会把

- 仓库根目录，以及
- `<仓库根>/src`

加入 `sys.path`，因此即使没有执行 `pip install -e .`，也能从源码导入
`figtreekit_mcp`。但 `figtreekit`、`mcp` 等第三方依赖仍需安装；推荐直接
运行 `bash scripts/setup_env.sh`。

示例通过 `create_server(...)` 先完成 21 个工具处理器的注册，再直接调用
`TOOLS[...]`。

## 文档索引

| 中文 | English |
|------|---------|
| [示例一：校验与摘要](01_validate_and_summarize_CN.md) | [Example 01](01_validate_and_summarize_EN.md) |
| [示例二：分类学审计](02_taxonomy_audit_CN.md) | [Example 02](02_taxonomy_audit_EN.md) |
| [示例三：出版级出图](03_publication_figure_CN.md) | [Example 03](03_publication_figure_EN.md) |
| [客户端配置说明](client_configs/README_CN.md) | [Client configs](client_configs/README_EN.md) |
