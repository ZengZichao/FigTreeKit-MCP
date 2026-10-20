# Example 02: taxonomy audit and coloring

> **English** | [简体中文](02_taxonomy_audit_CN.md)


Script: [`02_taxonomy_audit.py`](02_taxonomy_audit.py)

## Goal

Audit monophyly at phylum level (or any other rank) and export a Nexus that
really contains branch colors:

1. `analyze_taxonomy(rank=phylum)` - monophyletic/non-monophyletic groups;
2. `taxonomy_completeness` - taxonomy coverage;
3. `style_tree` - color with `auto_color_rank=phylum`, then override colors for
   the tips of non-monophyletic groups;
4. read the exported `.nex` and verify that `!color` annotations exist.

## Prerequisites

- Python 3.11+;
- `bash scripts/setup_env.sh` has been run;
- no Java/JAR required;
- no network access required;
- the built-in 12-tip tree is used by default and carries embedded taxonomy;
- for your own data, pass `--mapping` when tip labels do not contain taxonomy.

## Run

```bash
# Built-in tree (embedded taxonomy)
python examples/02_taxonomy_audit.py

# Your own tree + mapping table
python examples/02_taxonomy_audit.py \
  --tree /absolute/path/to/tree.nwk \
  --mapping /absolute/path/to/taxonomy.tsv

# Audit the class rank
python examples/02_taxonomy_audit.py --rank class
```

## Options

| Option | Environment variable | Default | Meaning |
|--------|----------------------|---------|---------|
| `--tree` | `FIGTREEKIT_MCP_TREE` | built-in 12-tip tree | Newick/Nexus file |
| `--mapping` | `FIGTREEKIT_MCP_MAPPING` | none | taxonomy mapping (TSV/CSV) |
| `--rank` | - | `phylum` | rank to audit |
| `--workspace` | `FIGTREEKIT_MCP_WORKSPACE` | system temp dir | workspace |

## Key fix: never pass a phylum name as a tip list

FigTreeKit resolves `taxa` in `color` / `color_all` operations against **tip
labels**.  The previous example passed phylum names such as `"PhyC"` directly
to `color_all`.  A phylum name is not a tip label, so FigTreeKit found no
target and coloring silently became a no-op.

This example uses two correct paths:

1. **`auto_color_rank="phylum"`**: a public `style_tree` parameter.  It calls
   `figtreekit_mcp._core.color_groups_by_result()` internally:
   - monophyletic groups: `set_clade_color_all(<the group's real tips>)`;
   - non-monophyletic groups: `set_clade_color` once per real tip.
2. **Explicit per-tip `color`**: resolve real tip labels through
   `check_monophyly.resolved_taxa_preview`, then emit one
   `{"op": "color", "taxa": [<single tip>], "color": "#..."}` per tip.
   Non-monophyletic groups must be handled tip by tip; passing the whole group
   to `color` would only color their MRCA branch.

Notes:

- `analyze_taxonomy` returns group names and counts only, not complete tip
  lists; use `check_monophyly` when you need labels;
- `check_monophyly` previews at most 10 tips.  For larger groups the script
  does not emit explicit per-tip operations; `auto_color_rank` still resolves
  the complete list internally;
- with `--mapping`, `check_monophyly` does not accept a mapping table, so the
  explicit per-tip override is skipped and `auto_color_rank` handles
  everything (it supports mapping tables);
- group names may carry a leading underscore (for example `_PhyC`) from the
  parser.  The display strips it; the original name is passed back to tools.

## Built-in tree

The built-in tree has 12 tips and 5 phyla:

- `PhyA`: 4 tips, monophyletic;
- `PhyB`: 2 tips, monophyletic;
- `PhyD`: 1 tip, monophyletic;
- `PhyE`: 2 tips, monophyletic;
- `PhyC`: 3 tips, **non-monophyletic** (mixed with a `PhyD` tip).

The default run therefore reports `non_monophyletic=1`.

## Expected output

Actual output for the built-in tree (`<workspace>` is the temporary directory
printed by the script):

```text
== FigTreeKit-MCP example 02: taxonomy audit ==
tree      : built-in 12-tip tree (embedded taxonomy)
mapping   : none (taxonomy parsed from tip labels)
rank      : phylum
workspace : <workspace>
== analyze_taxonomy(rank=phylum) ==
  total_labels=12 mapped=12 unmapped=0
  groups=5 monophyletic=4 non_monophyletic=1 monophyly_rate=75.0%
  monophyletic    : PhyA(4), PhyB(2), PhyE(2), PhyD(1)
  non-monophyletic: PhyC(3)
== taxonomy_completeness ==
  coverage=100.0% complete=12 incomplete=0 missing=0
  rank_coverage={'phylum': 100.0, 'class': 100.0}
== style_tree (phylum auto-color + explicit non-monophyletic tips) ==
  nexus_file=<workspace>/run_<uuid8>/output.nex
  cli_command=python -m figtreekit '<workspace>/run_<uuid8>/input.tre' -o '<workspace>/run_<uuid8>/output.nex' --force --layout rectilinear --tip-labels-show --color-clade 'T7_p__PhyC_c__Cls4:#E53935' --color-clade 'T9_p__PhyC_c__Cls4:#E53935' --color-clade 'T10_p__PhyC_c__Cls6:#E53935' --auto-color phylum --taxonomy-levels d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus
  operations_applied:
    - auto_color: applied (rank=phylum, groups=5)
    - color: applied
    - color: applied
    - color: applied
[PASS] exported Nexus contains 17 !color annotation(s)
[PASS] PhyC: 3/3 non-monophyletic tips carry !color

Audit result:
| group | monophyletic | taxa_count |
|-------|--------------|------------|
| PhyA | yes | 4 |
| PhyC | no | 3 |
| PhyB | yes | 2 |
| PhyE | yes | 2 |
| PhyD | yes | 1 |

Result: taxonomy audit completed; Nexus coloring verified.
```

Exit code: `0`.

The number of `!color` annotations depends on the tree and rank.  The important
checks are: it is **not zero**, and every explicitly targeted non-monophyletic
tip carries `!color`.

## Verification criteria

- the summary reports total labels, mapped labels, coverage, monophyly rate and
  the number of problematic groups;
- the exported `.nex` contains at least one `!color` annotation;
- every tip of a non-monophyletic group carries `!color` when the complete tip
  list is available;
- the audit table's monophyly flags match `analyze_taxonomy`;
- exit code is 0.

## FAQ

### Why can't `color_all` take a phylum name?

Because `taxa` matches tip labels.  A phylum name is not a tip, so `color_all`
finds nothing and does not color anything (no error).  Pass the group's real
tips instead: monophyletic groups can use `color_all`; non-monophyletic groups
need one `color` operation per tip.

### Why does `analyze_taxonomy` not return tip lists?

The MCP tool returns a compact audit summary (group names and counts) to keep
responses small on large trees.  Use `check_monophyly` for explicit labels, or
let `auto_color_rank` resolve them internally.

## Prompt for an MCP client

```text
Call analyze_taxonomy(rank=phylum) to get monophyletic/non-monophyletic phyla,
then taxonomy_completeness for coverage.  When coloring, do not pass phylum
names as taxa: use style_tree(auto_color_rank="phylum"), or resolve real tip
labels with check_monophyly and call color per tip; monophyletic groups may use
color_all with their complete tip list.  Finally read the exported .nex and
confirm it contains !color annotations, then report the coloring per phylum.
```

## See also

- Chinese version: [02_taxonomy_audit_CN.md](02_taxonomy_audit_CN.md)
- Examples overview: [README_EN.md](README_EN.md)
