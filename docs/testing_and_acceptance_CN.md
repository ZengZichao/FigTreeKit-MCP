# 测试与验收

**简体中文** | [English](testing_and_acceptance_EN.md)

适用版本：**0.1.0**。本文说明测试布局、运行方式、覆盖率、自检、等价性探针、GTDB 验收脚本、调试客户端，以及如何复现 AC/SEC 检查。**跳过（skip）不是通过**；真实数据缺失时，相关结论不能宣称已验证。

## 1. 测试布局

`tests/` 使用 pytest，`pyproject.toml` 设置 `asyncio_mode = "auto"`、`testpaths = ["tests"]`，并注册唯一自定义 marker：`slow`。

| 文件 | 覆盖内容 |
|------|----------|
| `conftest.py` | 共享 fixture：小树/分类树/多树/FASTA/FASTQ 文本、临时工作区、`AppContext`、假 `Context`、`call` 便捷函数、真实数据发现与跳过 |
| `test_environment_tools.py` | T01–T03：版本形状、Java/JAR 探测、check/setup 的 check_only |
| `test_validate_tools.py` | T04–T06：Newick/Nexus/FASTA/FASTQ、负分支、多树、交叉验证、translate block |
| `test_analyze_tools.py` | T07–T09：末端名单/类群名单、strict、映射表、GTDB 条件测试 |
| `test_style_tools.py` | T10–T12：导出、`cli_command`、`config_json`、极坐标、多树、run_name、示例/GTDB 条件测试 |
| `test_clade_tools.py` | T13–T19：高亮/颜色/字体/折叠/清除、错误键、GTDB 条件测试 |
| `test_render_tools.py` | T20：输入校验、错误信封；PNG/SVG 真实渲染（Java 不可用时跳过） |
| `test_passthrough.py` | T21：argv 限制、输出改写、零 shell、真实样式命令、`--help`、失败信封、输入白名单 |
| `test_params.py` | `ParamSpec` 校验、`to_cli_args`、`to_config_dict`、操作渲染、枚举稳定性 |
| `test_cli_command.py` | 命令拼接、`#RRGGBB` 引号、`shlex` 往返 |
| `test_errors.py` | 19 个错误码、异常映射、信封形状、`guard` |
| `test_logging.py` | 日志级别、stderr、`--log-file`、ISO 时间戳、handler 去重 |
| `test_cli_entry.py` | 启动参数默认值、回环限制、`--version`、`--self-test`、退出码 |
| `test_workspace.py` | 根目录、白名单、软链接、`..`、大小限额、run 清理、产物注册 |
| `test_workspace_hardening.py` | 工作区/路径加固的补充边界用例 |
| `test_security.py` | SEC-1…SEC-12（见 §7） |
| `test_concurrency.py` | 全局锁原语、并发样式/CLI、run 目录隔离 |
| `test_taxonomy_concurrency.py` | taxonomy rank-prefix 作用域的并发隔离与恢复（防全局状态泄漏） |
| `test_property_hypothesis.py` | Hypothesis 属性测试：参数校验只抛 `ToolError`、任意颜色/操作不崩溃 |
| `test_server_smoke.py` | 真实 stdio 子进程 E2E：握手、21 工具、资源/Prompt、典型调用、错误路径、取消、关闭、stdout 纯净 |
| `test_equivalence.py` | 6 组黄金参数慢速等价性（需要展示树，标记 `slow`） |

测试数会随开发变化；用 `python -m pytest --collect-only -q` 获取当前准确数量，不要在文档中把某个历史数字当作常量。

## 2. 运行测试

先安装开发依赖（见开发指南）：

```bash
python -m pip install -e ".[dev,render]"
```

常用命令：

```bash
# 全部测试
python -m pytest -q

# 排除慢速测试
python -m pytest -q -m "not slow"

# 仅慢速测试（等价性/真实渲染）
python -m pytest -q -m slow

# 只跑 E2E 协议
python -m pytest -q tests/test_server_smoke.py

# 只跑安全验收
python -m pytest -q tests/test_security.py

# 覆盖率（配置目标 80%）
python -m pytest -q --cov=figtreekit_mcp --cov-report=term-missing

# 自检
python -m figtreekit_mcp --self-test

# 收集数量
python -m pytest --collect-only -q
```

Windows 下如果 `pytest` 不在 `PATH`，使用 `python -m pytest`；在未激活环境时使用 `<python> -m pytest`。在中文 Windows 上若设置了 `PYTHONIOENCODING=utf-8`，请同时设置 `PYTHONUTF8=1`，使父进程与子进程使用一致的 UTF-8 编码。

`pyproject.toml` 设置了 `timeout = 1800` 与 `timeout_method = "thread"`：单个测试最多 1800 秒，避免慢速 JVM 渲染被误判为卡死，同时仍能兜住真正挂起的测试。

## 3. 覆盖率

`pyproject.toml` 中：

```toml
[tool.coverage.run]
source = ["figtreekit_mcp"]
omit = ["*/tests/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

目标是 **80%**。注意：

- `--self-test`、E2E 子进程和 XML/stdio 协议路径可能不会被进程内 coverage 统计；
- 排除慢速/E2E 后的子集覆盖率与全量覆盖率不同，报告中应注明命令；
- 覆盖率门限为 **80%**；实际数值以当前测试输出为准，换用不同子集时请重新测量并注明命令；
- 覆盖率达标不等于行为正确，仍需检查跳过项和真实数据测试。

## 4. `--self-test`

```bash
python -m figtreekit_mcp --self-test \
  --workspace-root "<workspace>"
```

检查项：

1. 依赖可导入：`mcp`、`figtreekit`、`Bio`；
2. 工具注册恰为 21 个，且名称集合完整；
3. 源码无裸 `print()` 写 stdout（排除 `_cli.py`/`__main__.py` 的终端输出）；
4. Java 探测（缺失为 `[WARN]`，不失败）；
5. JAR 探测（缺失为 `[WARN]`，不失败）；
6. 小树 `style_tree` → `.nex` 往返；
7. 工作区可写 + 越权路径被拒绝；
8. Java 可用时做 PNG 渲染（不可用则 `[WARN] 跳过`）。

全部通过返回 0；任一失败返回 1。Java/JAR 缺失只影响渲染项，不阻止其他能力。

## 5. 测试数据与跳过含义

### 5.1 自动发现路径

`tests/conftest.py` 从 `tests/` 向上最多 6 层查找：

- GTDB：`FigTreeKit-参考文件/参考数据-GTDB-R232/`
  - 需要 `ar53_r232.tree`、`ar53_r232_taxonomy.tsv`、`ar53_r232_class.tree`、`ar53_r232_phylum.tree` 等；
- 展示数据：`FigTreeKit-功能展示/输入文件/FigTree_withLACA_CLK_95CI.tree.recover` 与 `.tsv`。

典型布局：

```text
<parent>/
├── <repo>/                      ← 本仓库
├── FigTreeKit-参考文件/
│   └── 参考数据-GTDB-R232/
└── FigTreeKit-功能展示/
    └── 输入文件/
        ├── FigTree_withLACA_CLK_95CI.tree.recover
        └── FigTree_withLACA_CLK_95CI.tsv
```

如果目录不存在，fixture 调用 `pytest.skip(...)`。由于 fixture 依赖顺序，缺少 GTDB 目录时你可能看到“`参考数据-GTDB-R232 目录不存在`”或“`ar53_r232_phylum.tree 缺失`”等不同消息；两者都表示真实数据不可用。

### 5.2 跳过类型

| 跳过原因 | 影响 |
|----------|------|
| GTDB 目录/文件缺失 | T07–T09、T10、T17/T18 的 GTDB 集成测试跳过 |
| 展示树/TSV 缺失 | 展示树样式/校验测试、`test_equivalence.py` 跳过 |
| Java 不可用 | `test_render_tools.py` 的 PNG/SVG 真实渲染跳过 |
| 渲染依赖缺失 | SEC-9 真实渲染超时测试跳过 |
| 没有 match | pytest marker 过滤（如 `-m "not slow"`）导致的选择性跳过 |

**跳过不是通过**：报告中应分别写“passed / failed / skipped”，并说明跳过原因。真实数据验收（AC-4/5/6/12）在没有数据时只能说“未验证”。

### 5.3 手动提供数据

- 把数据放到上述相对位置；或
- 对测试 fixture 修改环境（不推荐直接改测试）；或
- 对独立脚本使用显式 `--read-root` / `--allow-read-root`。

`tools/gtdb_acceptance.py` 会从 `--read-root`、`FIGTREEKIT_GTDB_DIR`、`FIGTREEKIT_MCP_GTDB_DIR` 或同级目录解析数据位置；`tools/mcp_debug_client.py` 的只读根来自重复的 `--allow-read-root` 或 `FIGTREEKIT_MCP_READ_ROOTS`。为可复现起见，**建议始终显式传 `--read-root`/`--allow-read-root`**。

## 6. 调试客户端 `tools/mcp_debug_client.py`

以真实 stdio 子进程启动服务器，使用官方 `mcp` 客户端：

```bash
# 列出 21 个工具
python tools/mcp_debug_client.py --list-tools \
  --workspace-root "<workspace>" \
  --allow-read-root "<data-dir>"

# 调用工具（JSON 参数）
python tools/mcp_debug_client.py --call summarize_tree \
  '{"tree_content":"(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"}' \
  --workspace-root "<workspace>"

# 读取资源
python tools/mcp_debug_client.py --read-resource figtreekit://version \
  --workspace-root "<workspace>"

# 导出全部工具的 JSON Schema
python tools/mcp_debug_client.py --dump-schema --workspace-root "<workspace>"

# 获取 Prompt
python tools/mcp_debug_client.py --prompt create-publication-figure \
  --workspace-root "<workspace>"
```

- `--call` 的第二个参数是 JSON 字符串；空对象用 `{}`。
- `--allow-read-root` 可重复；省略时读取 `FIGTREEKIT_MCP_READ_ROOTS`（按 `os.pathsep` 分隔）或为空，建议始终显式传入。
- 输出为 `{"isError": ..., "content": [...]}`；错误信封可能在 `content[0]` 中且 `isError=false`，需要解析 JSON。
- 退出码：0 成功，1 工具返回 `isError=true`，2 用法错误；`KeyboardInterrupt` 返回 130。

## 7. SEC-1…SEC-12 对照

`tests/test_security.py` 当前覆盖：

| 编号 | 检查 | 测试要点 |
|------|------|----------|
| SEC-1 | 路径穿越 | `../../../../etc/passwd` 被 `access_denied` 拒绝 |
| SEC-2 | 软链接逃逸 | 只读根内软链接指向根外被拒绝 |
| SEC-3 | `run_name` 穿越 | `../../evil` 触发 `param_validation_failed` |
| SEC-4 | 输出改写 | `-o /tmp/x.nex`、`-o ../../escaped.nex` 被改写进 run 目录并披露 |
| SEC-5 | 控制字符/双向文本 | NUL、`U+202E` 被 `anomalous_content` 拒绝 |
| SEC-6 | 大小限额 | 11 MiB 内容触发 `input_too_large` |
| SEC-7 | 零 shell | `;`/`$(...)`/`|`/`&&` 作为普通参数，不执行 |
| SEC-8 | 并发隔离 | 8 个样式 + 2 个 CLI 并发，各自独立 run 目录 |
| SEC-9 | 渲染超时 | 确定性注入超时错误并断言 `render_timeout`；Java/JAR 缺失时跳过 |
| SEC-10 | Java 缺失 | `java_missing` 与提示 |
| SEC-11 | JAR 缺失 | `jar_missing` 与 `setup_figtree` 提示 |
| SEC-12 | stdout 纯净 | 源码静态扫描无裸 `print()` |

运行：

```bash
python -m pytest -q tests/test_security.py
```

## 8. 等价性探针 `tools/equivalence_probe.py`

用途：对 6 组黄金参数，比较：

1. **API 基准**：直接用 figtreekit Python API；
2. **CLI 基准**：`python -m figtreekit`；
3. **MCP 基准**：`style_tree` handler；
4. 断言 MCP `.nex` 与 CLI `.nex` **逐字节相同**；
5. 断言 MCP/CLI 在归一化树名/索引后与 API 基准语义相同；
6. 可选：MCP 渲染 PNG 与 `java -jar` 直出 PNG 的像素统计差 <0.5%。

用法：

```bash
python tools/equivalence_probe.py \
  "<showcase-tree>" \
  "<taxonomy.tsv>" \
  "<workspace>"
```

要求：

- 展示树与 TSV 存在（例如 `FigTreeKit-功能展示/输入文件/FigTree_withLACA_CLK_95CI.*`）；
- 渲染比较需要 Java + JAR + Pillow；缺失时该项返回 “render skipped” 并视为通过；
- 退出码 0 = 全部检查通过，1 = 有失败，2 = 参数不足；
- 脚本不暴露 `--only` 命令行参数；`run_probe(..., only=[...])` 仅在 Python 中可用。

`tests/test_equivalence.py` 是该探针的 pytest 入口，两个用例都标记 `slow`：一个 `check_render=False`，一个 `check_render=True`。没有展示数据时 fixture 跳过；数据存在时可能运行较久，建议给足超时。

## 9. GTDB 五步验收 `tools/gtdb_acceptance.py`

```bash
python tools/gtdb_acceptance.py \
  --read-root "<GTDB-R232-dir>" \
  --workspace-root "<workspace>"
# 无 Java/JAR 时跳过渲染步骤
python tools/gtdb_acceptance.py \
  --read-root "<GTDB-R232-dir>" \
  --workspace-root "<workspace>" --no-render
```

需要输入目录中有 `ar53_r232.tree` 与 `ar53_r232_taxonomy.tsv`。数据目录按 `--read-root`、`FIGTREEKIT_GTDB_DIR`、`FIGTREEKIT_MCP_GTDB_DIR` 或同级目录的顺序解析；找不到时打印 `[SKIP]` 并返回 **3**（不是失败）。`--workspace-root` 省略时使用临时目录；`--no-render` 显式跳过第 4 步（无 Java/JAR 时使用）。

五步的**实际**检查：

| 步骤 | 调用 | 实际断言 |
|------|------|----------|
| 1 | `validate_tree` | `ok=true` 且 `leaf_count >= 700` |
| 2 | `analyze_taxonomy(rank=class)` | 解析 `figtreekit --analyze-taxonomy class` 的输出，逐项比较 `total_labels`、`mapped_labels`、`total_groups`、`monophyletic`、`non_monophyletic`、`monophyly_rate` |
| 3 | `style_tree(polar, phylum)` | 要求 `cli_command` 含 `--taxonomy-levels`/`--taxonomy-mapping-file`；用该命令重新生成 `.nex`，与 MCP `.nex` **逐字节比较** |
| 4 | `render_tree(PNG 2400×1600 + PDF)` | PNG 尺寸正确、非空白（非白像素比例与灰度标准差检查）；PDF 以 `%PDF-` 开头。缺少 Java/JAR 时该步失败；只能用 `--no-render` 显式跳过 |
| 5 | `collapse_rank(class)` | 要求 `collapsed_groups > 0` 且 `.nex` 含 `!collapse`；用等价的 CLI argv 生成 `.nex` 并**逐字节比较** |

因此，AC-12 在数据存在时包含与 CLI 的逐字节对比；数据缺失时脚本返回 `[SKIP]`/退出码 3，此时不能宣称 AC-12 通过。脚本默认使用临时工作区，数据目录建议显式传入以便复现。

## 10. AC-1…AC-12 复现命令

| AC | 命令/证据 | 说明 |
|----|-----------|------|
| AC-1 | `python -m figtreekit_mcp --self-test`；`python -c "import mcp, figtreekit, Bio, PIL"` | 依赖导入；Pillow 可选 |
| AC-2 | `python tools/mcp_debug_client.py --list-tools ...`；`pytest tests/test_server_smoke.py -q` | 21 工具 + 3 资源 + 2 Prompt |
| AC-3 | `pytest tests/test_server_smoke.py -q` | 握手/列工具/调用/资源；错误路径见 §11 |
| AC-4/5 | 放置 GTDB 数据后 `pytest tests/test_analyze_tools.py tests/test_validate_tools.py -q` | 无数据则跳过 |
| AC-6 | 放置展示数据后 `pytest tests/test_equivalence.py -m slow -q` 或直接运行探针 | 慢；逐字节 + 规范化 API 比较 |
| AC-7 | `pytest tests/test_render_tools.py -q`；`--self-test` | `render_tree` 接受 PNG/PDF/SVG/JPEG 并返回 CLI 配方；不宣称像素级等价，Python 侧配色后处理无法由 CLI 复现；PDF/JPEG 无自动化断言 |
| AC-8 | `pytest tests/test_passthrough.py -q`；`mcp_debug_client --call run_figtreekit_cli '{"argv":["--help"]}'` | 真实样式命令与自检路径 |
| AC-9 | `pytest tests/test_security.py -q` | SEC-1…12 |
| AC-10 | `pytest --cov=figtreekit_mcp --cov-report=term-missing`；`--self-test` | 目标 80%；以最新输出为准 |
| AC-11 | 对照本组中英文文档与源码 | 文档一致性需要人工复核 |
| AC-12 | `python tools/gtdb_acceptance.py --read-root ... --workspace-root ...` | 需要 GTDB 数据；数据存在时执行 CLI 数字/逐字节对比；无数据返回 3 并 `[SKIP]` |

## 11. 已知差异与注意事项

1. **MCP 错误以普通结果返回**：服务器把 `ToolError` 转成 `ok:false` 信封，`CallToolResult.isError` 通常为 `false`。E2E 测试已按此语义断言；客户端必须检查 `ok`/`code`/`error_key`（以及 `error_detail`/`details`），不能只看 `isError`。
2. **慢速等价性探针耗时较长**：在 Windows + 大树上，Java 渲染/分析可能接近 10 分钟；请给 `pytest` 或脚本足够时间。
3. **GTDB 脚本需要数据**：数据缺失时返回 3 并打印 `[SKIP]`，此时不能宣称 AC-12 通过；数据存在时脚本包含 CLI 数字与 `.nex` 逐字节对比，见 §9。
4. **PDF/JPEG 无自动化断言**：`render_tree` 接受它们，但测试只覆盖 PNG/SVG。
5. **`--cli-timeout` 未接入**：透传工具默认 300 秒；测试超时时请显式传 `timeout`。
6. **数据/只读根源**：`gtdb_acceptance.py` 支持 `--read-root` 与 `FIGTREEKIT_GTDB_DIR`/`FIGTREEKIT_MCP_GTDB_DIR`；`mcp_debug_client.py` 支持 `--allow-read-root` 与 `FIGTREEKIT_MCP_READ_ROOTS`。显式传参最便于复现。
7. **Prompt 模板参数**：模板为中英双语；`tree_content` 只以来源说明体现，不嵌入整段树文本；`render_formats`、`tree_file`、`rank` 等会插值。
8. **测试数据位置**：仓库不附带 GTDB/展示数据；测试发现逻辑依赖同级目录布局，移动仓库后需重新放置数据。

## 12. 相关文档

- [`development_guide_CN.md`](development_guide_CN.md)
- [`tools_reference_CN.md`](tools_reference_CN.md)
- [`deployment_and_client_setup_CN.md`](deployment_and_client_setup_CN.md)
- [`README_CN.md`](README_CN.md)
