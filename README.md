# FigTreeKit-MCP

**简体中文** | [English](README_EN.md)

> 面向 AI 助手的 MCP 服务器：把 FigTreeKit 的系统发育树 **校验 → 分析 → 样式化 → 导出 → 渲染** 流程暴露为 21 个工具、3 个资源和 2 个 Prompt。
>
> 版本 **0.1.0** · 许可证 **GPL-2.0-or-later** · Python **≥ 3.11** · 仅渲染需要 **Java 8+**

FigTreeKit-MCP 基于 [Model Context Protocol](https://modelcontextprotocol.io/)（MCP）和官方 Python SDK 的 FastMCP 实现。它不重新实现树算法：解析、Nexus 生成、分类学分析与 FigTree 渲染都委托给 [FigTreeKit](https://github.com/ZengZichao/FigTreeKit) 内核，因此 MCP 结果与 `figtreekit` 命令行/API 保持一致，并可为每次样式化调用返回可复现的命令行。

## 特性

- **21 个工具（T01–T21）**：环境检查与安装、校验、分析、样式化、类群操作、渲染和完整 CLI 透传。
- **3 个资源**：`figtreekit://version`、`figtreekit://help`、`figtreekit://defaults`。
- **2 个 Prompt**：`create-publication-figure`、`taxonomy-audit`。
- **可复现性**：`style_tree`、`apply_config`、`export_nexus` 返回等效的 `cli_command` 与 `config_json`。6 组黄金展示参数在 700 末端展示树上通过 MCP 与 CLI 的逐字节比较，并在归一化非确定性字段后与 Python API 基准语义一致。`render_tree` 返回 CLI 配方，但 Python 侧的配色后处理无法由 CLI 逐字节复现，结果中会明确说明。
- **多树选择**：`multi_tree=first|last|random|split|all|ask`、0 基 `tree_index`，以及用于复现 `random` 的 `seed`。
- **安全边界**：一个可写工作区 + 零到多个只读根；`Path.resolve()` 软链接收束；拒绝 `..`/盘符相对路径与 Windows 保留产物名；透传输出强制收敛到 run 目录并披露改写；`shell=False`。
- **三种传输**：stdio（默认，推荐）、SSE、Streamable HTTP。
- **不阻塞事件循环但串行执行**：每个同步 handler 在 AnyIO 工作线程中运行，同时由全局锁串行化调用，因为 figtreekit 使用进程级分类等级前缀与警告过滤器；异常统一转换为结构化错误信封。
- **可运行示例**：`examples/` 下三个脚本默认使用内置 12 末端树，无需外部数据即可完成验证、审计和样式化（渲染需要 Java/JAR）。

## 架构一览

```text
MCP 客户端（Claude Desktop / Cursor / VS Code / 自建）
        │  stdio / SSE / Streamable HTTP
        ▼
FastMCP 服务器（server.py）
  ├─ 工具注册：21 个同步 handler 由异步包装器送入 AnyIO 工作线程
  ├─ 全局串行化：每个调用获取进程级 RLock（分类学全局状态 + JVM 子进程）
  ├─ 异常 → 统一错误信封（ok:false / code / error_key / error / error_detail / details / run_dir）
  ├─ 资源：figtreekit://version / help / defaults
  ├─ Prompt：create-publication-figure / taxonomy-audit
  └─ lifespan：AppContext（版本、Java/JAR、工作区、限额、超时）
        │
        ▼
工具层（tools/*.py）
  ├─ 输入解析与白名单（_core.resolve_tree_source + _workspace）
  ├─ ParamSpec（params.py）：参数校验 / to_cli_args / to_config_dict
  ├─ 样式化与类群操作（style.py / clade.py）
  ├─ 渲染（render.py，调用 Java + figtree_patched.jar）
  └─ CLI 透传（passthrough.py，shell=False）
        │
        ▼
figtreekit 内核（Nexus 生成、分类学分析、FigTree 渲染）
```

要点：

- 21 个 MCP 输入 schema 保留原始同步 handler 的签名与类型标注；注册层只包装执行方式，不改变参数面。
- `params.ParamSpec` 是 `style_tree` 参数面的唯一来源；`to_cli_args()` 生成命令行，`to_config_dict()` 生成 FigTree block JSON，`tools/style.py` 中的进程内应用逻辑与二者保持同一顺序。
- `AppContext` 在服务器启动时创建并保存工作区、允许读取根、版本、Java/JAR 探测结果和超时配置；工具通过 `get_app(ctx)` 获取。
- 每次调用分配自己的 `run_<uuid8>` 目录；产物描述符包含 `relative`、`absolute`、`size_bytes`，图像还可能有 `data_uri`、`mime`、`width`、`height`。
- 服务器假设工作区、已安装的 `figtreekit` 包和 JAR 是可信的；不对 JVM/Python 做沙箱。

更详细的模块职责、扩展方式和并发模型见 [`docs/development_guide_CN.md`](docs/development_guide_CN.md)。

## 环境要求

| 项 | 要求 | 说明 |
|----|------|------|
| Python | **3.11 或更高** | `pyproject.toml` 中 `requires-python = ">=3.11"` |
| Java | **8 或更高**（仅渲染需要） | `render_tree` 调用 `java -jar figtree_patched.jar` |
| FigTree JAR | `figtree_patched.jar` | 通常随 `figtreekit` 包提供；也可用 `--jar` 指定或用 `setup_figtree` 安装 |
| 操作系统 | macOS / Linux / Windows | Windows 路径与 shell 注意事项见部署指南 |
| 可选 | Pillow ≥ 10 | 安装 `[render]` extra 后用于图像尺寸和 base64 预览 |

不渲染时，Java/JAR 缺失不会影响校验、分析、样式化和导出工具；`get_environment` 会报告 `render_ready` 状态。

## 安装

### 方式一：标准 venv + pip（推荐）

macOS / Linux：

```bash
cd "<project-root>"
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,render]"
```

Windows（PowerShell）：

```powershell
cd "<project-root>"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev,render]"
```

`[dev,render]` 会一并安装测试依赖（pytest、pytest-asyncio、pytest-cov、pytest-timeout、hypothesis、ruff、mypy）和 Pillow。只使用服务器而不跑测试时，可以安装：

```bash
python -m pip install -e ".[render]"
```

### 方式二：uv

```bash
cd "<project-root>"
uv venv --python 3.11
uv pip install -e ".[dev,render]"
```

### 方式三：安装脚本

仓库提供可移植的 POSIX shell 安装脚本，会检查 Python ≥ 3.11、安装 `mcp`、测试/渲染依赖，并以 editable 模式安装本项目：

```bash
cd "<project-root>"
bash scripts/setup_env.sh
```

可用环境变量：

```bash
# 指定 Python 解释器
PYTHON="/path/to/python3.11" bash scripts/setup_env.sh

# 同时以 editable 模式安装本地 FigTreeKit 源码（可选）
FIGTREEKIT_SRC="/path/to/FigTreeKit" bash scripts/setup_env.sh
```

Windows 下请在 Git Bash/WSL 中运行该脚本，或按上面的 PowerShell 命令手动安装。

### 依赖与 PyPI

`figtreekit-mcp` 的运行时依赖是 `figtreekit>=1.1.4,<2` 和 `mcp>=1.29,<2`；渲染可选依赖是 `pillow>=10`（`[render]`）。如果 FigTreeKit 尚未随环境安装，可以：

```bash
# 从 PyPI 安装已发布的 figtreekit
python -m pip install "figtreekit>=1.1.4,<2"

# 或从本地源码目录安装（开发时）
python -m pip install -e "<path-to-FigTreeKit>"
```

如果当前环境/镜像已经提供 `figtreekit-mcp` 包，也可以直接：

```bash
python -m pip install figtreekit-mcp
```

仓库本身以 `src/` 布局开发；在仓库根目录执行 `pip install -e ".[dev,render]"` 即可。`pyproject.toml` 的 `readme = "README_EN.md"`，因此构建元数据的长描述为英文 README；中文说明即本文件。

### 验证安装

```bash
python -c "import figtreekit_mcp, figtreekit, mcp; print(figtreekit_mcp.__version__)"
python -m figtreekit_mcp --version
python -m figtreekit_mcp --self-test
```

`--self-test` 会检查依赖、21 个工具注册、stdout 纯净性、Java/JAR、样式往返、工作区白名单和（Java 可用时）PNG 渲染，返回 0 表示全部通过。

## 启动

### stdio（MCP 客户端使用）

macOS / Linux：

```bash
"<project-root>/.venv/bin/python" -m figtreekit_mcp \
  --transport stdio \
  --workspace-root "<project-root>/figtreekit-mcp-workspace" \
  --allow-read-root "<data-dir>"
```

Windows：

```powershell
"<project-root>\.venv\Scripts\python.exe" -m figtreekit_mcp `
  --transport stdio `
  --workspace-root "<project-root>\figtreekit-mcp-workspace" `
  --allow-read-root "<data-dir>"
```

也可以使用 console script（确保其所在环境已激活）：

```bash
figtreekit-mcp --transport stdio --workspace-root "<project-root>/figtreekit-mcp-workspace"
```

如果不传 `--workspace-root`，默认值是当前工作目录下的 `figtreekit-mcp-workspace`。相对路径输入以该工作区为基准解析。含空格的路径必须加引号。

### SSE / Streamable HTTP

```bash
python -m figtreekit_mcp \
  --transport sse \
  --host 127.0.0.1 --port 8777 \
  --workspace-root "<project-root>/figtreekit-mcp-workspace"
```

```bash
python -m figtreekit_mcp \
  --transport http \
  --host 127.0.0.1 --port 8777 \
  --workspace-root "<project-root>/figtreekit-mcp-workspace"
```

- `--transport sse` 的默认端点为 `/sse`；`--transport http`（Streamable HTTP）的默认端点为 `/mcp`。
- 默认只允许回环地址。绑定 `0.0.0.0` 或其他非回环地址必须显式加 `--allow-remote-bind`，且服务**没有内置认证或 TLS**；只应在认证反向代理/VPN 之后使用。详见 [`SECURITY_CN.md`](SECURITY_CN.md)。

### 常用启动参数

| 参数 | 默认值 | 作用 |
|------|--------|------|
| `--transport {stdio,sse,http}` | `stdio` | 传输方式 |
| `--host` | `127.0.0.1` | SSE/HTTP 绑定主机 |
| `--port` | `8777` | SSE/HTTP 绑定端口 |
| `--allow-remote-bind` | 关闭 | 允许非回环绑定 |
| `--workspace-root` | `./figtreekit-mcp-workspace` | 可写工作区 |
| `--allow-read-root DIR` | 无 | 只读白名单根，可重复 |
| `--jar PATH` | 自动探测 | 指定 `figtree_patched.jar` |
| `--content-max-bytes` | `10485760`（10 MiB） | `tree_content` 上限 |
| `--file-max-bytes` | `209715200`（200 MiB） | 白名单文件上限 |
| `--cli-timeout` | `300` | 透传超时（`run_figtreekit_cli` 仍独立默认 300 秒） |
| `--render-timeout` | `180` | 渲染 JVM 超时；调用未提供 `timeout` 时使用 |
| `--setup-timeout` | `600` | `setup_figtree` 下载/编译超时 |
| `--keep-runs` | `50` | 保留的 run 目录数量 |
| `-v` / `-vv` | WARNING | INFO / DEBUG 日志（写 stderr） |
| `-q` | 关闭 | 仅 ERROR 日志 |
| `--log-file PATH` | 无 | 追加写日志文件 |
| `--self-test` | 关闭 | 运行自检并退出（0/1） |
| `--version` | — | 打印 `figtreekit-mcp 0.1.0` |

完整参数、工具参数默认值和错误键见 [`docs/tools_reference_CN.md`](docs/tools_reference_CN.md)。

## 客户端接入

三种客户端的完整配置、占位符说明和排错步骤见 [`docs/deployment_and_client_setup_CN.md`](docs/deployment_and_client_setup_CN.md)。可直接编辑的模板在 [`examples/client_configs/`](examples/client_configs/)，其中的 `/absolute/path/to/...` 都是占位符，必须替换为真实的 Python、工作区和数据目录绝对路径。

Claude Desktop（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "figtreekit": {
      "command": "<python>",
      "args": [
        "-m", "figtreekit_mcp",
        "--transport", "stdio",
        "--workspace-root", "<workspace>",
        "--allow-read-root", "<data-dir>"
      ]
    }
  }
}
```

Cursor（`mcp.json`）使用同样的 `mcpServers` 结构；VS Code（`.vscode/mcp.json`）使用 `servers` 结构，并加 `"type": "stdio"`。远程 SSE 客户端把服务器 URL 指向 `http://127.0.0.1:8777/sse`；Streamable HTTP 指向 `http://127.0.0.1:8777/mcp`。若客户端无法继承 shell 的 `PATH`，请使用 Python 与 Java 的绝对路径。

## 工具、资源与 Prompt

### 工具（T01–T21）

| 编号 | 工具 | 作用 |
|------|------|------|
| T01 | `get_environment` | 运行时环境快照（版本、Java/JAR、工作区、只读根、`render_ready`） |
| T02 | `check_figtree` | 检查 Java 8+ 与 `figtree_patched.jar`，缺失时返回结构化错误和提示 |
| T03 | `setup_figtree` | 检查、复用或下载/编译 patched FigTree JAR |
| T04 | `validate_tree` | 深度校验 Newick/Nexus/FASTA/FASTQ |
| T05 | `summarize_tree` | 解析并摘要树结构、分支长度与末端标签 |
| T06 | `cross_validate` | 树末端标签与 FASTA/FASTQ 序列 ID 交叉比对 |
| T07 | `check_monophyly` | 单个或多个类群/末端名单的单系性检查 |
| T08 | `analyze_taxonomy` | 按分类等级批量分析单系性 |
| T09 | `taxonomy_completeness` | 分类学完整性/覆盖率报告 |
| T10 | `style_tree` | 核心样式化：完整参数面 + 导出 FigTree Nexus |
| T11 | `apply_config` | 应用 figtree-block JSON 配置 + 操作序列并导出 |
| T12 | `export_nexus` | 低层 Newick/Nexus 结构转换，不做样式化 |
| T13 | `highlight_clade` | 为类群添加背景高亮带 |
| T14 | `color_clade` | 为 MRCA 或全部后代分支着色 |
| T15 | `set_clade_font` | 设置类群末端标签字体 |
| T16 | `collapse_clade` | 按精确末端名折叠类群（三角/卡通） |
| T17 | `collapse_group` | 按分类类群名折叠，带单系预检 |
| T18 | `collapse_rank` | 按等级折叠全部分类群，复现 CLI `--collapse-rank` |
| T19 | `clear_annotations` | 清除高亮/折叠注解（含内嵌注释） |
| T20 | `render_tree` | 通过 Java + JAR 渲染 PNG/PDF/SVG/JPEG |
| T21 | `run_figtreekit_cli` | 以参数数组执行任意 figtreekit CLI（零 shell） |

### 资源（3）

| URI | 内容 |
|-----|------|
| `figtreekit://version` | 版本、Python/MCP SDK、Java、JAR、工作区、只读根的 JSON 快照 |
| `figtreekit://help` | `figtreekit` CLI 全量帮助文本与 MCP↔CLI 对照提示 |
| `figtreekit://defaults` | FigTree 默认配置参数（figtree block 键，JSON） |

### Prompt（2）

| 名称 | 参数 | 用途 |
|------|------|------|
| `create-publication-figure` | `tree_file`、`tree_content`、`layout`（默认 `polar`）、`collapse_rank`（默认 `class`）、`render_formats`（默认 `PNG,PDF`） | 引导“验证 → 摘要 → 分析 → 样式化 → 渲染”的出版级出图流程 |
| `taxonomy-audit` | `tree_file`、`tree_content`、`rank`（默认 `phylum`） | 引导批量单系性分析、完整性核查和审计表输出 |

## 示例

三个示例脚本都默认使用内置 12 末端树，不依赖外部数据：

```bash
python examples/01_validate_and_summarize.py
python examples/02_taxonomy_audit.py
python examples/03_publication_figure.py --style-only   # 只样式化，不需要 Java
python examples/03_publication_figure.py                # 样式化 + PNG/PDF 渲染
```

| 示例 | 内容 | 外部依赖 |
|------|------|----------|
| `01_validate_and_summarize` | `validate_tree` + `summarize_tree`，输出表格 | 无 |
| `02_taxonomy_audit` | 分类学单系性/完整性 + 着色导出 `.nex` | 无 |
| `03_publication_figure` | 极坐标样式化 + 折叠/配色 + PNG/PDF | 渲染需要 Java 8+ 与 JAR；`--style-only` 不需要 |

每个脚本都有对应的 Markdown 剧本（`examples/01_validate_and_summarize_CN.md` / `_EN.md` 等）；客户端配置模板在 `examples/client_configs/`，使用前请替换其中的占位符。

## 安全模型

- **一个可写根**（`--workspace-root`）+ **零到多个只读根**（`--allow-read-root`）；工作区根同时可读。
- 输入路径经 `Path.resolve()` 规范化（跟随软链接），最终必须落在允许根内；含 `..` 的路径在解析前被拒绝；盘符相对路径被拒绝；根内指向外部的软链接被拒绝。
- 所有产物写入 `run_<uuid8>`；`style_tree`/`apply_config`/`export_nexus` 对 `run_name` 额外限制为字母、数字、`_`、`-`（1–64 字符），其他工具的产物名被限制为运行目录内的纯文件名；Windows 保留设备名不能作为产物名。
- `run_figtreekit_cli` 使用 `shell=False` 的参数数组；禁止 `argv[0]` 为解释器/`-m`，禁止 `--figtree-jar`，输入文件参数经过白名单检查；输出目标参数总会被改写进 run 目录，并在 `rewrites` 中披露。
- 输入文本在解析前扫描控制字符和 Unicode 双向覆盖字符；默认 `tree_content` 上限 10 MiB，文件上限 200 MiB。
- SSE/HTTP 默认仅回环，且没有认证/TLS。不要把服务直接暴露到公网。

完整策略与报告方式见 [`SECURITY_CN.md`](SECURITY_CN.md)。

## 质量与验证

- `tests/` 覆盖单元、工具层集成、真实 stdio 协议 E2E、安全边界、属性测试与 MCP↔CLI 等价性。
- `python -m pytest -q` 运行完整测试；`python -m figtreekit_mcp --self-test` 检查依赖、21 个工具注册、stdout 纯净性、Java/JAR、样式往返与工作区白名单。
- GTDB R232 与 700 末端展示树的真实数据测试需要外部数据；数据缺失时相关用例会跳过，**跳过不等于通过**。
- 测试命令、覆盖率门限、等价性探针与 GTDB 验收说明见 [`docs/testing_and_acceptance_CN.md`](docs/testing_and_acceptance_CN.md)。

## 文档

| 文档 | 中文 | English |
|------|------|---------|
| 文档索引 | [`docs/README_CN.md`](docs/README_CN.md) | [`docs/README_EN.md`](docs/README_EN.md) |
| 工具/资源/Prompt 参考 | [`docs/tools_reference_CN.md`](docs/tools_reference_CN.md) | [`docs/tools_reference_EN.md`](docs/tools_reference_EN.md) |
| 开发指南 | [`docs/development_guide_CN.md`](docs/development_guide_CN.md) | [`docs/development_guide_EN.md`](docs/development_guide_EN.md) |
| 部署与客户端接入 | [`docs/deployment_and_client_setup_CN.md`](docs/deployment_and_client_setup_CN.md) | [`docs/deployment_and_client_setup_EN.md`](docs/deployment_and_client_setup_EN.md) |
| 测试与验收 | [`docs/testing_and_acceptance_CN.md`](docs/testing_and_acceptance_CN.md) | [`docs/testing_and_acceptance_EN.md`](docs/testing_and_acceptance_EN.md) |
| 引用 | [`CITATION_CN.md`](CITATION_CN.md) | [`CITATION_EN.md`](CITATION_EN.md) / [`CITATION.cff`](CITATION.cff) |
| 第三方声明 | [`NOTICE_CN.md`](NOTICE_CN.md) | [`NOTICE`](NOTICE) |
| GPL 中文说明 | [`LICENSE_CN.md`](LICENSE_CN.md) | [`LICENSE`](LICENSE)（正式文本） |
| 安全策略 | [`SECURITY_CN.md`](SECURITY_CN.md) | [`SECURITY.md`](SECURITY.md) |

## 许可证与引用

本项目采用 **GPL-2.0-or-later**。正式许可证文本见 [`LICENSE`](LICENSE)；中文解释见 [`LICENSE_CN.md`](LICENSE_CN.md)（不替代正式文本）。第三方组件（FigTreeKit、FigTree、iText、Biopython、MCP SDK、Pillow）的归属与许可证见 [`NOTICE`](NOTICE) 和 [`NOTICE_CN.md`](NOTICE_CN.md)。

引用方式见 [`CITATION.cff`](CITATION.cff)、[`CITATION_CN.md`](CITATION_CN.md) 和 [`CITATION_EN.md`](CITATION_EN.md)。
