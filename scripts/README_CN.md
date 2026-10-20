# 脚本说明

> [English](README_EN.md) | **简体中文**


本目录包含两个 POSIX sh 脚本：

| 脚本 | 用途 |
|------|------|
| `setup_env.sh` | 安装/修复 Python 环境与 editable 项目 |
| `figtreekit-mcp.sh` | 以 stdio 方式启动 MCP 服务器（供客户端调用） |

两个脚本都不依赖 micromamba、不写死绝对路径，并从脚本自身位置推导
仓库根目录。

## `setup_env.sh`

### 作用

1. 检查 Python 版本（>= 3.11）和 pip；
2. 如果设置了 `FIGTREEKIT_SRC`，以 editable 方式安装该 FigTreeKit 源码；
   否则检查当前解释器能否导入 `figtreekit`；
3. 安装运行时依赖 `mcp>=1.29,<2`；
4. 安装测试/渲染依赖：
   - `pytest>=7.5`
   - `pytest-asyncio>=0.23`
   - `hypothesis>=6.0`
   - `pytest-cov>=4.0`
   - `pillow>=10.0`
5. 以 `pip install --no-deps -e .` 安装本项目；
6. 校验 `mcp`、`figtreekit`、`Bio`、`PIL` 可导入，并运行
   `python -m figtreekit_mcp --version`。

脚本是幂等的，可以重复运行。

### 用法

```bash
# 使用 PATH 中的 python3
bash scripts/setup_env.sh

# 指定解释器（推荐：虚拟环境）
PYTHON=/absolute/path/to/venv/bin/python bash scripts/setup_env.sh

# 同时安装一个 FigTreeKit 源码 checkout
PYTHON=/absolute/path/to/venv/bin/python \
FIGTREEKIT_SRC=/absolute/path/to/FigTreeKit \
bash scripts/setup_env.sh
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PYTHON` | `python3` | Python 3.11+ 解释器路径或命令名 |
| `ENV_PY` | 无 | `PYTHON` 未设置时的兼容回退 |
| `FIGTREEKIT_SRC` | 无 | 可选的 FigTreeKit 源码目录；设置后执行 `pip install --no-deps -e` |

### 预期输出（节选）

```text
[setup] Project root : /absolute/path/to/FigTreeKit-MCP
[setup] Interpreter  : python3
[setup] Python       : /absolute/path/to/python3 3.11.x
[setup] Step 1/4: FIGTREEKIT_SRC not set - checking installed figtreekit
[setup] Step 2/4: installing runtime dependency mcp>=1.29,<2
[setup] Step 3/4: installing test / render extras (pytest, hypothesis, pillow)
[setup] Step 4/4: installing figtreekit-mcp editable (--no-deps): /absolute/path/to/FigTreeKit-MCP
[setup] Verifying imports and entry point
  mcp         1.x.y
  figtreekit  1.x.y
  biopython   1.x.y
  pillow      10.x.y
figtreekit-mcp 0.1.0

[setup] Done.
```

### 常见错误

| 错误 | 处理 |
|------|------|
| `Python interpreter 'python3' was not found` | 安装 Python 3.11+，或设置 `PYTHON` |
| `... is too old` | 使用 3.11 或更高版本 |
| `pip is not available` | 先创建虚拟环境：`python3.11 -m venv .venv` |
| `figtreekit is not importable` | `pip install 'figtreekit>=1.1.4'` 或设置 `FIGTREEKIT_SRC` |
| `Could not install ...` | 检查网络/代理、pip 权限；必要时使用 `--user` 或虚拟环境 |

## `figtreekit-mcp.sh`

### 作用

以 stdio 传输启动服务器，并把参数转发给 `python -m figtreekit_mcp`：

```bash
exec "$PYTHON" -m figtreekit_mcp \
  --transport stdio \
  --workspace-root "$PROJECT_ROOT/figtreekit-mcp-workspace" \
  "$@"
```

脚本从自身路径推导 `PROJECT_ROOT`，所以整个 checkout 可以移动位置。

### 用法

```bash
# 默认工作目录：<仓库>/figtreekit-mcp-workspace
bash scripts/figtreekit-mcp.sh

# 添加只读数据根
bash scripts/figtreekit-mcp.sh --allow-read-root /absolute/path/to/tree-data

# 指定解释器
PYTHON=/absolute/path/to/venv/bin/python bash scripts/figtreekit-mcp.sh
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PYTHON` | `python3` | Python 解释器 |
| `ENV_PY` | 无 | `PYTHON` 未设置时的兼容回退 |
| `FIGTREEKIT_MCP_WORKSPACE` | `<仓库>/figtreekit-mcp-workspace` | 工作目录 |

额外参数原样转发；如果同时传入 `--workspace-root`，以命令行参数为准。

### 在客户端中使用

Claude Desktop / Cursor 的 `command` 可以设为 `bash`，第一个参数指向本脚本：

```json
"command": "bash",
"args": ["/absolute/path/to/scripts/figtreekit-mcp.sh"]
```

也可以直接把 `command` 设为 Python 绝对路径，详见
`examples/client_configs/README_CN.md`。

## Windows 说明

POSIX sh 脚本需要 Git Bash、MSYS2 或 WSL。Windows 原生环境可以直接调用
模块，不需要 `.sh`：

```powershell
# PowerShell
py -3.11 -m figtreekit_mcp --transport stdio `
  --workspace-root "F:\path\to\figtreekit-mcp-workspace" `
  --allow-read-root "F:\path\to\tree-data"
```

```cmd
REM cmd.exe
py -3.11 -m figtreekit_mcp --transport stdio ^
  --workspace-root "F:\path\to\figtreekit-mcp-workspace" ^
  --allow-read-root "F:\path\to\tree-data"
```

如果使用虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m figtreekit_mcp --version
.\.venv\Scripts\python.exe -m figtreekit_mcp --self-test
```

`setup_env.sh` 在 Git Bash 中同样可用：

```bash
PYTHON=/c/absolute/path/to/venv/Scripts/python.exe bash scripts/setup_env.sh
```

客户端配置里的 Windows 路径要写成 JSON 转义形式（`C:\\Users\\...`）。

## 语法检查

修改脚本后建议运行：

```bash
bash -n scripts/setup_env.sh
bash -n scripts/figtreekit-mcp.sh
```

## 相关文档

- 英文版：[README_EN.md](README_EN.md)
- 示例总览：[../examples/README_CN.md](../examples/README_CN.md)
- 工具脚本：[../tools/README_CN.md](../tools/README_CN.md)
