# Example 03: publication figure

> **English** | [简体中文](03_publication_figure_CN.md)


Script: [`03_publication_figure.py`](03_publication_figure.py)

## Goal

Reproduce a publication-style figure: **polar layout + class collapse
(cartoon) + phylum colors + scale axis**:

1. `summarize_tree` to confirm the tree size;
2. `style_tree`: `layout=polar`, `auto_color_rank=phylum`,
   `collapse_rank=class`, `collapse_style=cartoon`, `scale_axis=show`, then
   export `.nex`;
3. `render_tree`: render PNG (2400x1600) and PDF.

## Two modes

| Mode | Command | Java / JAR | Exit code |
|------|---------|------------|-----------|
| Styled Nexus only | `--style-only` | no | 0 on success |
| Full PNG + PDF | default (no flag) | yes | 0 on success, 1 on failure |

In the default mode, if rendering is unavailable (missing Java or JAR), the
script exits **non-zero**; it never reports success silently.  Use
`--style-only` when Java/JAR is unavailable, or install Java 8+ and
`figtree_patched.jar` first.

## Prerequisites

- Python 3.11+;
- `bash scripts/setup_env.sh` has been run;
- the default mode additionally needs:
  - Java 8+ on `PATH` (or `JAVA_HOME` set);
  - `figtree_patched.jar` (usually bundled with `figtreekit`; `setup_figtree`
    can install it);
- no network access required;
- the built-in 12-tip tree is used by default.

Check Java/JAR:

```bash
python -m figtreekit_mcp --self-test
```

## Run

```bash
# Styled Nexus only (no Java)
python examples/03_publication_figure.py --style-only

# Full PNG + PDF
python examples/03_publication_figure.py

# Your own tree + mapping table
python examples/03_publication_figure.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv \
  --style-only
```

## Options

| Option | Environment variable | Default | Meaning |
|--------|----------------------|---------|---------|
| `--tree` | `FIGTREEKIT_MCP_TREE` | built-in 12-tip tree | Newick/Nexus file |
| `--mapping` | `FIGTREEKIT_MCP_MAPPING` | none | taxonomy mapping (TSV/CSV) |
| `--style-only` | - | off | export `.nex` only, skip rendering |
| `--workspace` | `FIGTREEKIT_MCP_WORKSPACE` | system temp dir | workspace |

## Expected output: `--style-only`

Actual output for the built-in tree (`<workspace>` is the temporary directory
printed by the script):

```text
== FigTreeKit-MCP example 03: publication figure ==
tree      : built-in 12-tip tree (embedded taxonomy)
mapping   : none (taxonomy parsed from tip labels)
mode      : style-only (no Java/JAR)
workspace : <workspace>
== summarize_tree ==
  tips=12 tree_count=1 format=newick
== style_tree (polar + class collapse/cartoon + phylum colors) ==
  nexus_file=<workspace>/run_<uuid8>/output.nex
  cli_command=python -m figtreekit '<workspace>/run_<uuid8>/input.tre' -o '<workspace>/run_<uuid8>/output.nex' --force --layout polar --tip-labels-hide --scale-axis-show --angular-range 180 --root-angle 90 --set scaleAxis.reverseAxis=false --set scaleAxis.fontSize=14 --set scaleAxis.significantDigits=2 --collapse-rank class --collapse-style cartoon --auto-color phylum --taxonomy-levels d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus
  operation: auto_color=applied (rank=phylum, groups=5)
  operation: collapse_rank=applied (rank=class, applied_count=7)
[PASS] exported Nexus contains the expected style annotations
== render_tree ==
  skipped (--style-only)

Artifacts:
  nexus: <workspace>/run_<uuid8>/output.nex
Result: styled Nexus exported; rendering skipped (exit 0).
```

Exit code: `0`.

## Expected output: full render

```text
== FigTreeKit-MCP example 03: publication figure ==
tree      : built-in 12-tip tree (embedded taxonomy)
mapping   : none (taxonomy parsed from tip labels)
mode      : render PNG + PDF
workspace : <workspace>
== summarize_tree ==
  tips=12 tree_count=1 format=newick
== style_tree (polar + class collapse/cartoon + phylum colors) ==
  nexus_file=<workspace>/run_<uuid8>/output.nex
  cli_command=python -m figtreekit '<workspace>/run_<uuid8>/input.tre' -o '<workspace>/run_<uuid8>/output.nex' --force --layout polar --tip-labels-hide --scale-axis-show --angular-range 180 --root-angle 90 --set scaleAxis.reverseAxis=false --set scaleAxis.fontSize=14 --set scaleAxis.significantDigits=2 --collapse-rank class --collapse-style cartoon --auto-color phylum --taxonomy-levels d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus
  operation: auto_color=applied (rank=phylum, groups=5)
  operation: collapse_rank=applied (rank=class, applied_count=7)
[PASS] exported Nexus contains the expected style annotations
== render_tree ==
  PNG: <workspace>/run_<uuid8>/output.png (2400x1600, 52906 bytes)
  PDF: <workspace>/run_<uuid8>/output.pdf (2310 bytes)

Artifacts:
  nexus: <workspace>/run_<uuid8>/output.nex
  PNG: <workspace>/run_<uuid8>/output.png
  PDF: <workspace>/run_<uuid8>/output.pdf
Result: styled Nexus and rendered images produced.
```

Exit code: `0`.  PNG/PDF byte sizes vary slightly with fonts and the Java
version; the PNG dimensions must be exactly 2400x1600.

## When rendering is unavailable

If Java or the JAR is missing, the default mode prints something like:

```text
== render_tree ==
[FAIL] render PNG: java_missing: rendering requires Java 8+, but java was not found
       Java not found in PATH
  hint: install Java 8+ and figtree_patched.jar (TOOLS check_figtree / setup_figtree), or rerun with --style-only.
```

and exits with code `1`.  The `.nex` has already been written; rerun with
`--style-only` or install Java/JAR and try again.

## Verification criteria

- the `.nex` exists and contains `!color` annotations; when collapsing
  happened it also contains `!collapse` (collapse) or `!cartoon` (cartoon)
  annotations;
- `--style-only` exits 0;
- on success, PNG and PDF both exist and the PNG is 2400x1600;
- on render failure, the exit code is non-zero;
- `cli_command` can be pasted into a shell to reproduce the same `.nex`
  (equivalence red line).

## Windows notes

- quote paths in PowerShell;
- if Java lives in a custom directory, set `JAVA_HOME` before launching the MCP
  client;
- set `$env:PYTHONIOENCODING = "utf-8"` if the console garbles output.

## See also

- Chinese version: [03_publication_figure_CN.md](03_publication_figure_CN.md)
- Examples overview: [README_EN.md](README_EN.md)
