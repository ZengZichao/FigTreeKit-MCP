# 客户端配置（Claude Desktop / Cursor / VS Code）

> [English](README_EN.md) | **简体中文**


本目录提供三份 MCP 客户端配置模板：

| 文件 | 客户端 | 顶层键 |
|------|--------|--------|
| `claude_desktop_config.json` | Claude Desktop | `mcpServers` |
| `cursor_mcp.json` | Cursor | `mcpServers` |
| `vscode_mcp.json` | VS Code | `servers` |

## 必须修改占位符

三份文件中的路径都是占位符，直接使用会启动失败。请把：

| 占位符 | 替换为 |
|--------|--------|
| `/absolute/path/to/python3.11` | 已安装本项目依赖的 Python 3.11+ 解释器绝对路径 |
| `/absolute/path/to/figtreekit-mcp-workspace` | 可写的输出目录绝对路径 |
| `/absolute/path/to/tree-data` | 允许读取的树/分类数据目录绝对路径；不限制时可删除该行 |

示例（Linux/macOS）：

```json
"command": "/absolute/path/to/venv/bin/python",
"args": [
  "-m", "figtreekit_mcp",
  "--transport", "stdio",
  "--workspace-root", "/absolute/path/to/figtreekit-workspace",
  "--allow-read-root", "/absolute/path/to/tree-data"
]
```

示例（Windows，JSON 中反斜杠必须写成 `\\`）：

```json
"command": "C:\\absolute\\path\\to\\venv\\Scripts\\python.exe",
"args": [
  "-m", "figtreekit_mcp",
  "--transport", "stdio",
  "--workspace-root", "C:\\absolute\\path\\to\\figtreekit-workspace",
  "--allow-read-root", "C:\\absolute\\path\\to\\tree-data"
]
```

也可以使用 `scripts/figtreekit-mcp.sh` 作为 `command`，把脚本绝对路径放在
第一个参数：

```json
"command": "bash",
"args": ["/absolute/path/to/scripts/figtreekit-mcp.sh"]
```

## 传输方式

- **stdio 是默认传输**，也是本目录三份配置使用的方式；客户端会启动一个
  子进程并通过标准输入/输出通信。
- 只有需要远程共享时才使用 SSE 或 Streamable HTTP：
  ```bash
  python -m figtreekit_mcp --transport http --host 127.0.0.1 --port 8777
  ```
  这不在本目录的配置模板范围内。

## Java 只在渲染时需要

| 功能 | 需要 Java/JAR |
|------|----------------|
| `validate_tree`、`summarize_tree`、`cross_validate` | 否 |
| `analyze_taxonomy`、`check_monophyly`、`taxonomy_completeness` | 否 |
| `style_tree`、`apply_config`、`export_nexus`、clade 工具 | 否 |
| `render_tree`（PNG/PDF/SVG/JPEG） | 是 |
| `check_figtree`、`setup_figtree` | 检查/安装 Java/JAR |

如果只需要校验、分析和导出 `.nex`，不安装 Java 也能正常使用。
需要渲染时，请确保启动客户端的进程能访问 `java`：

- `java` 在 `PATH` 中；或
- 在客户端配置里设置 `JAVA_HOME`（Claude Desktop / Cursor 支持 `env` 字段）；
- 或通过 `FIGTREE_JAR` 指定 JAR 路径。

## 安装位置

### Claude Desktop

- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows：`%APPDATA%\Claude\claude_desktop_config.json`
- Linux：`~/.config/Claude/claude_desktop_config.json`

修改后完全退出并重新启动 Claude Desktop。

### Cursor

- 项目级：`<项目>/.cursor/mcp.json`
- 用户级：`~/.cursor/mcp.json`

也可以在 Cursor 的 Settings -> MCP 中粘贴同样的 JSON。

### VS Code

把 `vscode_mcp.json` 的内容放到工作区的 `.vscode/mcp.json`（注意顶层键是
`servers`，不是 `mcpServers`）。VS Code 1.102+ 支持该配置；保存后在 MCP
面板中启动服务器。

## 验证

1. 先确认 JSON 语法正确：
   ```bash
   python -m json.tool examples/client_configs/claude_desktop_config.json
   python -m json.tool examples/client_configs/cursor_mcp.json
   python -m json.tool examples/client_configs/vscode_mcp.json
   ```
2. 确认解释器能启动服务器：
   ```bash
   /absolute/path/to/python3.11 -m figtreekit_mcp --version
   /absolute/path/to/python3.11 -m figtreekit_mcp --self-test
   ```
3. 在客户端中查看工具列表，应看到 21 个工具（`get_environment`、
   `validate_tree`、`style_tree`、`render_tree` 等）。
4. 也可以不经过客户端，用调试客户端验证：
   ```bash
   python tools/mcp_debug_client.py --list-tools
   ```

## 安全提示

- `--allow-read-root` 是只读白名单；只添加确实需要读取的数据目录，不要
  指向整个用户主目录或磁盘根目录。
- 工作目录是唯一的可写根；工具产物只会写入其下的 `run_<uuid8>` 目录。
- 不要把含个人路径、令牌或凭据的配置提交到版本库。

## 相关文档

- 英文版：[README_EN.md](README_EN.md)
- 示例总览：[../README_CN.md](../README_CN.md)
- 启动脚本：[../../scripts/README_CN.md](../../scripts/README_CN.md)
