# Example 01: validate and summarize

> **English** | [简体中文](01_validate_and_summarize_CN.md)


Script: [`01_validate_and_summarize.py`](01_validate_and_summarize.py)

## Goal

Run a complete check on a Newick/Nexus tree and report a table with:

- format, number of tips, number of trees;
- structural problems (negative branches, unbalanced parentheses, duplicate
  tips, ...);
- branch-length range, internal-node count, rooted state;
- a preview of tip labels.

The script calls the same MCP handlers as the server:

1. `validate_tree`;
2. `summarize_tree`.

## Prerequisites

- Python 3.11+;
- `bash scripts/setup_env.sh` has been run (or `figtreekit` and `mcp` are
  installed manually);
- no Java/JAR required;
- no network access required;
- the built-in 12-tip tree is used by default, so no external data is needed.

## Run

```bash
# Built-in tree
python examples/01_validate_and_summarize.py

# Your own tree
python examples/01_validate_and_summarize.py --tree /absolute/path/to/tree.nwk

# Environment variable
FIGTREEKIT_MCP_TREE=/absolute/path/to/tree.nwk \
  python examples/01_validate_and_summarize.py
```

Windows PowerShell:

```powershell
py -3.11 examples/01_validate_and_summarize.py --tree "C:\data\tree.nwk"
```

## Options

| Option | Environment variable | Default | Meaning |
|--------|----------------------|---------|---------|
| `--tree` | `FIGTREEKIT_MCP_TREE` | built-in 12-tip tree | Newick/Nexus file |
| `--workspace` | `FIGTREEKIT_MCP_WORKSPACE` | system temp dir | workspace |

## Built-in tree

The default tree has 12 tips, 5 phyla and 8 classes.  Labels use GTDB-style
taxonomy tags, for example:

```
T1_p__PhyA_c__Cls1
T7_p__PhyC_c__Cls4
```

All three examples use the same tree so they tell one consistent story.

## Expected output

Actual output for the built-in tree (`<workspace>` is the temporary directory
printed by the script):

```text
== FigTreeKit-MCP example 01: validate + summarize ==
input     : built-in 12-tip Newick tree
workspace : <workspace>
== validate_tree ==
  [PASS] valid=True format=newick leaf_count=12 tree_count=1
== summarize_tree ==
  format=newick tree_count=1 tips=12
  internal_nodes=9 rooted=False
  branch_lengths min=0.1 max=0.5 negative=0 has_missing=False
  tip_labels_total=12 preview(first 20)=['T1_p__PhyA_c__Cls1', 'T2_p__PhyA_c__Cls1', 'T3_p__PhyA_c__Cls2', 'T4_p__PhyA_c__Cls2', 'T5_p__PhyB_c__Cls3', 'T6_p__PhyB_c__Cls3', 'T7_p__PhyC_c__Cls4', 'T8_p__PhyD_c__Cls5', 'T9_p__PhyC_c__Cls4', 'T10_p__PhyC_c__Cls6', 'T11_p__PhyE_c__Cls7', 'T12_p__PhyE_c__Cls8']

| format | tips | trees | issues | verdict |
|--------|------|-------|--------|---------|
| newick | 12 | 1 | none (ERROR) | PASS |

Result: validation and summary passed.
```

Exit code: `0`.

## Verification criteria

- `validate_tree.valid=True` with no ERROR;
- `leaf_count` equals `tip_labels_total` for a single-tree input;
- `branch_lengths.negative=0`;
- the table's `tips` value matches the summary;
- exit code is 0.

If the tree contains negative branches, unbalanced parentheses, or other
problems, `validate_tree` raises a structured error; the script exits with
code 1 and prints the error code and details.

## Prompt for an MCP client

The same result can be obtained from an AI assistant in Claude Desktop /
Cursor / VS Code with:

```text
Validate and summarize the given tree:
1. call validate_tree (tree_file: <absolute path>); list every ERROR if it fails;
2. call summarize_tree (include_tip_labels=true, tip_labels_limit=20) and report
   tip count, branch lengths and whether the file contains multiple trees;
3. if a sequence file is available, call cross_validate for tree/sequence parity.
Finish with a table: format / tips / trees / issues / verdict.
```

## See also

- Chinese version: [01_validate_and_summarize_CN.md](01_validate_and_summarize_CN.md)
- Examples overview: [README_EN.md](README_EN.md)
