# FigTreeKit-MCP examples

> **English** | [简体中文](README_CN.md)


This directory contains three runnable examples that show how to use the same
in-process MCP tool handlers as the server without an AI client:
**validate -> analyze -> style -> export -> render**.

| Example | Purpose | Java / JAR | External data |
|---------|---------|------------|---------------|
| `01_validate_and_summarize.py` | Tree validation + summary | no | no (built-in 12-tip tree) |
| `02_taxonomy_audit.py` | Monophyly audit + colored Nexus | no | no (embedded taxonomy labels) |
| `03_publication_figure.py` | Polar publication figure + PNG/PDF | default mode yes; `--style-only` no | no (built-in tree) |

All three examples use the same small built-in 12-tip tree by default.  The
tree deliberately contains one non-monophyletic phylum (`PhyC`) for Example
02, so no network access or GTDB download is required.

## Prerequisites

- Python 3.11 or newer;
- Runtime dependencies installed:
  ```bash
  bash scripts/setup_env.sh
  ```
  The script checks for `figtreekit` (or installs a local checkout via
  `FIGTREEKIT_SRC`), installs `mcp`, the test dependencies and Pillow, then
  installs this project in editable mode;
- Only the default render mode of Example 03 needs Java 8+ and
  `figtree_patched.jar`.  `figtreekit` normally ships the JAR; check with
  `python -m figtreekit_mcp --self-test`;
- No network access is needed.

## Quick start

From the repository root:

```bash
# Example 01: validation and summary
python examples/01_validate_and_summarize.py

# Example 02: taxonomy audit (embedded taxonomy by default)
python examples/02_taxonomy_audit.py

# Example 03: export the styled Nexus only (no Java)
python examples/03_publication_figure.py --style-only

# Example 03: render PNG + PDF (Java/JAR required)
python examples/03_publication_figure.py
```

On Windows use `py -3.11` or the virtual environment's `python.exe` when
`python` is not on `PATH`.  If your console garbles UTF-8 output:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

```cmd
set PYTHONIOENCODING=utf-8
```

## Using your own data

All examples accept `--tree` and an optional `--mapping`:

```bash
python examples/01_validate_and_summarize.py --tree /absolute/path/to/tree.nwk

python examples/02_taxonomy_audit.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv

python examples/03_publication_figure.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv \
  --style-only
```

- `--tree`: Newick or Nexus tree file;
- `--mapping`: TSV/CSV taxonomy mapping used when tip labels have no embedded
  taxonomy;
- `--rank` (Example 02): rank to audit, default `phylum`;
- `--workspace`: output directory; a system temporary directory by default.

Environment variables can replace the flags:

| Variable | Meaning |
|----------|---------|
| `FIGTREEKIT_MCP_TREE` | default tree file |
| `FIGTREEKIT_MCP_MAPPING` | default taxonomy mapping |
| `FIGTREEKIT_MCP_WORKSPACE` | default workspace directory |

Command-line flags take precedence over environment variables.

## Outputs and cleanup

Each example creates a temporary
`figtreekit-mcp-example-<random>` workspace, prints its absolute path, and
writes every tool result into a `run_<uuid8>` subdirectory (`.nex`, `.png`,
`.pdf`).  The absolute artifact paths are printed to stdout.

To keep the artifacts, pass a fixed directory:

```bash
python examples/03_publication_figure.py --workspace ./figtreekit-mcp-example-output
```

The examples do not write to the repository-level
`figtreekit-mcp-workspace` unless you point `--workspace` there.  Temporary
workspaces can be deleted at any time.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | success (including Example 03 `--style-only`) |
| `1` | tool error, failed validation, ineffective coloring, or render requested without Java/JAR |
| `2` | usage error, missing input file, or missing Python dependency |

Example 03 exits non-zero when rendering is requested but Java/JAR is not
available, and tells you to install Java/JAR or use `--style-only`; it never
returns 0 silently in that case.

## Running from a clean checkout

Before importing the package, every example adds

- the repository root, and
- `<repo>/src`

to `sys.path`, so the source tree can be imported even without
`pip install -e .`.  Third-party dependencies (`figtreekit`, `mcp`, ...) still
need to be installed; `bash scripts/setup_env.sh` is the recommended path.

The examples call `create_server(...)` first to register all 21 tool handlers
before invoking `TOOLS[...]`.

## Documentation index

| Chinese | English |
|---------|---------|
| [示例一：校验与摘要](01_validate_and_summarize_CN.md) | [Example 01](01_validate_and_summarize_EN.md) |
| [示例二：分类学审计](02_taxonomy_audit_CN.md) | [Example 02](02_taxonomy_audit_EN.md) |
| [示例三：出版级出图](03_publication_figure_CN.md) | [Example 03](03_publication_figure_EN.md) |
| [客户端配置说明](client_configs/README_CN.md) | [Client configs](client_configs/README_EN.md) |
