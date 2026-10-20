# Client configurations (Claude Desktop / Cursor / VS Code)

> **English** | [简体中文](README_CN.md)


This directory contains three MCP client configuration templates:

| File | Client | Top-level key |
|------|--------|---------------|
| `claude_desktop_config.json` | Claude Desktop | `mcpServers` |
| `cursor_mcp.json` | Cursor | `mcpServers` |
| `vscode_mcp.json` | VS Code | `servers` |

## You must edit the placeholders

Every path in the three files is a placeholder; using them unchanged will fail
to start the server.  Replace:

| Placeholder | Replace with |
|-------------|--------------|
| `/absolute/path/to/python3.11` | absolute path to the Python 3.11+ interpreter that has this project installed |
| `/absolute/path/to/figtreekit-mcp-workspace` | absolute path to a writable output directory |
| `/absolute/path/to/tree-data` | absolute path to the tree/taxonomy data directory you allow reading; remove the line if unrestricted |

Linux/macOS example:

```json
"command": "/absolute/path/to/venv/bin/python",
"args": [
  "-m", "figtreekit_mcp",
  "--transport", "stdio",
  "--workspace-root", "/absolute/path/to/figtreekit-workspace",
  "--allow-read-root", "/absolute/path/to/tree-data"
]
```

Windows example (backslashes must be doubled in JSON):

```json
"command": "C:\\absolute\\path\\to\\venv\\Scripts\\python.exe",
"args": [
  "-m", "figtreekit_mcp",
  "--transport", "stdio",
  "--workspace-root", "C:\\absolute\\path\\to\\figtreekit-workspace",
  "--allow-read-root", "C:\\absolute\\path\\to\\tree-data"
]
```

You can also use `scripts/figtreekit-mcp.sh` as the command:

```json
"command": "bash",
"args": ["/absolute/path/to/scripts/figtreekit-mcp.sh"]
```

## Transport

- **stdio is the default transport**, and the three templates use it.  The
  client starts a child process and talks over stdin/stdout.
- SSE / Streamable HTTP are only needed for remote sharing:
  ```bash
  python -m figtreekit_mcp --transport http --host 127.0.0.1 --port 8777
  ```
  They are outside the scope of these templates.

## Java is needed only for rendering

| Capability | Java / JAR needed |
|------------|-------------------|
| `validate_tree`, `summarize_tree`, `cross_validate` | no |
| `analyze_taxonomy`, `check_monophyly`, `taxonomy_completeness` | no |
| `style_tree`, `apply_config`, `export_nexus`, clade tools | no |
| `render_tree` (PNG/PDF/SVG/JPEG) | yes |
| `check_figtree`, `setup_figtree` | check/install Java/JAR |

Validation, analysis and `.nex` export work without Java.  For rendering make
sure the client process can find `java`:

- `java` is on `PATH`; or
- set `JAVA_HOME` in the client configuration (Claude Desktop / Cursor support
  an `env` object); or
- point `FIGTREE_JAR` at the JAR file.

## Where to install the config

### Claude Desktop

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

Fully quit and restart Claude Desktop after editing.

### Cursor

- Project: `<project>/.cursor/mcp.json`
- User: `~/.cursor/mcp.json`

You can also paste the same JSON in Cursor Settings -> MCP.

### VS Code

Copy the content of `vscode_mcp.json` into `.vscode/mcp.json` in your workspace
(note the top-level key is `servers`, not `mcpServers`).  VS Code 1.102+ supports
this file; start the server from the MCP panel after saving.

## Verify

1. Check JSON syntax:
   ```bash
   python -m json.tool examples/client_configs/claude_desktop_config.json
   python -m json.tool examples/client_configs/cursor_mcp.json
   python -m json.tool examples/client_configs/vscode_mcp.json
   ```
2. Check that the interpreter can start the server:
   ```bash
   /absolute/path/to/python3.11 -m figtreekit_mcp --version
   /absolute/path/to/python3.11 -m figtreekit_mcp --self-test
   ```
3. In the client, list tools: you should see 21 tools (`get_environment`,
   `validate_tree`, `style_tree`, `render_tree`, ...).
4. You can also test without a GUI client:
   ```bash
   python tools/mcp_debug_client.py --list-tools
   ```

## Security notes

- `--allow-read-root` is a read-only whitelist.  Add only the data directories
  you really need; never point it at your home directory or a disk root.
- The workspace is the only writable root; artifacts go into `run_<uuid8>`
  subdirectories.
- Do not commit configurations containing personal paths, tokens, or
  credentials.

## See also

- Chinese version: [README_CN.md](README_CN.md)
- Examples overview: [../README_EN.md](../README_EN.md)
- Launcher scripts: [../../scripts/README_EN.md](../../scripts/README_EN.md)
