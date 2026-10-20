# 工具脚本

> [English](README_EN.md) | **简体中文**


本目录包含 4 个开发/验收工具脚本，均可从仓库根目录运行：

| 脚本 | 用途 | 需要网络/外部数据 |
|------|------|--------------------|
| `gtdb_acceptance.py` | GTDB R232 真实数据五步端到端验收（AC-12） | 需要 GTDB 数据；缺失时 SKIP |
| `mcp_debug_client.py` | stdio MCP 调试客户端 | 否 |
| `equivalence_probe.py` | MCP / CLI / API 三方等价性探针（AC-6/7） | 需要输入树 + 分类表 |
| `ref_test_gen.py` | 用 figtreekit Python API 生成 6 组黄金参数 `.nex` 基准 | 需要输入树 + 分类表 |

所有脚本都会把仓库根目录和 `<仓库根>/src` 加入 `sys.path`，因此在干净
checkout 中不需要先 `pip install -e .`（第三方依赖仍需安装）。脚本不依赖
硬编码的绝对路径。

## `gtdb_acceptance.py`

### 用途

用真实 GTDB R232 数据（`ar53_r232.tree` + `ar53_r232_taxonomy.tsv`）执行
五步验收：

| 步骤 | 检查 |
|------|------|
| 1 | `validate_tree` 通过，末端数 >= 700 |
| 2 | `analyze_taxonomy(class)` 的计数与 `figtreekit --analyze-taxonomy class` CLI 输出一致 |
| 3 | `style_tree(polar, phylum)` 的 `.nex` 与 CLI 逐字节一致 |
| 4 | `render_tree` PNG 2400x1600 + PDF 存在、尺寸正确、非空白 |
| 5 | `collapse_rank(class)` 的 `.nex` 与 CLI 逐字节一致，且包含 `!collapse` |

步骤 2/3/5 都会真正执行 CLI 并比较计数或 SHA-256，不是“非空即通过”。
步骤 4 用灰度直方图判断非空白（非白像素比例 + 灰度标准差），不会把纯白
或纯色图误判为成功。

### 输入

- `--read-root <目录>`：包含 `ar53_r232.tree` 与
  `ar53_r232_taxonomy.tsv` 的目录；
- 或环境变量 `FIGTREEKIT_GTDB_DIR` / `FIGTREEKIT_MCP_GTDB_DIR`；
- 未指定时会尝试仓库旁边的
  `FigTreeKit-参考文件/参考数据-GTDB-R232`；
- `--workspace-root <目录>`：可选，默认使用系统临时目录；
- `--no-render`：显式跳过步骤 4（适用于没有 Java/JAR 的环境）。

### 运行

```bash
python tools/gtdb_acceptance.py --read-root /absolute/path/to/参考数据-GTDB-R232

FIGTREEKIT_GTDB_DIR=/absolute/path/to/参考数据-GTDB-R232 \
  python tools/gtdb_acceptance.py

python tools/gtdb_acceptance.py --read-root /path/to/data --no-render
```

### 退出码

| 退出码 | 含义 |
|--------|------|
| `0` | 五步全部通过（`--no-render` 的显式 SKIP 允许） |
| `1` | 任一步失败 |
| `2` | 命令行用法错误 |
| `3` | SKIP：GTDB 数据目录或文件缺失 |

数据缺失时输出示例：

```text
[SKIP] GTDB R232 data not found - acceptance cannot run.
       Provide the directory with one of:
         python tools/gtdb_acceptance.py --read-root /path/to/参考数据-GTDB-R232
         FIGTREEKIT_GTDB_DIR=/path/to/参考数据-GTDB-R232 python tools/gtdb_acceptance.py
       Expected files: ar53_r232.tree, ar53_r232_taxonomy.tsv
```

成功时输出示例（真实 GTDB 数据的数字会不同）：

```text
gtdb_acceptance (GTDB R232) - AC-12
data      : <data dir>
workspace : <workspace>
------------------------------------------------------------------------
[PASS] step 1: validate_tree ok: leaves=704, trees=1, format=newick
[PASS] step 2: analyze_taxonomy(class) == CLI: labels=704, mapped=704, groups=64, mono=64, non_mono=0, rate=100.0%
[PASS] step 3: style_tree .nex == CLI .nex (sha256 02e779a7f8a3)
[PASS] step 4: render_tree PNG 2400x1600 + PDF ok (non-white=100.00%, pdf=24965 B)
[PASS] step 5: collapse_rank(class) collapsed=64, .nex == CLI (sha256 9030a8a2bcd4)
------------------------------------------------------------------------
RESULT: ALL PASS
```

> 说明：`collapse_rank` 工具返回的 `cli_command` 目前缺少
> `--taxonomy-levels` / `--taxonomy-mapping-file`（源码限制），因此步骤 5
> 不直接使用该字符串，而是显式构造等价 CLI 参数进行逐字节比较。

## `mcp_debug_client.py`

### 用途

通过官方 `mcp` Python SDK 启动真实服务器子进程（stdio），用于：

- 列出工具；
- 调用工具（JSON 参数）；
- 读取资源；
- 导出工具 JSON Schema；
- 获取 Prompt。

### 输入与环境变量

| 参数/变量 | 说明 |
|-----------|------|
| `--list-tools` | 列出全部工具（应为 21 个） |
| `--call TOOL JSON` | 调用工具，例如 `--call validate_tree '{"tree_content":"(A:1,B:1);"}'` |
| `--read-resource URI` | 例如 `figtreekit://version` |
| `--dump-schema` | 输出所有工具的 JSON Schema |
| `--prompt NAME` | 例如 `create-publication-figure` |
| `--workspace-root` | 默认 `$FIGTREEKIT_MCP_WORKSPACE` 或 `<仓库>/figtreekit-mcp-workspace` |
| `--allow-read-root` | 可重复；默认读取 `$FIGTREEKIT_MCP_READ_ROOTS`（用 `os.pathsep` 分隔，Windows 为 `;`，POSIX 为 `:`） |

### 运行

```bash
# 工具列表
python tools/mcp_debug_client.py --list-tools

# 读取版本资源
python tools/mcp_debug_client.py --read-resource figtreekit://version

# 直接传树内容，不需要文件白名单
python tools/mcp_debug_client.py \
  --call validate_tree '{"tree_content": "(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"}'

# 调用文件相关工具时添加只读根
python tools/mcp_debug_client.py \
  --allow-read-root /absolute/path/to/tree-data \
  --call summarize_tree '{"tree_file": "/absolute/path/to/tree-data/tree.nwk"}'
```

### 输出与退出码

成功时 JSON 输出到 stdout；服务器日志在 stderr。退出码：

- `0`：成功；
- `1`：工具返回 `isError=true`，或客户端/服务器异常；
- `2`：用法错误、JSON 解析失败或缺少 `mcp` 依赖。

## `equivalence_probe.py`

### 用途

对 6 组“黄金参数”执行三方等价性检查：

1. **API 基准**：直接调用 figtreekit `FigTreeStyler`；
2. **CLI 基准**：`python -m figtreekit ...`；
3. **MCP 基准**：`style_tree` 处理器；

检查项：

- MCP `.nex` 与 CLI `.nex` 逐字节一致；
- MCP/CLI 与 API 基准在规范化树名后语义一致；
- 若 Java/JAR 可用，比较 MCP 渲染 PNG 与直接 `java -jar` PNG 的像素统计，
  差异 < 0.5%。

### 输入

```bash
python tools/equivalence_probe.py <input.tree> <taxonomy.tsv> <workspace_root>
```

- `input.tree`：Newick/Nexus 树；
- `taxonomy.tsv`：分类映射表；
- `workspace_root`：输出目录（会写入 6 组渲染对比图）。

依赖 `ref_test_gen.py`（同目录）。需要 `figtreekit`、`pillow`；渲染对比
还需要 Java/JAR（缺失时会记录 skip）。

### 输出与退出码

```text
equivalence probe: ALL PASS
  [PASS] radial_full: MCP .nex == CLI .nex (byte-for-byte)
  ...
```

- `0`：全部通过；
- `1`：存在差异；
- `2`：参数不足或输入文件不存在。

## `ref_test_gen.py`

### 用途

用 figtreekit Python API 生成 6 组黄金参数的 `.nex` 基准：

1. radial，完整展开；
2. polar，完整展开；
3. polar，class 折叠，cartoon；
4. polar，class 折叠，collapse；
5. rectilinear，phylum 折叠，cartoon；
6. rectilinear，phylum 折叠，collapse。

### 输入

```bash
python tools/ref_test_gen.py <input.tree> <taxonomy.tsv> <out_dir>
```

### 输出与退出码

每个参数集输出 `<out_dir>/<key>.nex`，并打印：

```text
generated radial_full: <out_dir>/radial_full.nex
...
```

- `0`：成功；
- `1`：输入文件不存在；
- `2`：参数不足。

## 说明

- 所有脚本都可以用 `python -m py_compile` 做语法检查：
  ```bash
  python -m py_compile tools/gtdb_acceptance.py tools/mcp_debug_client.py \
    tools/equivalence_probe.py tools/ref_test_gen.py
  ```

## 相关文档

- 英文版：[README_EN.md](README_EN.md)
- 示例总览：[../examples/README_CN.md](../examples/README_CN.md)
- 脚本说明：[../scripts/README_CN.md](../scripts/README_CN.md)
