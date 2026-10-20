# Tool scripts

> **English** | [简体中文](README_CN.md)


This directory contains four development / acceptance tools.  All can be run
from the repository root:

| Script | Purpose | Network / external data |
|--------|---------|-------------------------|
| `gtdb_acceptance.py` | GTDB R232 five-step end-to-end acceptance (AC-12) | needs GTDB data; SKIP if absent |
| `mcp_debug_client.py` | stdio MCP debug client | no |
| `equivalence_probe.py` | MCP / CLI / API equivalence probe (AC-6/7) | needs a tree + taxonomy table |
| `ref_test_gen.py` | generate the 6 golden `.nex` baselines with the figtreekit API | needs a tree + taxonomy table |

Every script adds the repository root and `<repo>/src` to `sys.path`, so a
clean checkout does not need `pip install -e .` first (third-party
dependencies are still required).  No script relies on a hard-coded absolute
path.

## `gtdb_acceptance.py`

### Purpose

Run five acceptance steps against real GTDB R232 data
(`ar53_r232.tree` + `ar53_r232_taxonomy.tsv`):

| Step | Check |
|------|-------|
| 1 | `validate_tree` passes and the tree has 700+ tips |
| 2 | `analyze_taxonomy(class)` counts equal the `figtreekit --analyze-taxonomy class` CLI output |
| 3 | `style_tree(polar, phylum)` `.nex` is byte-identical to the CLI `.nex` |
| 4 | `render_tree` PNG 2400x1600 + PDF exist, have the right size, and are not blank |
| 5 | `collapse_rank(class)` `.nex` is byte-identical to the CLI `.nex` and contains `!collapse` |

Steps 2/3/5 actually run the CLI and compare counts or SHA-256 hashes; they do
not pass on a "non-empty" check.  Step 4 uses a grayscale histogram (non-white
ratio plus intensity standard deviation), so a pure-white or flat-colour image
cannot pass.

### Inputs

- `--read-root <dir>`: directory containing `ar53_r232.tree` and
  `ar53_r232_taxonomy.tsv`;
- or `FIGTREEKIT_GTDB_DIR` / `FIGTREEKIT_MCP_GTDB_DIR`;
- if neither is given, a sibling
  `FigTreeKit-参考文件/参考数据-GTDB-R232` directory is tried;
- `--workspace-root <dir>`: optional, defaults to a system temp directory;
- `--no-render`: explicitly skip step 4 (for environments without Java/JAR).

### Run

```bash
python tools/gtdb_acceptance.py --read-root /absolute/path/to/参考数据-GTDB-R232

FIGTREEKIT_GTDB_DIR=/absolute/path/to/参考数据-GTDB-R232 \
  python tools/gtdb_acceptance.py

python tools/gtdb_acceptance.py --read-root /path/to/data --no-render
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | all five steps passed (an explicit `--no-render` SKIP is allowed) |
| `1` | at least one step failed |
| `2` | invalid usage |
| `3` | SKIP: GTDB data directory or files are missing |

Missing-data output:

```text
[SKIP] GTDB R232 data not found - acceptance cannot run.
       Provide the directory with one of:
         python tools/gtdb_acceptance.py --read-root /path/to/参考数据-GTDB-R232
         FIGTREEKIT_GTDB_DIR=/path/to/参考数据-GTDB-R232 python tools/gtdb_acceptance.py
       Expected files: ar53_r232.tree, ar53_r232_taxonomy.tsv
```

Example successful output (real GTDB numbers will differ):

```text
gtdb_acceptance (GTDB R232) - AC-12
data      : <data dir>
workspace : <workspace>
------------------------------------------------------------------------
[PASS] step 1: validate_tree ok: leaves=704, trees=1, format=newick
[PASS] step 2: analyze_taxonomy(class) == CLI: labels=704, mapped=704, groups=64, mono=64, non_mono=0, rate=100.0%
[PASS] step 3: style_tree .nex == CLI .nex (sha256 02e779a7f8a3)
[PASS] step 4: render_tree PNG 2400x1600 + PDF ok (non-white=100.00%, pdf=24965 B)
[PASS] step 5: collapse_rank(class) collapsed=64, .nex == CLI (sha256 9030a8a2bcd4)
------------------------------------------------------------------------
RESULT: ALL PASS
```

> Note: the `cli_command` returned by `collapse_rank` currently omits
> `--taxonomy-levels` / `--taxonomy-mapping-file` (a source limitation), so
> step 5 does not reuse that string; it builds the equivalent CLI argv
> explicitly and compares bytes.

## `mcp_debug_client.py`

### Purpose

Start a real server subprocess over stdio with the official `mcp` Python SDK
and:

- list tools;
- call a tool with JSON arguments;
- read a resource;
- dump every tool's JSON Schema;
- fetch a prompt.

### Inputs and environment

| Option / variable | Meaning |
|-------------------|---------|
| `--list-tools` | list all tools (21) |
| `--call TOOL JSON` | call a tool, e.g. `--call validate_tree '{"tree_content":"(A:1,B:1);"}'` |
| `--read-resource URI` | e.g. `figtreekit://version` |
| `--dump-schema` | print every tool's JSON Schema |
| `--prompt NAME` | e.g. `create-publication-figure` |
| `--workspace-root` | default `$FIGTREEKIT_MCP_WORKSPACE` or `<repo>/figtreekit-mcp-workspace` |
| `--allow-read-root` | repeatable; default `$FIGTREEKIT_MCP_READ_ROOTS` (`os.pathsep`-separated: `;` on Windows, `:` on POSIX) |

### Run

```bash
# List tools
python tools/mcp_debug_client.py --list-tools

# Read the version resource
python tools/mcp_debug_client.py --read-resource figtreekit://version

# Pass tree content directly; no file whitelist needed
python tools/mcp_debug_client.py \
  --call validate_tree '{"tree_content": "(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"}'

# Add a read root for file-based tools
python tools/mcp_debug_client.py \
  --allow-read-root /absolute/path/to/tree-data \
  --call summarize_tree '{"tree_file": "/absolute/path/to/tree-data/tree.nwk"}'
```

### Output and exit codes

Successful JSON goes to stdout; server logs go to stderr.  Exit codes:

- `0`: success;
- `1`: the tool returned `isError=true`, or the client/server failed;
- `2`: usage error, JSON parse error, or missing `mcp` dependency.

## `equivalence_probe.py`

### Purpose

Run three-way equivalence checks for the six "golden" parameter sets:

1. **API baseline**: raw figtreekit `FigTreeStyler`;
2. **CLI baseline**: `python -m figtreekit ...`;
3. **MCP baseline**: the `style_tree` handler.

Checks:

- MCP `.nex` equals CLI `.nex` byte-for-byte;
- MCP/CLI equal the API baseline after normalising tree names;
- when Java/JAR is available, compare MCP-rendered PNG with a direct
  `java -jar` PNG; pixel-stat difference must be < 0.5%.

### Input

```bash
python tools/equivalence_probe.py <input.tree> <taxonomy.tsv> <workspace_root>
```

- `input.tree`: Newick/Nexus tree;
- `taxonomy.tsv`: taxonomy mapping;
- `workspace_root`: output directory (render comparison files are written
  there).

It imports `ref_test_gen.py` from the same directory.  Requires `figtreekit`
and `pillow`; render comparison additionally needs Java/JAR (skipped if
missing).

### Output and exit codes

```text
equivalence probe: ALL PASS
  [PASS] radial_full: MCP .nex == CLI .nex (byte-for-byte)
  ...
```

- `0`: all checks passed;
- `1`: a difference was found;
- `2`: not enough arguments or an input file does not exist.

## `ref_test_gen.py`

### Purpose

Generate the six golden `.nex` baselines with the figtreekit Python API:

1. radial, fully expanded;
2. polar, fully expanded;
3. polar, class collapse, cartoon;
4. polar, class collapse, collapse;
5. rectilinear, phylum collapse, cartoon;
6. rectilinear, phylum collapse, collapse.

### Input

```bash
python tools/ref_test_gen.py <input.tree> <taxonomy.tsv> <out_dir>
```

### Output and exit codes

Each parameter set writes `<out_dir>/<key>.nex` and prints:

```text
generated radial_full: <out_dir>/radial_full.nex
...
```

- `0`: success;
- `1`: an input file does not exist;
- `2`: not enough arguments.

## Notes

- All scripts can be syntax-checked with:
  ```bash
  python -m py_compile tools/gtdb_acceptance.py tools/mcp_debug_client.py \
    tools/equivalence_probe.py tools/ref_test_gen.py
  ```

## See also

- Chinese version: [README_CN.md](README_CN.md)
- Examples overview: [../examples/README_EN.md](../examples/README_EN.md)
- Scripts: [../scripts/README_EN.md](../scripts/README_EN.md)
