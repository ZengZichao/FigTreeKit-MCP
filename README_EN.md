# FigTreeKit-MCP

[简体中文](README.md) | **English**

> An MCP server for AI assistants that exposes the FigTreeKit phylogenetic-tree workflow — **validate → analyze → style → export → render** — as 21 tools, 3 resources and 2 prompts.
>
> Version **0.1.0** · License **GPL-2.0-or-later** · Python **≥ 3.11** · **Java 8+** for rendering only

FigTreeKit-MCP is built on the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) using FastMCP from the official Python SDK. It does not reimplement tree algorithms: parsing, Nexus generation, taxonomy analysis and FigTree rendering are delegated to the [FigTreeKit](https://github.com/ZengZichao/FigTreeKit) kernel. MCP results therefore track the `figtreekit` CLI/API, and every styling call can return a reproducible command line.

## Features

- **21 tools (T01–T21)**: environment checks and setup, validation, analysis, styling, clade operations, rendering and full CLI pass-through.
- **3 resources**: `figtreekit://version`, `figtreekit://help`, `figtreekit://defaults`.
- **2 prompts**: `create-publication-figure`, `taxonomy-audit`.
- **Reproducibility**: `style_tree`, `apply_config` and `export_nexus` return an equivalent `cli_command` and `config_json`. Six golden showcase parameter sets pass byte-for-byte MCP↔CLI comparison on the 700-tip showcase tree, and match the Python API baseline semantically after normalizing non-deterministic fields. `render_tree` returns a CLI recipe, but Python-side color post-processing is not CLI-reproducible byte-for-byte; the result discloses this limitation.
- **Multi-tree selection**: `multi_tree=first|last|random|split|all|ask`, a 0-based `tree_index`, and `seed` for reproducible `random` selection.
- **Security boundary**: one writable workspace plus zero or more read-only roots; `Path.resolve()` symlink containment; rejection of `..`/drive-relative paths and Windows reserved artifact names; pass-through outputs are always forced into the run directory and disclosed; `shell=False`.
- **Three transports**: stdio (default and recommended), SSE and Streamable HTTP.
- **Responsive loop, serialized calls**: each synchronous handler runs in an AnyIO worker thread, while a global lock serializes invocations because figtreekit uses process-global taxonomy rank prefixes and warning filters; failures become a structured error envelope.
- **Runnable examples**: the three scripts under `examples/` use a built-in 12-tip tree and need no external data for validation, auditing and styling (rendering still needs Java/JAR).

## Architecture at a glance

```text
MCP client (Claude Desktop / Cursor / VS Code / custom)
        │  stdio / SSE / Streamable HTTP
        ▼
FastMCP server (server.py)
  ├─ Tool registration: 21 sync handlers sent to AnyIO worker threads by async wrappers
  ├─ Global serialization: every call acquires a process-wide RLock (taxonomy global state + JVM children)
  ├─ Exceptions → unified envelope (ok:false / code / error_key / error / error_detail / details / run_dir)
  ├─ Resources: figtreekit://version / help / defaults
  ├─ Prompts: create-publication-figure / taxonomy-audit
  └─ lifespan: AppContext (versions, Java/JAR, workspace, limits, timeouts)
        │
        ▼
Tool layer (tools/*.py)
  ├─ Input resolution and whitelist (_core.resolve_tree_source + _workspace)
  ├─ ParamSpec (params.py): validation / to_cli_args / to_config_dict
  ├─ Styling and clade operations (style.py / clade.py)
  ├─ Rendering (render.py, Java + figtree_patched.jar)
  └─ CLI pass-through (passthrough.py, shell=False)
        │
        ▼
figtreekit kernel (Nexus generation, taxonomy analysis, FigTree rendering)
```

Key points:

- The 21 MCP input schemas preserve the original synchronous handler signatures and type hints; registration only changes how handlers execute, not the parameter surface.
- `params.ParamSpec` is the single source of truth for the `style_tree` parameter surface. `to_cli_args()` produces the command line, `to_config_dict()` produces the FigTree block JSON, and the in-process application path in `tools/style.py` follows the same ordering.
- `AppContext` is created at server startup and holds the workspace, allowed read roots, versions, Java/JAR probe results and timeout configuration. Tools obtain it through `get_app(ctx)`.
- Each call gets its own `run_<uuid8>` directory. Artifact descriptors contain `relative`, `absolute` and `size_bytes`; images may also carry `data_uri`, `mime`, `width` and `height`.
- The server assumes the workspace, the installed `figtreekit` package and the JAR are trusted. It does not sandbox the JVM or Python.

See [`docs/development_guide_EN.md`](docs/development_guide_EN.md) for module responsibilities, extension steps and the concurrency model.

## Requirements

| Item | Requirement | Notes |
|------|-------------|-------|
| Python | **3.11 or newer** | `requires-python = ">=3.11"` in `pyproject.toml` |
| Java | **8 or newer** (rendering only) | `render_tree` invokes `java -jar figtree_patched.jar` |
| FigTree JAR | `figtree_patched.jar` | Normally supplied by the `figtreekit` package; can also be selected with `--jar` or installed by `setup_figtree` |
| OS | macOS / Linux / Windows | Windows path and shell notes are in the deployment guide |
| Optional | Pillow ≥ 10 | Installed by the `[render]` extra for image dimensions and base64 previews |

Without Java/JAR, validation, analysis, styling and export tools still work. `get_environment` reports `render_ready`.

## Installation

### Option 1: standard venv + pip (recommended)

macOS / Linux:

```bash
cd "<project-root>"
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,render]"
```

Windows (PowerShell):

```powershell
cd "<project-root>"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev,render]"
```

The `[dev,render]` extra installs the test stack (pytest, pytest-asyncio, pytest-cov, pytest-timeout, hypothesis, ruff, mypy) plus Pillow. For server use without tests:

```bash
python -m pip install -e ".[render]"
```

### Option 2: uv

```bash
cd "<project-root>"
uv venv --python 3.11
uv pip install -e ".[dev,render]"
```

### Option 3: setup script

A portable POSIX shell installer checks Python ≥ 3.11, installs `mcp`, the test/render dependencies, and installs this project in editable mode:

```bash
cd "<project-root>"
bash scripts/setup_env.sh
```

Environment variables:

```bash
# Select a specific interpreter
PYTHON="/path/to/python3.11" bash scripts/setup_env.sh

# Optionally install a local FigTreeKit checkout in editable mode
FIGTREEKIT_SRC="/path/to/FigTreeKit" bash scripts/setup_env.sh
```

On Windows, run the script in Git Bash/WSL, or follow the PowerShell commands above.

### Dependencies and PyPI

`figtreekit-mcp` requires `figtreekit>=1.1.4,<2` and `mcp>=1.29,<2`; the optional render extra is `pillow>=10` (`[render]`). If FigTreeKit is not available in the environment:

```bash
# Install a released figtreekit from PyPI
python -m pip install "figtreekit>=1.1.4,<2"

# Or install a local source checkout during development
python -m pip install -e "<path-to-FigTreeKit>"
```

If your package index already provides the server package, you can also install it directly:

```bash
python -m pip install figtreekit-mcp
```

This repository uses a `src/` layout; from the repository root, `pip install -e ".[dev,render]"` is the supported development install. `pyproject.toml` sets `readme = "README_EN.md"`, so built package metadata uses the English README as its long description; the Chinese README ([`README.md`](README.md)) is its mirror.

### Verify the installation

```bash
python -c "import figtreekit_mcp, figtreekit, mcp; print(figtreekit_mcp.__version__)"
python -m figtreekit_mcp --version
python -m figtreekit_mcp --self-test
```

`--self-test` checks dependencies, registration of 21 tools, stdout purity, Java/JAR, a styling round trip, the workspace whitelist and (when Java is available) PNG rendering. Exit code 0 means all checks passed.

## Running the server

### stdio (for MCP clients)

macOS / Linux:

```bash
"<project-root>/.venv/bin/python" -m figtreekit_mcp \
  --transport stdio \
  --workspace-root "<project-root>/figtreekit-mcp-workspace" \
  --allow-read-root "<data-dir>"
```

Windows:

```powershell
"<project-root>\.venv\Scripts\python.exe" -m figtreekit_mcp `
  --transport stdio `
  --workspace-root "<project-root>\figtreekit-mcp-workspace" `
  --allow-read-root "<data-dir>"
```

You can also use the console script (with its environment activated):

```bash
figtreekit-mcp --transport stdio --workspace-root "<project-root>/figtreekit-mcp-workspace"
```

If `--workspace-root` is omitted, it defaults to `figtreekit-mcp-workspace` under the current working directory. Relative input paths are resolved against that workspace. Quote paths that contain spaces.

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

- The default SSE endpoint is `/sse`; the default Streamable HTTP endpoint is `/mcp`.
- Only loopback binds are allowed by default. Binding `0.0.0.0` or another non-loopback address requires `--allow-remote-bind`, and the server has **no built-in authentication or TLS**. Use it only behind an authenticating reverse proxy/VPN. See [`SECURITY.md`](SECURITY.md).

### Common startup flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--transport {stdio,sse,http}` | `stdio` | Transport |
| `--host` | `127.0.0.1` | SSE/HTTP bind host |
| `--port` | `8777` | SSE/HTTP bind port |
| `--allow-remote-bind` | off | Allow non-loopback binds |
| `--workspace-root` | `./figtreekit-mcp-workspace` | Writable workspace |
| `--allow-read-root DIR` | none | Read-only whitelist root, repeatable |
| `--jar PATH` | auto-detect | Explicit `figtree_patched.jar` |
| `--content-max-bytes` | `10485760` (10 MiB) | `tree_content` limit |
| `--file-max-bytes` | `209715200` (200 MiB) | Whitelisted file limit |
| `--cli-timeout` | `300` | Pass-through timeout (`run_figtreekit_cli` still defaults to 300 s independently) |
| `--render-timeout` | `180` | JVM render timeout when the call omits `timeout` |
| `--setup-timeout` | `600` | `setup_figtree` download/build timeout |
| `--keep-runs` | `50` | Number of run directories to keep |
| `-v` / `-vv` | WARNING | INFO / DEBUG logs (stderr) |
| `-q` | off | ERROR logs only |
| `--log-file PATH` | none | Append logs to a file |
| `--self-test` | off | Run self-diagnostics and exit (0/1) |
| `--version` | — | Print `figtreekit-mcp 0.1.0` |

See [`docs/tools_reference_EN.md`](docs/tools_reference_EN.md) for full flags, tool parameter defaults and error keys.

## Client setup

Full configuration, placeholder rules and troubleshooting for the three clients are in [`docs/deployment_and_client_setup_EN.md`](docs/deployment_and_client_setup_EN.md). Ready-to-edit templates live in [`examples/client_configs/`](examples/client_configs/); every `/absolute/path/to/...` value is a placeholder and must be replaced with real absolute paths for Python, the workspace and the data directory.

Claude Desktop (`claude_desktop_config.json`):

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

Cursor (`mcp.json`) uses the same `mcpServers` structure; VS Code (`.vscode/mcp.json`) uses `servers` and requires `"type": "stdio"`. Remote SSE clients point at `http://127.0.0.1:8777/sse`; Streamable HTTP clients point at `http://127.0.0.1:8777/mcp`. If the client cannot inherit the shell `PATH`, use absolute paths for Python and Java.

## Tools, resources and prompts

### Tools (T01–T21)

| ID | Tool | Purpose |
|----|------|---------|
| T01 | `get_environment` | Runtime snapshot (versions, Java/JAR, workspace, read roots, `render_ready`) |
| T02 | `check_figtree` | Check Java 8+ and `figtree_patched.jar`, with structured guidance when missing |
| T03 | `setup_figtree` | Check, reuse or download/build the patched FigTree JAR |
| T04 | `validate_tree` | Deep validation of Newick/Nexus/FASTA/FASTQ |
| T05 | `summarize_tree` | Parse and summarize structure, branch lengths and tip labels |
| T06 | `cross_validate` | Cross-check tree tip labels against FASTA/FASTQ sequence IDs |
| T07 | `check_monophyly` | Monophyly checks for one or more groups/tip lists |
| T08 | `analyze_taxonomy` | Batch monophyly analysis by taxonomic rank |
| T09 | `taxonomy_completeness` | Taxonomic completeness/coverage report |
| T10 | `style_tree` | Core styling with the full parameter surface + FigTree Nexus export |
| T11 | `apply_config` | Apply a figtree-block JSON config + operation sequence and export |
| T12 | `export_nexus` | Low-level Newick/Nexus structure conversion without styling |
| T13 | `highlight_clade` | Add a background highlight band for a clade |
| T14 | `color_clade` | Color the MRCA or all descendant branches of a clade |
| T15 | `set_clade_font` | Set the tip-label font for a clade |
| T16 | `collapse_clade` | Collapse a clade by exact tip names (triangle/cartoon) |
| T17 | `collapse_group` | Collapse by taxonomic group name with a monophyly pre-check |
| T18 | `collapse_rank` | Collapse all groups at a rank, matching CLI `--collapse-rank` |
| T19 | `clear_annotations` | Clear highlight/collapse annotations (including embedded comments) |
| T20 | `render_tree` | Render PNG/PDF/SVG/JPEG via Java + JAR |
| T21 | `run_figtreekit_cli` | Run arbitrary figtreekit CLI argv arrays (zero shell) |

### Resources (3)

| URI | Content |
|-----|---------|
| `figtreekit://version` | JSON snapshot of versions, Python/MCP SDK, Java, JAR, workspace and read roots |
| `figtreekit://help` | Full `figtreekit` CLI help plus MCP↔CLI mapping notes |
| `figtreekit://defaults` | FigTree default configuration parameters (figtree block keys, JSON) |

### Prompts (2)

| Name | Arguments | Purpose |
|------|-----------|---------|
| `create-publication-figure` | `tree_file`, `tree_content`, `layout` (default `polar`), `collapse_rank` (default `class`), `render_formats` (default `PNG,PDF`) | Guide a publication-figure flow: validate → summarize → analyze → style → render |
| `taxonomy-audit` | `tree_file`, `tree_content`, `rank` (default `phylum`) | Guide batch monophyly analysis, completeness checks and an audit table |

## Examples

All three example scripts use a built-in 12-tip tree and need no external data:

```bash
python examples/01_validate_and_summarize.py
python examples/02_taxonomy_audit.py
python examples/03_publication_figure.py --style-only   # styling only, no Java
python examples/03_publication_figure.py                # styling + PNG/PDF rendering
```

| Example | Contents | External dependency |
|---------|----------|---------------------|
| `01_validate_and_summarize` | `validate_tree` + `summarize_tree`, table output | none |
| `02_taxonomy_audit` | Monophyly/completeness + colored `.nex` export | none |
| `03_publication_figure` | Polar styling + collapse/color + PNG/PDF | Java 8+ and JAR for rendering; `--style-only` does not need them |

Each script has a matching Markdown playbook (`examples/01_validate_and_summarize_CN.md` / `_EN.md`, etc.). Client config templates live in `examples/client_configs/`; replace their placeholders before use.

## Security model

- **One writable root** (`--workspace-root`) plus **zero or more read-only roots** (`--allow-read-root`); the workspace root is also readable.
- Input paths are normalized with `Path.resolve()` (following symlinks) and must end up inside an allowed root; paths containing `..` are rejected before resolution; drive-relative paths are rejected; symlinks inside a root that point outside are rejected.
- All artifacts go to `run_<uuid8>`; `style_tree`/`apply_config`/`export_nexus` further restrict `run_name` to letters, digits, `_` and `-` (1–64 characters), while other tools restrict artifact names to plain filenames inside the run directory; Windows reserved device names cannot be used as artifact names.
- `run_figtreekit_cli` uses `shell=False` argv arrays; `argv[0]` cannot be an interpreter/`-m`, `--figtree-jar` is rejected, input file arguments are whitelisted; output target arguments are always rewritten into the run directory and disclosed in `rewrites`.
- Input text is scanned for control characters and Unicode bidirectional overrides before parsing; default `tree_content` limit is 10 MiB and file limit is 200 MiB.
- SSE/HTTP binds to loopback by default and has no authentication/TLS. Do not expose it directly to the public internet.

See [`SECURITY.md`](SECURITY.md) for the full policy and reporting process.

## Quality and verification

- `tests/` covers unit, tool-level integration, real stdio protocol E2E, security boundaries, property-based tests and MCP↔CLI equivalence.
- Run the full suite with `python -m pytest -q`; `python -m figtreekit_mcp --self-test` checks dependencies, registration of the 21 tools, stdout purity, Java/JAR, a styling round trip and the workspace whitelist.
- Real-data tests for GTDB R232 and the 700-tip showcase tree require external data; related cases skip when it is absent, and **a skip is not a pass**.
- See [`docs/testing_and_acceptance_EN.md`](docs/testing_and_acceptance_EN.md) for test commands, the coverage gate, the equivalence probe and GTDB acceptance.

## Documentation

| Document | Chinese | English |
|----------|---------|---------|
| Documentation index | [`docs/README_CN.md`](docs/README_CN.md) | [`docs/README_EN.md`](docs/README_EN.md) |
| Tool/resource/prompt reference | [`docs/tools_reference_CN.md`](docs/tools_reference_CN.md) | [`docs/tools_reference_EN.md`](docs/tools_reference_EN.md) |
| Development guide | [`docs/development_guide_CN.md`](docs/development_guide_CN.md) | [`docs/development_guide_EN.md`](docs/development_guide_EN.md) |
| Deployment and client setup | [`docs/deployment_and_client_setup_CN.md`](docs/deployment_and_client_setup_CN.md) | [`docs/deployment_and_client_setup_EN.md`](docs/deployment_and_client_setup_EN.md) |
| Testing and acceptance | [`docs/testing_and_acceptance_CN.md`](docs/testing_and_acceptance_CN.md) | [`docs/testing_and_acceptance_EN.md`](docs/testing_and_acceptance_EN.md) |
| Citation | [`CITATION_CN.md`](CITATION_CN.md) | [`CITATION_EN.md`](CITATION_EN.md) / [`CITATION.cff`](CITATION.cff) |
| Third-party notices | [`NOTICE_CN.md`](NOTICE_CN.md) | [`NOTICE`](NOTICE) |
| GPL Chinese notes | [`LICENSE_CN.md`](LICENSE_CN.md) | [`LICENSE`](LICENSE) (authoritative text) |
| Security policy | [`SECURITY_CN.md`](SECURITY_CN.md) | [`SECURITY.md`](SECURITY.md) |

## License and citation

This project is licensed under **GPL-2.0-or-later**. The authoritative license text is [`LICENSE`](LICENSE); Chinese explanatory notes are in [`LICENSE_CN.md`](LICENSE_CN.md) (not a substitute). Third-party attributions and licenses (FigTreeKit, FigTree, iText, Biopython, MCP SDK, Pillow) are in [`NOTICE`](NOTICE) and [`NOTICE_CN.md`](NOTICE_CN.md).

Citation metadata is in [`CITATION.cff`](CITATION.cff), [`CITATION_CN.md`](CITATION_CN.md) and [`CITATION_EN.md`](CITATION_EN.md).
