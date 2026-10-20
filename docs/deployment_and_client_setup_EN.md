# Deployment and Client Setup

[简体中文](deployment_and_client_setup_CN.md) | **English**

Applies to version **0.1.0**. This guide covers installation on macOS/Linux/Windows, Java/JAR preparation, Claude Desktop/Cursor/VS Code configuration, SSE/HTTP deployment and troubleshooting. Examples use these placeholders:

- `<project-root>`: the repository root (the directory containing `pyproject.toml`);
- `<python>`: a Python 3.11+ interpreter, preferably `<project-root>/.venv`;
- `<data-dir>`: a tree/sequence data directory the server may read (read-only root);
- `<workspace>`: the server's writable workspace.

Quote paths that contain spaces. In JSON, prefer forward slashes `/` or escaped backslashes `\\` on Windows.

## 1. Prerequisites

| Component | Requirement | Check |
|-----------|-------------|-------|
| Python | ≥ 3.11 | `python --version` |
| pip / venv | shipped with Python | `python -m pip --version` |
| Java | ≥ 8 (rendering only) | `java -version` |
| FigTree JAR | `figtree_patched.jar` | Provided by `figtreekit`, or `--jar` / `setup_figtree` |

Tools other than `render_tree` do not need Java/JAR. `get_environment` reports `render_ready`.

## 2. Installation

### 2.1 macOS / Linux

```bash
cd "<project-root>"
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,render]"

# Optional: install a local FigTreeKit checkout
# python -m pip install -e "<path-to-FigTreeKit>"
```

Without tests:

```bash
python -m pip install -e ".[render]"
```

With uv:

```bash
cd "<project-root>"
uv venv --python 3.11
uv pip install -e ".[dev,render]"
```

### 2.2 Windows

PowerShell:

```powershell
cd "<project-root>"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev,render]"
```

If execution policy blocks activation, use the interpreter path directly:

```powershell
& "<project-root>\.venv\Scripts\python.exe" -m pip install -e ".[dev,render]"
```

In `cmd.exe`:

```bat
"<project-root>\.venv\Scripts\activate.bat"
```

`scripts/setup_env.sh` is a POSIX shell script. On Windows run it in Git Bash/WSL or follow the commands above.

### 2.3 Setup script (optional)

```bash
cd "<project-root>"
PYTHON="<python>" bash scripts/setup_env.sh

# Also install a sibling FigTreeKit checkout
FIGTREEKIT_SRC="<path-to-FigTreeKit>" bash scripts/setup_env.sh
```

The script checks Python ≥ 3.11, installs `mcp` and the test/render dependencies, installs this project in editable mode, and verifies the entry point with `python -m figtreekit_mcp --version`. The script installs the same `mcp>=1.29,<2` constraint as the project. If the environment pins an older version, the script reinstalls a compatible one.

### 2.4 Verify

```bash
"<python>" -m figtreekit_mcp --version
"<python>" -m figtreekit_mcp --self-test
```

Exit code 0 means all checks passed. Missing Java/JAR is reported as `[WARN]` and may still exit 0; use `get_environment`/`check_figtree` when you need `render_ready=true`.

## 3. Java and the FigTree JAR

### 3.1 Install Java

`render_tree` needs Java 8 or newer. Install a JDK/JRE that provides the `java` command (for example Adoptium Temurin) and make sure `java` is on the `PATH` of the process that MCP clients start. Client-launched processes may not inherit your interactive shell environment:

- Use a Python environment whose Java is visible to the same user;
- Verify `java -version` under the same user context;
- If Java is not on `PATH`, set `JAVA_HOME` at the system level and add `$JAVA_HOME/bin` to `PATH`.

### 3.2 JAR resolution order

1. Tool argument `jar_path` (where supported);
2. Server startup `--jar "<path>"`;
3. `figtreekit.find_figtree_jar()` auto-detection (usually the JAR bundled with the `figtreekit` package);
4. `FIGTREE_JAR` in environments where figtreekit honors it (mentioned in its hints).

A JAR outside the read roots is rejected by the whitelist. Put it in `<workspace>` or a `--allow-read-root`, or use the JAR bundled with `figtreekit`.

### 3.3 Using `setup_figtree`

```json
{"jar_path": null, "check_only": false, "verbose": true}
```

The tool reuses an available JAR or downloads/builds one. The timeout is `--setup-timeout` (default 600 s). To check only:

```json
{"check_only": true}
```

`check_only` returns a result even when dependencies are missing.

## 4. Starting the server

### 4.1 stdio (recommended)

```bash
"<python>" -m figtreekit_mcp \
  --transport stdio \
  --workspace-root "<workspace>" \
  --allow-read-root "<data-dir>"
```

Windows PowerShell:

```powershell
& "<python>" -m figtreekit_mcp `
  --transport stdio `
  --workspace-root "<workspace>" `
  --allow-read-root "<data-dir>"
```

Or the console script:

```bash
figtreekit-mcp --transport stdio --workspace-root "<workspace>"
```

Without `--workspace-root`, the default is `figtreekit-mcp-workspace` under the current working directory. Relative input paths resolve against the workspace.

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

- SSE default endpoint: `http://127.0.0.1:8777/sse`
- Streamable HTTP default endpoint: `http://127.0.0.1:8777/mcp`
- Only loopback binding is allowed by default. Non-loopback addresses require `--allow-remote-bind`.
- There is no built-in authentication or TLS. For remote access, place the server behind an authenticating reverse proxy (TLS, access control, rate limiting) or a VPN, and restrict source addresses.

### 4.3 Container deployment note

This repository **does not ship a Dockerfile or a prebuilt image**. If you containerize the server, maintain the image yourself and at minimum:

1. Use a Python 3.11+ base image, install this project (`pip install ".[render]"`) and a Java 8+ runtime;
2. Mount a writable volume as `--workspace-root` (otherwise artifacts die with the container), and add tree/sequence data as read-only volumes under `--allow-read-root`;
3. Ensure `figtree_patched.jar` is readable inside the image, or provide it via `--jar`/`setup_figtree`;
4. Containers usually bind `0.0.0.0`, which requires `--allow-remote-bind`; that flag is not authentication, so terminate TLS and enforce access control outside the container;
5. Do not mount the host home directory, an entire data disk, or the Docker socket into the container.

## 5. Client configuration

### 5.1 Placeholders

Resolve three absolute paths first:

```text
<python>       e.g. <project-root>/.venv/bin/python
               Windows: <project-root>\.venv\Scripts\python.exe
<workspace>    e.g. <project-root>/figtreekit-mcp-workspace
<data-dir>     e.g. /data/phylogeny or D:/data/phylogeny
```

`examples/client_configs/` contains three templates whose `/absolute/path/to/...` values are placeholders; **do not use them as-is**. The provided `scripts/figtreekit-mcp.sh` derives the project root from its own location and selects the interpreter/workspace via `PYTHON` and `FIGTREEKIT_MCP_WORKSPACE`:

```bash
PYTHON="<python>" FIGTREEKIT_MCP_WORKSPACE="<workspace>" \
  "<project-root>/scripts/figtreekit-mcp.sh" --allow-read-root "<data-dir>"
```

### 5.2 Claude Desktop

Configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

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

Quit and restart Claude Desktop completely after saving. On Windows prefer `"C:/Users/<user>/.../.venv/Scripts/python.exe"` or escape backslashes.

### 5.3 Cursor

Cursor uses MCP configuration (global `~/.cursor/mcp.json` or project `.cursor/mcp.json`):

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

Enable the server in Cursor's MCP settings and restart the session. If Cursor cannot find `python`, use an absolute path.

### 5.4 VS Code

Create `.vscode/mcp.json` in the project. VS Code uses `servers` (not `mcpServers`) and requires `type`:

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

Remote SSE:

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

Remote Streamable HTTP:

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

Cursor remote configuration may also use a `url` field; exact field names vary by Cursor version, so consult its MCP documentation.

## 6. Workspace and read-root design

- **One writable root**: `--workspace-root`. All `.nex`, images, logs and `run_<uuid8>` directories are written there.
- **Zero or more read-only roots**: `--allow-read-root`, repeatable. Input files (trees, sequences, mapping tables, Nexus, JAR) must live in the workspace or a read root.
- The workspace root is automatically added to the readable roots.
- Inputs are canonicalized with `Path.resolve()` (following symlinks). If the result escapes every root, the call fails with `access_denied`. Paths containing `..` are rejected before resolution.
- Outputs are written only under the workspace. `style_tree`/`apply_config`/`export_nexus` restrict `run_name` to letters/digits/`_`/`-`; other tools also use only basenames inside the run directory. Pass-through output flags are rewritten into the run directory.
- The server deletes the oldest run directories beyond `--keep-runs` (default 50): every 16 new runs in a long session, and again at shutdown. `--keep-runs 0` cleans all old directories. Active calls are not cleaned.

Keep the workspace on a dedicated directory. Do not add your home directory or an entire data disk as a read root; grant only the data directories you actually need.

## 7. Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `render_ready=false` or `code=java_missing` | Java is not visible to the server process | Install Java 8+ and verify `java -version` for the same user, see §7.2 |
| `code=jar_missing` | `figtree_patched.jar` was not found | Use `setup_figtree`, `--jar`, or the JAR shipped with `figtreekit`, see §7.3 |
| `multi_tree_required` / `multi_tree_ask` / `tree_index_out_of_range` | A multi-tree Nexus was not given an explicit selection | Run `summarize_tree`, then pass `multi_tree` or a 0-based `tree_index`, see §7.4 |
| The client reports success but there is no result | The failure is in an `ok:false` envelope; `isError` may be false | Inspect `ok`/`code`/`error_key`, see §7.5 |
| Render or pass-through timeout | Defaults are 180 s for rendering and 300 s for pass-through | Pass `timeout`, or adjust `--render-timeout`, see §7.6 |
| `access_denied` / path rejected | Path is outside allowed roots, contains `..`, or escapes via a symlink | Put the file in the workspace/a read root, see §7.1 and §7.7 |

### 7.1 Windows paths and quoting

- Quote paths containing spaces or non-ASCII characters; in JSON use `\\` or `/`.
- `cmd.exe` and PowerShell have different quoting rules. `cli_command` is generated for POSIX shells; replay in Git Bash or adjust manually.
- `scripts/*.sh` require a POSIX shell; use Git Bash/WSL or the PowerShell commands above.
- If a client reports "python not found", use an absolute path and confirm the project is installed in that interpreter (`python -c "import figtreekit_mcp"`).

### 7.2 No Java

Symptom: `render_tree` returns `code=java_missing`, or `get_environment.render_ready=false`.

1. Install JDK/JRE 8+ (Temurin recommended).
2. Verify `java -version` works for the server's user.
3. Restart the MCP client.
4. If you only need `.nex`, use `style_tree`/`apply_config`/`export_nexus` and skip `render_tree`.

### 7.3 No JAR

Symptom: `code=jar_missing` with installation hints in `details`.

1. Call `setup_figtree` (optionally with `check_only=true` first).
2. Use the `figtree_patched.jar` bundled with `figtreekit`.
3. Or pass `--jar "<path>"` at startup (the path must be readable).
4. Verify the `figtreekit` installation: `python -c "import figtreekit; print(figtreekit.find_figtree_jar())"`.

### 7.4 Multi-tree errors

Symptoms: `multi_tree_required`, `multi_tree_ask` or `tree_index_out_of_range`.

- Inspect `tree_count` with `summarize_tree`.
- Pass `multi_tree=first|last|random|split|all` or a 0-based `tree_index` to `style_tree`/`apply_config`.
- Pair `random` with `seed` for reproducibility.
- `split`/`all` produce a layout that differs from the CLI and return `warnings`; use CLI pass-through if you need one file per tree.

### 7.5 Error envelopes look like successes

Through the MCP registration layer, `ToolError` is converted into an ordinary `ok:false` result, so clients may show `isError=false`. Inspect `ok`, `code` and `error_key` in the returned JSON; do not rely only on the protocol error flag. `error` is a human-readable Chinese message, `error_detail` is the technical detail, and `error_key` is the stable machine identifier.

### 7.6 Timeouts

| Scenario | Default | How to change |
|----------|---------|---------------|
| Rendering | 180 s (`--render-timeout`) | Pass `timeout` to `render_tree` or change `--render-timeout` |
| CLI pass-through | 300 s | Pass `timeout` to `run_figtreekit_cli` (`--cli-timeout` is not wired yet) |
| JAR setup | 600 s (`--setup-timeout`) | Change at startup |
| MCP client | client-specific | Increase the client request timeout; large trees/figures can exceed the default |

### 7.7 Workspace not writable / path denied

- Ensure `--workspace-root` exists and is writable by the server user. The server tries to create it, but insufficient parent permissions will fail.
- Ensure inputs are inside `--allow-read-root` or the workspace; do not use `..` to escape a root.
- Symlinks pointing outside a root are rejected by design. Put the real file inside a root or add the appropriate read root.

### 7.8 Port already in use

Choose another port and update the client URL:

```bash
--port 8788
```

### 7.9 No output / client cannot connect

- Confirm the command starts and stays running in a terminal. A stdio server prints no prompt; this is normal.
- Use `--log-file "<path>"` to capture startup logs; default logs go to stderr at WARNING.
- Run `--self-test` to verify the installation.
- Run `tools/mcp_debug_client.py --list-tools` to start the server directly over stdio and isolate client configuration problems.
- Validate the client JSON, check that paths exist, and ensure each argument is a separate array element.

## 8. Remote deployment checklist

- [ ] Bind `127.0.0.1` by default; avoid `--allow-remote-bind` unless necessary.
- [ ] For remote access, require an authenticating reverse proxy/VPN with TLS, access control and rate limiting.
- [ ] Keep the workspace out of web-served directories; `run_*` may contain research data.
- [ ] Minimize read roots; do not add `/`, the home directory or an entire data disk.
- [ ] Run as a dedicated low-privilege account and control the provenance of executables/JARs.
- [ ] Record and rotate `--log-file`; logs may contain absolute paths and command output.
- [ ] Keep `figtreekit-mcp`, `figtreekit`, `mcp`, Biopython, Pillow and Java up to date.
- [ ] Read [`SECURITY.md`](../SECURITY.md).

## 9. Related documentation

- [`tools_reference_EN.md`](tools_reference_EN.md): all tool parameters, returns and error keys
- [`development_guide_EN.md`](development_guide_EN.md): architecture, extension and concurrency
- [`testing_and_acceptance_EN.md`](testing_and_acceptance_EN.md): tests, skips and acceptance
- [`README_EN.md`](README_EN.md): documentation index
