# 部署与客户端接入

**简体中文** | [English](deployment_and_client_setup_EN.md)

适用版本：**0.1.0**。本文从零开始说明 macOS/Linux/Windows 的安装、Java/JAR 准备、Claude Desktop/Cursor/VS Code 接入、SSE/HTTP 部署和常见故障排查。所有示例使用占位符：

- `<project-root>`：本仓库根目录（含 `pyproject.toml` 的目录）；
- `<python>`：Python 3.11+ 解释器，优先使用 `<project-root>/.venv` 中的解释器；
- `<data-dir>`：需要让服务器读取的树/序列数据目录（只读根）；
- `<workspace>`：服务器可写的工作区目录。

含空格的路径必须加引号。Windows 路径在 JSON 中建议使用正斜杠 `/` 或双反斜杠 `\\`。

## 1. 前置条件

| 组件 | 要求 | 检查命令 |
|------|------|----------|
| Python | ≥ 3.11 | `python --version` |
| pip / venv | 随 Python 提供 | `python -m pip --version` |
| Java | ≥ 8（仅渲染） | `java -version` |
| FigTree JAR | `figtree_patched.jar` | 由 `figtreekit` 提供，或 `--jar` / `setup_figtree` |

`render_tree` 之外的工具不需要 Java/JAR。`get_environment` 的 `render_ready` 会显示是否具备渲染条件。

## 2. 安装

### 2.1 macOS / Linux

```bash
cd "<project-root>"
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,render]"

# 可选：从本地源码安装 figtreekit
# python -m pip install -e "<path-to-FigTreeKit>"
```

不跑测试时：

```bash
python -m pip install -e ".[render]"
```

也可以使用 uv：

```bash
cd "<project-root>"
uv venv --python 3.11
uv pip install -e ".[dev,render]"
```

### 2.2 Windows

PowerShell：

```powershell
cd "<project-root>"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev,render]"
```

如果 PowerShell 阻止激活脚本，可临时调整执行策略，或直接使用解释器绝对路径：

```powershell
& "<project-root>\.venv\Scripts\python.exe" -m pip install -e ".[dev,render]"
```

在 `cmd.exe` 中激活：

```bat
"<project-root>\.venv\Scripts\activate.bat"
```

`scripts/setup_env.sh` 是 POSIX shell 脚本；Windows 请在 Git Bash 或 WSL 中运行，或按上面的命令手动安装。

### 2.3 使用安装脚本（可选）

```bash
cd "<project-root>"
PYTHON="<python>" bash scripts/setup_env.sh

# 同时安装同级 FigTreeKit 源码
FIGTREEKIT_SRC="<path-to-FigTreeKit>" bash scripts/setup_env.sh
```

脚本会检查 Python ≥ 3.11、安装 `mcp`、测试/渲染依赖，并以 editable 模式安装本项目，最后执行 `python -m figtreekit_mcp --version` 验证入口。脚本安装的 `mcp` 约束与项目一致（`mcp>=1.29,<2`）。如果环境已锁定旧版本，脚本会重新安装满足约束的版本。

### 2.4 安装后验证

```bash
"<python>" -m figtreekit_mcp --version
"<python>" -m figtreekit_mcp --self-test
```

`--self-test` 返回 0 表示所有检查通过。缺少 Java/JAR 时对应项会显示 `[WARN]`，但自检仍可能以 0 退出；需要渲染时请确保 `render_ready=true`。

## 3. Java 与 FigTree JAR

### 3.1 安装 Java

`render_tree` 需要 Java 8 或更高版本。推荐安装带 `java` 命令的 JDK/JRE（如 Adoptium Temurin、Oracle JDK、系统包管理器版本），并确保 `java` 在服务器的 `PATH` 中。MCP 客户端启动的进程不一定继承交互式 shell 的环境，建议：

- 在客户端配置中显式使用带 Java 的 Python 环境；
- 或在启动前确认 `java -version` 在相同用户环境下可用；
- 如 Java 不在 `PATH`，可在系统层面设置 `JAVA_HOME` 并把 `$JAVA_HOME/bin` 加入 `PATH`。

### 3.2 JAR 来源

优先级从高到低：

1. 工具参数 `jar_path`（仅 `render_tree`/`check_figtree`/`setup_figtree` 等）；
2. 服务器启动参数 `--jar "<path>"`；
3. `figtreekit.find_figtree_jar()` 自动探测（通常找到 `figtreekit` 包内随附的 `figtree_patched.jar`）；
4. 部分环境支持 `FIGTREE_JAR` 环境变量（figtreekit 的提示中会提到）。

如果 JAR 放在只读根之外，`--jar` 指定的路径会因白名单检查而不可读；请把 JAR 放入 `<workspace>` 或某个 `--allow-read-root`，或使用 `figtreekit` 自带 JAR。

### 3.3 使用 `setup_figtree`

在 MCP 客户端中调用：

```json
{"jar_path": null, "check_only": false, "verbose": true}
```

它会复用已有 JAR，或在需要时下载/编译；超时由 `--setup-timeout`（默认 600 秒）控制。若只想检查：

```json
{"check_only": true}
```

`check_only` 在依赖缺失时也返回检查结果，不抛错。

## 4. 启动服务器

### 4.1 stdio（推荐）

```bash
"<python>" -m figtreekit_mcp \
  --transport stdio \
  --workspace-root "<workspace>" \
  --allow-read-root "<data-dir>"
```

Windows PowerShell：

```powershell
& "<python>" -m figtreekit_mcp `
  --transport stdio `
  --workspace-root "<workspace>" `
  --allow-read-root "<data-dir>"
```

或使用 console script：

```bash
figtreekit-mcp --transport stdio --workspace-root "<workspace>"
```

`--workspace-root` 省略时默认为当前工作目录下的 `figtreekit-mcp-workspace`。相对路径输入以工作区根为基准。

### 4.2 SSE / Streamable HTTP

```bash
"<python>" -m figtreekit_mcp \
  --transport sse \
  --host 127.0.0.1 --port 8777 \
  --workspace-root "<workspace>"
```

```bash
"<python>" -m figtreekit_mcp \
  --transport http \
  --host 127.0.0.1 --port 8777 \
  --workspace-root "<workspace>"
```

- SSE 默认端点：`http://127.0.0.1:8777/sse`
- Streamable HTTP 默认端点：`http://127.0.0.1:8777/mcp`
- 默认只允许回环绑定。使用 `--host 0.0.0.0` 等非回环地址必须加 `--allow-remote-bind`。
- 服务没有内置认证/TLS。远程部署请放在认证反向代理（TLS、访问控制、限流）或 VPN 之后，并限制来源 IP。

### 4.3 容器部署说明

本仓库**不附带 Dockerfile 或预构建镜像**；如果需要容器化，请自行维护镜像并至少在镜像中：

1. 使用 Python 3.11+ 基础镜像，安装本项目（`pip install ".[render]"`）以及 Java 8+ 运行时；
2. 挂载一个可写卷作为 `--workspace-root`（否则产物随容器销毁），并把树/序列数据以只读卷加入 `--allow-read-root`；
3. 确认 `figtree_patched.jar` 在镜像内可读，或通过 `--jar`/`setup_figtree` 提供；
4. 容器内通常需要绑定 `0.0.0.0`，因此必须显式加 `--allow-remote-bind`；这不是认证机制，仍需在容器外终止 TLS 并做访问控制；
5. 不要把宿主家目录、整个数据盘或 Docker socket 挂进容器。

## 5. 客户端配置

### 5.1 通用占位符

先确定三个绝对路径：

```text
<python>       例如 <project-root>/.venv/bin/python
               Windows: <project-root>\.venv\Scripts\python.exe
<workspace>    例如 <project-root>/figtreekit-mcp-workspace
<data-dir>     例如 /data/phylogeny 或 D:/data/phylogeny
```

`examples/client_configs/` 中有三份模板；其中的 `/absolute/path/to/...` 是占位符，**不要直接使用**，请按本节替换。仓库自带的 `scripts/figtreekit-mcp.sh` 会从脚本位置推导项目根，并通过 `PYTHON`/`FIGTREEKIT_MCP_WORKSPACE` 选择解释器和工作区，适合无法继承 shell 环境的客户端：

```bash
PYTHON="<python>" FIGTREEKIT_MCP_WORKSPACE="<workspace>" \
  "<project-root>/scripts/figtreekit-mcp.sh" --allow-read-root "<data-dir>"
```

### 5.2 Claude Desktop

配置文件位置：

- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows：`%APPDATA%\Claude\claude_desktop_config.json`

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

保存后完全退出并重启 Claude Desktop。Windows 的 `<python>` 建议写成 `"C:/Users/<user>/.../.venv/Scripts/python.exe"` 或转义反斜杠。

### 5.3 Cursor

Cursor 使用 MCP 配置（全局 `~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`）：

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

保存后在 Cursor 的 MCP 设置中启用服务器并重启会话。若 Cursor 找不到 `python`，使用绝对路径而不是依赖 `PATH`。

### 5.4 VS Code

在项目内创建 `.vscode/mcp.json`（VS Code 使用 `servers` 而不是 `mcpServers`，并需要 `type`）：

```json
{
  "servers": {
    "figtreekit": {
      "type": "stdio",
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

远程 SSE：

```json
{
  "servers": {
    "figtreekit": {
      "type": "sse",
      "url": "http://127.0.0.1:8777/sse"
    }
  }
}
```

远程 Streamable HTTP：

```json
{
  "servers": {
    "figtreekit": {
      "type": "http",
      "url": "http://127.0.0.1:8777/mcp"
    }
  }
}
```

Cursor 的远程配置也可使用 `"url"` 字段（具体字段名随 Cursor 版本略有差异，请以其 MCP 文档为准）。

## 6. 工作区与只读根设计

- **一个可写根**：`--workspace-root`。所有 `.nex`、图片、日志和 `run_<uuid8>` 目录都写在这里。
- **零到多个只读根**：`--allow-read-root`，可重复。输入文件（树、序列、映射表、Nexus、JAR）必须位于工作区根或某个只读根内。
- 工作区根会自动加入可读根列表。
- 输入路径会经 `Path.resolve()` 规范化（跟随软链接）；如果解析结果逃逸出所有根，返回 `access_denied`。含 `..` 的路径在解析前即拒绝。
- 输出只写工作区；`style_tree`/`apply_config`/`export_nexus` 的 `run_name` 限制为字母/数字/`_`/`-`，其他工具也只会使用运行目录内的纯文件名；透传输出参数会被改写进运行目录。
- 服务器按 `--keep-runs`（默认 50）删除最旧的 run 目录：长期会话中每 16 次新 run 触发一次，关闭时再执行一次；`--keep-runs 0` 会清理全部旧目录。正在运行的调用不会被清理。

建议将工作区放在独立磁盘目录，不要把整个家目录设为只读根；只授予实际需要的数据目录。

## 7. 故障排查

| 症状 | 可能原因 | 处理 |
|------|----------|------|
| `render_ready=false` 或 `code=java_missing` | 运行服务器的环境找不到 Java | 安装 Java 8+ 并确认同一用户环境可执行 `java -version`，见 §7.2 |
| `code=jar_missing` | `figtree_patched.jar` 未找到 | 使用 `setup_figtree`、`--jar` 或 `figtreekit` 自带 JAR，见 §7.3 |
| `multi_tree_required` / `multi_tree_ask` / `tree_index_out_of_range` | 多树 Nexus 未显式选择树 | 先 `summarize_tree`，再传 `multi_tree` 或 0 基 `tree_index`，见 §7.4 |
| 客户端显示调用成功但没有结果 | 错误在 `ok:false` 信封中，`isError` 可能为 false | 检查 `ok`/`code`/`error_key`，见 §7.5 |
| 渲染或透传超时 | 默认 180 秒渲染、300 秒透传 | 调用时传 `timeout`，或调整 `--render-timeout`，见 §7.6 |
| `access_denied` / 路径被拒绝 | 路径在允许根之外、含 `..` 或软链接逃逸 | 把文件放入工作区/只读根，见 §7.1、§7.7 |

### 7.1 Windows 路径与引号

- 含空格/中文的路径必须加引号；JSON 中反斜杠要写成 `\\` 或改用 `/`。
- `cmd.exe` 与 PowerShell 的引号规则不同；`cli_command` 是按 POSIX shell 生成的，重放时建议用 Git Bash，或手动调整。
- `scripts/*.sh` 需要 POSIX shell；Windows 用 Git Bash/WSL，或按本文的 PowerShell 命令手动安装。
- 如果客户端启动时报“找不到 python”，使用绝对路径，并确认该解释器已安装本项目（`python -c "import figtreekit_mcp"`）。

### 7.2 没有 Java

症状：`render_tree` 返回 `code=java_missing`，或 `get_environment.render_ready=false`。

处理：

1. 安装 JDK/JRE 8+（推荐 Temurin）；
2. 确认运行服务器的用户环境中 `java -version` 可用；
3. 重启 MCP 客户端；
4. 如果只需要 `.nex`，使用 `style_tree`/`apply_config`/`export_nexus`，不调用 `render_tree`。

### 7.3 没有 JAR

症状：`code=jar_missing`，`details` 中有安装提示。

处理：

1. 调用 `setup_figtree`（可先 `check_only=true`）；
2. 或使用 `figtreekit` 包内自带的 `figtree_patched.jar`；
3. 或通过启动参数 `--jar "<path>"` 指定（路径必须在可读根内）；
4. 确认 `figtreekit` 安装完整（`python -c "import figtreekit; print(figtreekit.find_figtree_jar())"`）。

### 7.4 多树错误

症状：`multi_tree_required`、`multi_tree_ask` 或 `tree_index_out_of_range`。

处理：

- 用 `summarize_tree` 查看 `tree_count`；
- 在 `style_tree`/`apply_config` 中显式传 `multi_tree=first|last|random|split|all`，或传 0 基 `tree_index`；
- `random` 建议同时传 `seed`，否则每次可能选中不同树；
- `split`/`all` 的单产物布局与 CLI 不同，结果会带 `warnings`；需要逐树文件请直接使用 CLI 透传。

### 7.5 错误信封显示为“成功”

通过 MCP 注册层调用时，`ToolError` 会被转换成 `ok:false` 的普通结果，客户端可能显示 `isError=false`。请检查返回 JSON 的 `ok`、`code`、`error_key`，不要只看协议层错误标志。`error` 是中文可读消息，`error_detail` 是技术细节，`error_key` 适合程序判断。

### 7.6 超时

| 场景 | 默认 | 调整方式 |
|------|------|----------|
| 渲染 | 180 秒（`--render-timeout`） | 调用 `render_tree` 时传 `timeout`，或启动时改 `--render-timeout` |
| CLI 透传 | 300 秒 | 调用 `run_figtreekit_cli` 时传 `timeout`（`--cli-timeout` 当前未接入） |
| JAR 安装 | 600 秒（`--setup-timeout`） | 启动时调整 `--setup-timeout` |
| MCP 客户端自身 | 各客户端不同 | 增大客户端请求超时；大图/大树的渲染可能超过默认值 |

### 7.7 工作区不可写 / 路径被拒绝

- 确认 `--workspace-root` 存在且运行用户可写；服务器会尝试创建目录，但父目录权限不足会失败。
- 确认输入文件位于 `--allow-read-root` 或工作区内；不要使用 `..` 跳出根目录。
- 软链接指向根外会被拒绝，这是预期行为；请把真实文件放入根内，或增加对应的只读根。

### 7.8 端口占用

SSE/HTTP 启动失败并提示端口占用时，换一个端口：

```bash
--port 8788
```

同时更新客户端 URL。

### 7.9 没有输出 / 客户端连不上

- 确认命令在终端中能启动并保持运行（stdio 服务器不会打印提示，这是正常的）。
- 用 `--log-file "<path>"` 查看启动日志；默认日志写 stderr，级别 WARNING。
- 用 `--self-test` 验证安装。
- 用 `tools/mcp_debug_client.py --list-tools` 直接以 stdio 启动服务器，排除客户端配置问题。
- 检查客户端配置的 JSON 是否合法、路径是否存在、参数是否被拆成独立数组元素。

## 8. 远程部署检查清单

- [ ] 默认只绑定 `127.0.0.1`，非必要不使用 `--allow-remote-bind`。
- [ ] 如必须远程访问，前置认证反向代理/VPN，启用 TLS、访问控制和限流。
- [ ] 不把工作区放在 Web 可下载目录；`run_*` 中可能含研究数据。
- [ ] 只读根最小化；不要把 `/`、家目录或整个数据盘加入白名单。
- [ ] 用专用低权限账户运行；限制可执行文件和 JAR 的来源。
- [ ] 记录并轮转 `--log-file`；日志可能含绝对路径和命令输出。
- [ ] 定期升级 `figtreekit-mcp`、`figtreekit`、`mcp`、Biopython、Pillow 与 Java。
- [ ] 阅读 [`SECURITY_CN.md`](../SECURITY_CN.md)。

## 9. 相关文档

- [`tools_reference_CN.md`](tools_reference_CN.md)：全部工具参数、返回与错误键
- [`development_guide_CN.md`](development_guide_CN.md)：架构、扩展与并发
- [`testing_and_acceptance_CN.md`](testing_and_acceptance_CN.md)：测试、跳过含义与验收
- [`README_CN.md`](README_CN.md)：文档索引
