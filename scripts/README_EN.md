# Scripts

> **English** | [简体中文](README_CN.md)


This directory contains two POSIX sh scripts:

| Script | Purpose |
|--------|---------|
| `setup_env.sh` | install / repair the Python environment and the editable project |
| `figtreekit-mcp.sh` | start the MCP server over stdio (for clients) |

Neither script depends on micromamba or hard-coded absolute paths; the
repository root is derived from each script's own location.

## `setup_env.sh`

### What it does

1. checks Python (>= 3.11) and pip;
2. if `FIGTREEKIT_SRC` is set, installs that FigTreeKit checkout in editable
   mode; otherwise checks that `figtreekit` is importable;
3. installs the runtime dependency `mcp>=1.29,<2`;
4. installs the test/render extras:
   - `pytest>=7.5`
   - `pytest-asyncio>=0.23`
   - `hypothesis>=6.0`
   - `pytest-cov>=4.0`
   - `pillow>=10.0`
5. installs this project with `pip install --no-deps -e .`;
6. verifies imports (`mcp`, `figtreekit`, `Bio`, `PIL`) and runs
   `python -m figtreekit_mcp --version`.

The script is idempotent and can be rerun safely.

### Usage

```bash
# Use python3 from PATH
bash scripts/setup_env.sh

# Select an interpreter (recommended: a virtual environment)
PYTHON=/absolute/path/to/venv/bin/python bash scripts/setup_env.sh

# Also install a FigTreeKit source checkout
PYTHON=/absolute/path/to/venv/bin/python \
FIGTREEKIT_SRC=/absolute/path/to/FigTreeKit \
bash scripts/setup_env.sh
```

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PYTHON` | `python3` | Python 3.11+ executable or command name |
| `ENV_PY` | none | compatibility fallback when `PYTHON` is unset |
| `FIGTREEKIT_SRC` | none | optional FigTreeKit checkout; installed editable with `--no-deps` |

### Expected output (excerpt)

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

### Troubleshooting

| Error | Fix |
|-------|-----|
| `Python interpreter 'python3' was not found` | install Python 3.11+, or set `PYTHON` |
| `... is too old` | use 3.11 or newer |
| `pip is not available` | create a virtual environment: `python3.11 -m venv .venv` |
| `figtreekit is not importable` | `pip install 'figtreekit>=1.1.4'` or set `FIGTREEKIT_SRC` |
| `Could not install ...` | check network/proxy and pip permissions; use a virtual environment |

## `figtreekit-mcp.sh`

### What it does

Starts the server over stdio and forwards arguments to
`python -m figtreekit_mcp`:

```bash
exec "$PYTHON" -m figtreekit_mcp \
  --transport stdio \
  --workspace-root "$PROJECT_ROOT/figtreekit-mcp-workspace" \
  "$@"
```

`PROJECT_ROOT` comes from the script's own path, so the checkout can be moved.

### Usage

```bash
# Default workspace: <repo>/figtreekit-mcp-workspace
bash scripts/figtreekit-mcp.sh

# Add a read-only data root
bash scripts/figtreekit-mcp.sh --allow-read-root /absolute/path/to/tree-data

# Select an interpreter
PYTHON=/absolute/path/to/venv/bin/python bash scripts/figtreekit-mcp.sh
```

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PYTHON` | `python3` | Python interpreter |
| `ENV_PY` | none | compatibility fallback when `PYTHON` is unset |
| `FIGTREEKIT_MCP_WORKSPACE` | `<repo>/figtreekit-mcp-workspace` | workspace |

Extra arguments are forwarded unchanged; an explicit `--workspace-root` on the
command line wins over the default.

### Use from a client

In Claude Desktop / Cursor you can set `command` to `bash` and point the first
argument at this script:

```json
"command": "bash",
"args": ["/absolute/path/to/scripts/figtreekit-mcp.sh"]
```

Alternatively use the absolute Python path directly; see
`examples/client_configs/README_EN.md`.

## Windows notes

POSIX sh scripts need Git Bash, MSYS2, or WSL.  On native Windows call the
module directly; no `.sh` is required:

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

With a virtual environment:

```powershell
.\.venv\Scripts\python.exe -m figtreekit_mcp --version
.\.venv\Scripts\python.exe -m figtreekit_mcp --self-test
```

`setup_env.sh` also works from Git Bash:

```bash
PYTHON=/c/absolute/path/to/venv/Scripts/python.exe bash scripts/setup_env.sh
```

Windows paths in client JSON must be escaped (`C:\\Users\\...`).

## Syntax check

After editing the scripts, run:

```bash
bash -n scripts/setup_env.sh
bash -n scripts/figtreekit-mcp.sh
```

## See also

- Chinese version: [README_CN.md](README_CN.md)
- Examples overview: [../examples/README_EN.md](../examples/README_EN.md)
- Tool scripts: [../tools/README_EN.md](../tools/README_EN.md)
