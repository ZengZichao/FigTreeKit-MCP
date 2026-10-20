# 示例三：出版级出图

> [English](03_publication_figure_EN.md) | **简体中文**


配套脚本：[`03_publication_figure.py`](03_publication_figure.py)

## 目标

复现「极坐标布局 + 纲级折叠（cartoon）+ 门级着色 + 刻度轴」的出版级图：

1. `summarize_tree` 确认树的规模；
2. `style_tree`：`layout=polar`、`auto_color_rank=phylum`、
   `collapse_rank=class`、`collapse_style=cartoon`、`scale_axis=show`，
   导出 `.nex`；
3. `render_tree`：渲染 PNG（2400x1600）和 PDF。

## 两种模式

| 模式 | 命令 | 是否需要 Java/JAR | 退出码 |
|------|------|--------------------|--------|
| 只导出样式化 Nexus | `--style-only` | 否 | 成功 0 |
| 完整渲染 PNG + PDF | 默认（不加参数） | 是 | 成功 0；失败 1 |

默认模式在渲染不可用（缺少 Java 或 JAR）时**返回非零**，不会静默成功。
如果当前环境没有 Java/JAR，请使用 `--style-only`，或先安装 Java 8+ 与
`figtree_patched.jar`。

## 前置条件

- Python 3.11+；
- 已运行 `bash scripts/setup_env.sh`；
- 默认模式额外需要：
  - Java 8+ 在 `PATH` 中（或设置 `JAVA_HOME`）；
  - `figtree_patched.jar`（`figtreekit` 通常自带；也可用 `setup_figtree` 安装）；
- 不需要网络；
- 默认使用内置的 12 末端树。

检查 Java/JAR：

```bash
python -m figtreekit_mcp --self-test
```

输出中应包含 `[PASS] Java 探测` 和 `[PASS] JAR 探测`。也可以调用
`check_figtree` 工具查看详细提示。

## 运行

```bash
# 只导出 .nex（不需要 Java）
python examples/03_publication_figure.py --style-only

# 完整渲染 PNG + PDF
python examples/03_publication_figure.py

# 自己的树 + 映射表
python examples/03_publication_figure.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv \
  --style-only
```

## 参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `--tree` | `FIGTREEKIT_MCP_TREE` | 内置 12 末端树 | Newick/Nexus 文件 |
| `--mapping` | `FIGTREEKIT_MCP_MAPPING` | 无 | 分类映射表（TSV/CSV） |
| `--style-only` | — | 关闭 | 只导出 `.nex`，跳过渲染 |
| `--workspace` | `FIGTREEKIT_MCP_WORKSPACE` | 系统临时目录 | 工作目录 |

## 预期输出：`--style-only`

以下为默认内置树的实际输出（`<workspace>` 为脚本打印的临时目录）：

```text
== FigTreeKit-MCP example 03: publication figure ==
tree      : built-in 12-tip tree (embedded taxonomy)
mapping   : none (taxonomy parsed from tip labels)
mode      : style-only (no Java/JAR)
workspace : <workspace>
== summarize_tree ==
  tips=12 tree_count=1 format=newick
== style_tree (polar + class collapse/cartoon + phylum colors) ==
  nexus_file=<workspace>/run_<uuid8>/output.nex
  cli_command=python -m figtreekit '<workspace>/run_<uuid8>/input.tre' -o '<workspace>/run_<uuid8>/output.nex' --force --layout polar --tip-labels-hide --scale-axis-show --angular-range 180 --root-angle 90 --set scaleAxis.reverseAxis=false --set scaleAxis.fontSize=14 --set scaleAxis.significantDigits=2 --collapse-rank class --collapse-style cartoon --auto-color phylum --taxonomy-levels d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus
  operation: auto_color=applied (rank=phylum, groups=5)
  operation: collapse_rank=applied (rank=class, applied_count=7)
[PASS] exported Nexus contains the expected style annotations
== render_tree ==
  skipped (--style-only)

Artifacts:
  nexus: <workspace>/run_<uuid8>/output.nex
Result: styled Nexus exported; rendering skipped (exit 0).
```

退出码为 `0`。

## 预期输出：完整渲染

```text
== FigTreeKit-MCP example 03: publication figure ==
tree      : built-in 12-tip tree (embedded taxonomy)
mapping   : none (taxonomy parsed from tip labels)
mode      : render PNG + PDF
workspace : <workspace>
== summarize_tree ==
  tips=12 tree_count=1 format=newick
== style_tree (polar + class collapse/cartoon + phylum colors) ==
  nexus_file=<workspace>/run_<uuid8>/output.nex
  cli_command=python -m figtreekit '<workspace>/run_<uuid8>/input.tre' -o '<workspace>/run_<uuid8>/output.nex' --force --layout polar --tip-labels-hide --scale-axis-show --angular-range 180 --root-angle 90 --set scaleAxis.reverseAxis=false --set scaleAxis.fontSize=14 --set scaleAxis.significantDigits=2 --collapse-rank class --collapse-style cartoon --auto-color phylum --taxonomy-levels d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus
  operation: auto_color=applied (rank=phylum, groups=5)
  operation: collapse_rank=applied (rank=class, applied_count=7)
[PASS] exported Nexus contains the expected style annotations
== render_tree ==
  PNG: <workspace>/run_<uuid8>/output.png (2400x1600, 52906 bytes)
  PDF: <workspace>/run_<uuid8>/output.pdf (2310 bytes)

Artifacts:
  nexus: <workspace>/run_<uuid8>/output.nex
  PNG: <workspace>/run_<uuid8>/output.png
  PDF: <workspace>/run_<uuid8>/output.pdf
Result: styled Nexus and rendered images produced.
```

退出码为 `0`。PNG/PDF 的字节数会因字体与 Java 版本略有不同，PNG 尺寸应严格
为 2400x1600。

## 渲染不可用时的行为

如果默认模式缺少 Java 或 JAR，脚本会打印类似：

```text
== render_tree ==
[FAIL] render PNG: java_missing: 渲染需要 Java 8+，但当前环境未找到 java
       Java not found in PATH
  hint: install Java 8+ and figtree_patched.jar (TOOLS check_figtree / setup_figtree), or rerun with --style-only.
```

并以退出码 `1` 结束。此时 `.nex` 已经生成，可以改用 `--style-only` 或安装
Java/JAR 后重试。

## 验证标准

- `.nex` 文件存在且包含 `!color` 注释；发生折叠时还包含 `!collapse`（collapse）
  或 `!cartoon`（cartoon）注释；
- `--style-only` 退出码为 0；
- 默认模式成功时 PNG 与 PDF 都存在，PNG 尺寸为 2400x1600；
- 默认模式渲染失败时退出码非 0；
- `cli_command` 可以逐字粘贴到 shell 复现同一 `.nex`（等价性红线）。

## Windows 说明

- PowerShell 中路径用引号包裹；
- 如果 Java 在自定义目录，请在启动 MCP 客户端前设置 `JAVA_HOME`；
- 控制台乱码时设置 `$env:PYTHONIOENCODING = "utf-8"`。

## 相关文档

- 英文版：[03_publication_figure_EN.md](03_publication_figure_EN.md)
- 示例总览：[README_CN.md](README_CN.md)
