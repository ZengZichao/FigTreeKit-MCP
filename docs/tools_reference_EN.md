# FigTreeKit-MCP Tool Reference

[简体中文](tools_reference_CN.md) | **English**

Applies to version **0.1.0**. This reference follows the actual function signatures in `src/figtreekit_mcp/tools/*.py`, `ParamSpec` in `params.py`, and the startup options in `_cli.py`. A default of `null`/`None` means "unspecified, use the figtreekit default", not an empty string.

## 1. Overview and conventions

### 1.1 Components, transports and runtime model

FigTreeKit-MCP v0.1.0 is a Python 3.11 MCP server that exposes the FigTreeKit phylogenetic-tree workflow to AI clients:

- **21 tools (T01–T21)**: environment (T01–T03), validation (T04–T06), taxonomic analysis (T07–T09), styling and export (T10–T12), clade operations (T13–T19), rendering (T20) and CLI pass-through (T21).
- **3 resources**: `figtreekit://version`, `figtreekit://help`, `figtreekit://defaults` (see §10).
- **2 prompts**: `create-publication-figure`, `taxonomy-audit` (see §11).
- **3 transports**: `--transport stdio` (default), `sse` and `http`. In `_cli.py` the value is literally `http`; it runs MCP **Streamable HTTP** (`streamable-http`).

**Workspace and read roots**: one writable root is selected by `--workspace-root` (default `<cwd>/figtreekit-mcp-workspace`); every artifact is written there. `--allow-read-root DIR` is repeatable and adds read-only input roots. The workspace root is always readable. File paths are resolved with `Path.resolve()` (following symlinks) and must stay inside a registered root, otherwise the call fails with `access_denied`. Relative paths resolve against the workspace root (`run_figtreekit_cli` positional tokens resolve against that call's run directory), and `..` segments are rejected.

**Per-call artifact directory**: tools that need disk output allocate a `run_<uuid8>` directory (8 hex digits) the first time they need it in a call. Artifact filenames can be set with `run_name`, and descriptors contain `relative`/`absolute`/`size_bytes`. `--keep-runs` bounds retention; cleanup runs when new run directories are allocated (every 16 allocations) and at server shutdown.

**Error envelope**: every tool shares one shape: success is `{"ok": true, ...}`; failure is `{"ok": false, "code", "error_key", "error", "error_detail", "details", "run_dir"}`. The MCP registration layer converts exceptions into ordinary results, so a client's `isError` may be `false`; rely on `ok`/`code`/`error_key`.

**Serialized execution**: tool calls are serialized server-side by a single re-entrant lock. figtreekit keeps taxonomy rank prefixes and warning filters in **process-global state**, and Java/CLI child processes are not safe to run concurrently; concurrent requests therefore queue, while the async wrapper still runs work in a worker thread so the event loop stays responsive.

### 1.2 Tree source: `tree_content` and `tree_file`

Every tool that accepts tree input follows the same rules:

- `tree_content`: Newick/Nexus/FASTA/FASTQ text passed directly;
- `tree_file`: a path inside an allowed read root (relative paths resolve against the workspace root);
- The two are **mutually exclusive** and exactly one is required. Otherwise the call fails with `invalid_argument` and `error_key` `mutually_exclusive_source` or `missing_tree_source`.
- Content is size-checked and scanned for anomalous content (NUL, control characters, Unicode bidirectional overrides) before parsing.

Tools such as `validate_tree`/`summarize_tree` allocate a `run_<uuid8>` directory; `run_dir` may be present even when validation leaves no long-lived artifact.

### 1.3 Results and errors

A successful call returns a JSON object with `"ok": true`. A failed call returns the unified envelope:

```json
{
  "ok": false,
  "code": "access_denied",
  "error_key": "outside_roots",
  "error": "路径不在允许访问的白名单根目录内",
  "error_detail": "请求路径：...",
  "details": [{"level": "ERROR", "message": "..."}],
  "run_dir": "run_ab12cd34"
}
```

- Direct handler calls normally **raise** `ToolError`. Calls through the MCP registration layer (`server.py`'s async wrapper) convert the exception into the `ok:false` envelope and return it as an ordinary tool result. The client's `isError` flag may therefore be `false`; use `ok`, `code` and `error_key`.
- `error` is a Chinese human-readable message, `error_key` is a stable identifier, `error_detail` may contain absolute paths and technical detail, and `details` is a list of `{level, message}`.
- Each tool lists its specific `error_key` values. Generic path, size and argument errors may occur for any tool.

### 1.4 Artifact descriptors

Artifacts returned by styling/export/render/pass-through tools generally look like:

```json
{
  "relative": "run_ab12cd34/output.nex",
  "absolute": "<workspace-root>/run_ab12cd34/output.nex",
  "size_bytes": 12345,
  "data_uri": null,
  "mime": null
}
```

- `relative` is relative to the workspace root and uses backslashes on Windows.
- Raw `RunStorage.register` entries attach a base64 `data_uri` for images (`.png`/`.jpg`/`.jpeg`/`.svg`/`.pdf`) up to **512 KiB**; otherwise it is `null`.
- `nexus_file` is normalized by `nexus_artifact` and contains **only** `relative`/`absolute`/`size_bytes`, without `data_uri`.
- `render_tree`'s `image` and `run_figtreekit_cli`'s `artifacts` are raw registration entries and may include `data_uri`/`mime`; PNG/JPEG may also include `width`/`height` when Pillow is available.
- `run_name` affects only the artifact filename, not a subdirectory; the default is `output`.

### 1.5 Error codes

There are 19 stable codes (`_errors.ERROR_CODES`):

| Code | Typical trigger |
|------|-----------------|
| `invalid_argument` | bad type/enum/range, missing required parameter, mutually exclusive parameters |
| `input_too_large` | `tree_content` or file exceeds its limit |
| `access_denied` | path outside roots, symlink escape, `..`, missing parent, unreadable file |
| `anomalous_content` | control characters or Unicode bidirectional overrides |
| `tree_parse_error` | Newick/Nexus/sequence parse failure, no tip labels |
| `validation_failed` | deep validation found ERROR/CRITICAL, or cross-validation mismatch |
| `taxonomy_conflict` | taxonomy conflict mapped from a figtreekit exception |
| `monophyly_error` | non-monophyletic group, unresolved group, strict collapse failure |
| `export_failed` | Nexus export failure |
| `java_missing` | rendering needs Java but `java` is unavailable |
| `jar_missing` | `figtree_patched.jar` missing or unreadable |
| `figtree_setup_failed` | JAR download/build failure or timeout |
| `render_bad_format` | format is not PNG/PDF/SVG/JPEG |
| `render_timeout` | JVM render timeout |
| `render_failed` | FigTree render failure |
| `cli_failed` | pass-through command exited non-zero |
| `cli_timeout` | pass-through command timed out |
| `cancelled` | cancelled by the client (allowed in envelopes) |
| `internal_error` | unmapped exception (with `stack_summary`, never written to stdout) |

Common `error_key` values include `param_validation_failed` (`style_tree`/`apply_config` validation), `path_traversal`, `outside_roots`, `content_too_large`, `file_too_large`, `anomalous_content_found`, `multi_tree_required`, `multi_tree_ask` and `tree_index_out_of_range`.

## 2. Tool index (T01–T21)

| ID | Tool | Module | Summary |
|----|------|--------|---------|
| T01 | `get_environment` | environment | Runtime snapshot |
| T02 | `check_figtree` | environment | Java/JAR check |
| T03 | `setup_figtree` | environment | Check, reuse or install the JAR |
| T04 | `validate_tree` | validate | Deep validation |
| T05 | `summarize_tree` | validate | Tree summary |
| T06 | `cross_validate` | validate | Tree↔sequence cross-check |
| T07 | `check_monophyly` | analyze | Monophyly check |
| T08 | `analyze_taxonomy` | analyze | Bulk analysis at a rank |
| T09 | `taxonomy_completeness` | analyze | Taxonomy completeness |
| T10 | `style_tree` | style | Core styling + export |
| T11 | `apply_config` | style | Apply figtree-block config |
| T12 | `export_nexus` | style | Structural conversion |
| T13 | `highlight_clade` | clade | Highlights |
| T14 | `color_clade` | clade | Branch colors |
| T15 | `set_clade_font` | clade | Fonts |
| T16 | `collapse_clade` | clade | Collapse by taxon names |
| T17 | `collapse_group` | clade | Collapse by group name |
| T18 | `collapse_rank` | clade | Collapse by rank |
| T19 | `clear_annotations` | clade | Clear highlights/collapses |
| T20 | `render_tree` | render | Render an image |
| T21 | `run_figtreekit_cli` | passthrough | CLI pass-through |

Every tool also receives an MCP-injected `ctx: Context` as its first argument; it is omitted from the tables.

## 3. Environment tools (T01–T03)

### T01 `get_environment`

No parameters.

Returns `ok`, `figtreekit_version`, `biopython_version`, `python_version`, `mcp_sdk_version`, `pillow` (`{ok, version}`; `ok:false`, `version:null` when absent), `java` (`{ok, version, message, hints}`), `jar` (`{ok, path, hints}`), `workspace_root`, `allowed_read_roots`, `render_ready`.

`allowed_read_roots` contains the workspace root plus every `--allow-read-root`. This tool never fails because Java/JAR is missing.

### T02 `check_figtree`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `jar_path` | string | `null` | Explicit JAR to check; otherwise server `--jar` or auto-detection |

Returns `ok`, `java_ok`, `java_version` (for example `17.x`), `jar_ok`, `jar_path`, `render_ready`, `hints`.

Errors: missing Java → `code=java_missing`; Java present but JAR missing → `code=jar_missing`. Both use `error_key=render_deps_missing` and put hints in `details`.

### T03 `setup_figtree`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `jar_path` | string | `null` | Register an existing JAR (must be whitelisted and a file) |
| `check_only` | bool | `false` | Check only; never fails because dependencies are missing |
| `verbose` | bool | `false` | Ask figtreekit for more setup output |

Behavior:

1. `check_only=true`: returns an `ok` envelope equivalent to the check, with `java_ok`, `java_version`, `jar_ok`, `jar_path`, `render_ready`, `hints` and `status`.
2. `jar_path` given: validates and registers it, returning `jar_path` and `status`; a non-file gives `invalid_argument/jar_not_a_file`.
3. An already available JAR is reused and returned.
4. Otherwise figtreekit's install flow downloads/builds the JAR. The timeout is `--setup-timeout` (default 600 s). Failures are `figtree_setup_failed` with `setup_timeout`, `setup_failed` or `setup_no_jar`.

The tool does not expose `install_dir`; figtreekit chooses the location.

## 4. Validation tools (T04–T06)

### T04 `validate_tree`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` | string | `null` | Newick/Nexus/FASTA/FASTQ text |
| `tree_file` | string | `null` | Tree/sequence file inside a read root |
| `mol_type` | string | `null` | `DNA`/`RNA`/`protein`; sequence input only |
| `skip_length_check` | bool | `false` | Skip FASTA alignment-length consistency |

Tree result: `ok`, `valid`, `warnings`, `errors`, `size_bytes`, `run_dir`, `format` (`newick`/`nexus`), `leaf_count`, `node_count`, `tree_count`.

FASTA result: `format:"fasta"`, `sequence_count`, `alphabet`, `duplicate_ids`, `length_mismatch`, etc. FASTQ returns `sequence_count`, `alphabet`, `duplicate_ids`.

Errors: invalid `mol_type` → `bad_mol_type`; unsupported format → `unsupported_format`; any ERROR/CRITICAL → `validation_failed` with `error_key=validation_errors` and one entry per issue in `details`; read failure → `tree_parse_error/read_failed`.

Nexus/FASTA/FASTQ temporary files are written inside this call's `run_dir` and deleted before returning. Validation leaves no persistent artifact. `taxonomy_levels` is **not** a parameter of this tool.

### T05 `summarize_tree`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` | string | `null` | Tree text |
| `tree_file` | string | `null` | Whitelisted file |
| `include_tip_labels` | bool | `true` | Include the tip-label preview |
| `tip_labels_limit` | int | `100` | Preview limit, 1..10000 |
| `multi_tree` | string | `null` | `first`/`last`/`random`/`split`/`all`/`ask` |
| `tree_index` | int | `null` | 0-based tree index |

Returns `ok`, `format`, `tree_count`, `selected_tree`, `statistics` (`tips`, `internal_nodes`, `rooted`, `branch_lengths`: `min`/`max`/`has_missing`/`negative`), `tip_labels_total`, `tip_labels_preview`, `translate_block` (`used`/`entries`), `warnings`; multi-tree inputs may add `multi_tree_hint`.

This tool **does not fail on validation issues**. A multi-tree file without an explicit selection defaults to the first tree and returns `multi_tree_hint` instead of an error. An invalid `tip_labels_limit` gives `bad_tip_labels_limit`.

### T06 `cross_validate`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` | string | `null` | Tree text |
| `tree_file` | string | `null` | Whitelisted tree file |
| `sequences_file` | string | `null` | **Required**; whitelisted FASTA/FASTQ |
| `strict` | bool | `true` | Fail on any mismatch |
| `low_memory` | bool | `false` | Accepted for CLI parity; IDs are always read lazily |

Returns `ok`, `valid`, `matched`, `tree_only`, `seq_only`, `errors`, `warnings`, `sequences_count`.

Errors: missing `sequences_file` → `missing_sequences_file`; no tree tips → `tree_parse_error/no_tip_labels`; sequence read failure → `tree_parse_error/seq_read_failed`; `strict=true` with mismatches → `validation_failed/cross_validation_failed`. The first tree is always used.

## 5. Analysis tools (T07–T09)

### T07 `check_monophyly`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` / `tree_file` | string | `null` | Tree source (mutually exclusive) |
| `groups` | array | `null` | **Required**; entries are group-name strings or exact `list[str]` taxon-label lists; both kinds may be mixed |
| `taxonomy_levels` | string | `null` | `prefix:rank,...`, e.g. `d:domain,p:phylum` |
| `strict` | bool | `false` | Fail if any group is non-monophyletic |

Returns `ok`, `results` (array) and `notes`. Each result contains `group`, `is_monophyletic`, `resolved_taxa_count`, `resolved_taxa_preview` (up to 10), `special_identifier`, `warnings`, `mrca_terminals` and `note`.

The two entry kinds behave differently:

- **Group name (string)**: resolved through `check_monophyly_by_group`. If that resolver raises `ValidationError` for a label dialect it cannot parse (typically GTDB labels with a superphylum segment), the server **falls back to taxonomy analysis**: it runs `analyze_taxonomy` for `domain`…`species`, matches the group name after stripping leading/trailing underscores against the `monophyletic`/`non_monophyletic` keys, and passes the resolved tip list to `check_monophyly`. On success the result `note` reads “resolved group members through taxonomy analysis”. If both paths fail the call returns `monophyly_error/group_not_found`; a failing list check returns `taxa_check_failed`.
- **Exact taxon-label list (`list[str]`)**: must be a **non-empty** list of strings and is passed directly to `check_monophyly` without taxonomy resolution. The `group` field is the comma-joined labels (≤10) or `N taxa`. If some labels are absent from the tree, `mrca_terminals` can be empty and an “MRCA not found” warning is emitted.

`LUCA`, `LACA`, `LBCA` and `root` are figtreekit special identifiers (case-sensitive): `LUCA` resolves to all tips, `LACA`/`LBCA` to all tips of the corresponding domain. Their results have `special_identifier=true` and a `note` describing the scope. With `strict=true` and any non-monophyletic group, the call fails with `monophyly_error/non_monophyletic_groups`. Only the first tree is analysed.

Errors: missing `groups` → `missing_groups`; empty or non-string list → `bad_group_taxa`; an entry that is neither a string nor a string list → `bad_group_entry`; unresolvable group → `group_not_found`; a rejected list → `taxa_check_failed`.

### T08 `analyze_taxonomy`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` / `tree_file` | string | `null` | Tree source |
| `rank` | string | **required** | `domain`/`superphylum`/`phylum`/`class`/`order`/`family`/`genus`/`species` |
| `taxonomy_mapping_file` | string | `null` | Whitelisted CSV/TSV mapping |
| `taxonomy_levels` | string | `null` | Custom rank prefixes |
| `group_size_min` | int | `1` | Report only groups with at least this many tips; must be ≥1 |

Returns `ok`, `rank`, `summary` (`total_labels`, `mapped_labels`, `unmapped_labels`, `total_groups`, `single_taxon_groups`, `monophyletic`, `non_monophyletic`, `monophyly_rate` rounded to one decimal), `monophyletic`/`non_monophyletic` (each `{group, taxa_count}`, sorted by descending taxa_count), `unmapped` (up to 200), `unmapped_total`, `warnings`, `run_dir`.

Errors: missing rank → `missing_rank`; bad rank → `bad_rank`; bad `group_size_min` → `bad_group_size_min`.

### T09 `taxonomy_completeness`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` / `tree_file` | string | `null` | Tree source |
| `taxonomy_mapping_file` | string | `null` | Whitelisted mapping table |
| `taxonomy_levels` | string | `null` | Custom rank prefixes |

Returns `ok`, `coverage` (0–100, two decimals), `complete`/`incomplete`/`missing` (each truncated to 200), their `*_total` values, and `rank_coverage`. This tool does not allocate a `run_dir`.

## 6. Styling and export tools (T10–T12)

### T10 `style_tree` (core)

**Parameter surface** (all optional; `null` means leave the figtreekit default unchanged):

| Group | Parameter | Type | Default | Description |
|-------|-----------|------|---------|-------------|
| Source/taxonomy | `tree_content` | string | `null` | Tree text (mutually exclusive with `tree_file`) |
| | `tree_file` | string | `null` | Whitelisted file |
| | `taxonomy_levels` | string | `null` | `prefix:rank,...`; active for loading **and** analysis |
| | `taxonomy_mapping_file` | string | `null` | Whitelisted mapping table |
| | `table_sep` | string | `null` | Single-character mapping separator |
| | `taxonomy_delimiter_mode` | string | `null` | `reverse`/`greedy`/`segment` |
| Layout | `layout` | string | `null` | `rectilinear`/`polar`/`radial` |
| | `expansion` | int | `null` | Expansion, must be ≥0 |
| | `zoom` | number | `null` | Must be >0 |
| Tree | `rooted` | bool | `null` | Set rooted |
| | `unrooted` | bool | `null` | Set unrooted; if both are given, `unrooted` wins |
| | `rooting_type` | string | `null` | `user`/`midpoint` |
| | `transform` | string | `null` | `cladogram`/`phylogram` |
| | `order` | string | `null` | `increasing`/`decreasing` |
| Appearance | `background_color` | string | `null` | `#RRGGBB` |
| | `foreground_color` | string | `null` | `#RRGGBB` |
| | `selection_color` | string | `null` | `#RRGGBB` |
| | `branch_width` | number | `null` | Must be >0 |
| | `branch_color_attribute` | string | `null` | Branch color attribute |
| Tip labels | `tip_labels` | string | `null` | `show`/`hide` |
| | `tip_label_font_name` | string | `null` | Font name |
| | `tip_label_font_size` | int | `null` | Must be >0 |
| | `tip_label_font_style` | int | `null` | 0 plain / 1 bold / 2 italic / 3 bold-italic |
| | `label_color` | string | `null` | `#RRGGBB` |
| | `align_tip_labels` | bool | `null` | Align tip labels |
| Node/branch labels | `node_labels` | string | `null` | `show`/`hide` |
| | `node_display_attribute` | string | `null` | Node display attribute; implies showing node labels |
| | `branch_labels` | string | `null` | `show`/`hide` |
| | `branch_display_attribute` | string | `null` | Branch display attribute; implies showing branch labels |
| Scale | `scale_bar` | string | `null` | `show`/`hide` |
| | `scale_axis` | string | `null` | `show`/`hide` |
| | `scale_axis_reverse` | bool | `null` | Reverse the axis |
| | `scale_axis_font_size` | int | `null` | Must be >0 |
| | `scale_axis_significant_digits` | int | `null` | Must be >0 |
| | `root_age` | number | `null` | Must be ≥0 |
| | `scale_factor` | number | `null` | Must be >0 |
| Polar | `polar_angular_range_degrees` | number | `null` | [0, 360] |
| | `polar_root_angle_degrees` | number | `null` | [0, 360] |
| Radial/rectilinear | `radial_spread` | number | `null` | ≥0 |
| | `curvature` | int | `null` | ≥0 |
| | `root_length` | int | `null` | ≥0 |
| Legend | `legend` | string | `null` | `show`/`hide` |
| | `legend_position` | string | `null` | `top`/`bottom`/`left`/`right` |
| Taxonomy-driven | `auto_color_rank` | string | `null` | Auto-color groups at a rank |
| | `collapse_rank` | string | `null` | Collapse groups at a rank; **always** performs a phylum color pass first |
| | `collapse_style` | string | `"collapse"` | `collapse`/`cartoon` |
| Operations/advanced | `operations` | array | `null` | Ordered clade operations, see §6.1 |
| | `additional_config` | object | `null` | Figtree block keys, rendered through `--set` |
| Multi-tree/artifact | `multi_tree` | string | `null` | `first`/`last`/`random`/`split`/`all`/`ask` |
| | `tree_index` | int | `null` | 0-based; integer, ≥0 |
| | `seed` | int | `null` | Seed for `multi_tree=random` |
| | `run_name` | string | `null` | Artifact base name: letters/digits/`_`/`-`, 1–64 chars |

**Returns**: `ok`, `nexus_file` (artifact descriptor), `cli_command`, `config_json` (string), `operations_applied` (array), `summary` (`tips`, `internal_nodes`, `rooted`, `layout`, `tree_count`, `format`), `run_dir`; a `warnings` string array is added when a parameter combination cannot be reproduced exactly by the CLI.

**Errors**: validation → `invalid_argument` with `error_key=param_validation_failed` and per-field `details`; multi-tree ambiguity → `multi_tree_required`; `multi_tree=ask` → `multi_tree_ask`; out-of-range index → `tree_index_out_of_range`; source errors → `mutually_exclusive_source`/`missing_tree_source`; taxonomy conflict → `taxonomy_conflict`; a malformed `taxonomy_levels` → `bad_taxonomy_spec`; an invalid `taxonomy_delimiter_mode` → `bad_delimiter_mode`; a mapping file outside the roots or over the limit → `access_denied`/`input_too_large`.

**Execution order**:

1. Load the tree and apply base styling (appearance → layout → tree properties → labels → scale → polar/radial/rectilinear → legend → `additional_config`);
2. Annotation operations (`highlight`/`color`/`color_all`/`font`/`clear_hilights`);
3. `auto_color_rank` coloring;
4. `collapse_rank` (when set, always color at phylum first, then collapse at the target rank);
5. Collapse operations (`collapse`/`collapse_group`/`collapse_rank`);
6. Export Nexus, write `input.tre` and the artifact, build `cli_command`/`config_json`.

**Multi-tree semantics**:

- `first`/`last`/`random`: style and export only the selected tree (`single_tree=True`); pair `random` with `seed`;
- `split`/`all`: preserve all trees, style only the selected one, and return a `warnings` entry explaining that the CLI writes one file per tree and the layout differs;
- `tree_index` has no CLI flag; replay may not select by index, and a `warnings` entry is returned when relevant.

#### 6.1 `operations` schema

| `op` | Required | Optional fields and defaults | Notes |
|------|----------|------------------------------|-------|
| `highlight` | `taxa: list[str]` | `color` (`#804548`), `width` (4, >0), `offset` (0, integer) | Background highlight band |
| `color` | `taxa: list[str]` | `color` (`#999999`) | Color the MRCA branch only |
| `color_all` | `taxa: list[str]` | `color` (`#999999`) | Color all descendant branches; the CLI `--color-all` is global |
| `font` | `taxa: list[str]` | `font_name` (`Arial`), `font_style` (0–3, default 0), `font_size` (12, >0) | Tip-label font |
| `collapse` | `taxa: list[str]` | `label`, `collapse_type` (`collapse`/`cartoon`, default `collapse`) | Collapse by exact taxon names |
| `collapse_group` | `group: str` | `label`, `collapse_type` | Collapse by group name |
| `collapse_rank` | `rank` (default `class`) | `collapse_style`/`collapse_type` (default `collapse`), `auto_color_rank` | Collapse by rank |
| `clear_hilights` | none | none | Clear highlights |

`taxa` must be a **non-empty array of non-empty strings**. Per-operation results are recorded in `operations_applied` with `status` values such as `applied`, `skipped`, `error`, `noop` or `info`.

#### 6.2 `cli_command` and `config_json` caveats

- `cli_command` looks like `python -m figtreekit "<input.tre>" -o "<output.nex>" --force ...` and uses a **literal `python`**, not the server interpreter path. Replace it with the correct interpreter or activate the same virtual environment when replaying.
- Paths and `#RRGGBB` colors are shell-quoted for POSIX shells. `cmd.exe` quoting differs; use Git Bash or adjust for PowerShell.
- `config_json` is a **string** and must be parsed again. It contains FigTree block keys only, not CLI-only switches.
- Polar angles are converted to FigTree internal units: `polarLayout.angularRange = (360 - polar_angular_range_degrees) * 1000`, `polarLayout.rootAngle = (polar_root_angle_degrees - 180) * 1000`.
- `--color-all` is a global switch and is emitted at most once. Mixing `color` and `color_all` cannot be expressed exactly; a warning is returned.
- `collapse_group` labels/non-default collapse styles have no exact CLI equivalent; the implementation uses resolved taxa where possible and warns otherwise.
- `multi_tree=split/all`, `random` without `seed`, and `tree_index`-only selection can produce warnings. Do not assume byte-for-byte equivalence in those cases.

### T11 `apply_config`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` / `tree_file` | string | `null` | Tree source |
| `config` | object | `null` | Figtree block keys (dot-separated) |
| `operations` | array | `null` | Same schema as `style_tree` |
| `auto_color_rank` | string | `null` | Auto-color rank |
| `collapse_rank` | string | `null` | Collapse rank |
| `collapse_style` | string | `"collapse"` | `collapse`/`cartoon` |
| `taxonomy_levels` | string | `null` | Custom rank prefixes; active during loading and analysis |
| `taxonomy_mapping_file` | string | `null` | Whitelisted mapping table |
| `multi_tree` | string | `null` | Multi-tree mode |
| `tree_index` | int | `null` | 0-based index |
| `seed` | int | `null` | Reproducible `random` selection |
| `run_name` | string | `null` | Artifact base name |

Returns the same common fields as `style_tree`. A non-object `config` gives `bad_config_type`; `operations`/enum/numeric validation failures give `param_validation_failed`. Keys are applied through figtreekit's `apply_dict`, with light boolean/number/`null` coercion.

`config_json` merges `additional_config`, but taxonomy-driven parameters such as `auto_color_rank`/`collapse_rank` are not keys in `to_config_dict`; they appear in `cli_command` and `operations_applied` instead.

### T12 `export_nexus`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tree_content` / `tree_file` | string | `null` | Tree source |
| `include_taxa_block` | bool | `true` | Emit a TAXA block |
| `run_name` | string | `null` | Artifact base name |

Returns `ok`, `nexus_file`, `cli_command` (no styling arguments, with `--force`), `config_json` (always `"{}"`), `summary`, `operations_applied` (empty), `run_dir`. This is a structural Newick→Nexus conversion without styling. With `include_taxa_block=false` and Newick input, figtreekit emits a compatibility warning and the output may lack a taxa block. An invalid `run_name` gives `invalid_argument/bad_run_name`.

## 7. Clade tools (T13–T19)

All clade tools return the common fields `ok`, `nexus_file`, `cli_command`, `config_json` (`"{}"`), `operations_applied`, `summary`, `run_dir`, plus their own counters. They only process the **first tree** and do not expose `multi_tree`/`tree_index`/`seed`.

### T13 `highlight_clade`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `highlights` | array | `null` | **Required**; each `{taxa, color?, width?, offset?}` |
| `clear_existing` | bool | `false` | Clear pending highlights and embedded `[&!hilight=...]` first |
| `run_name` | string | `null` | Artifact base name |

Each entry: `taxa` is a non-empty string array; `color` defaults to `#999999`; `width` defaults to 4 and must be >0; `offset` defaults to 0 and must be an integer (the CLI parses it with `int()`). Returns an extra `highlights_applied`. Errors: `missing_highlights`, `bad_taxa`, `bad_color`, `bad_width`, `bad_offset`.

### T14 `color_clade`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `colors` | array | `null` | **Required**; each `{taxa, color?, all?}` |
| `run_name` | string | `null` | Artifact base name |

`color` defaults to `#999999`; `all=true` colors all descendant branches, otherwise only the MRCA branch. Returns `colors_applied`. Errors: `missing_colors`, `bad_taxa`, `bad_color`.

### T15 `set_clade_font`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fonts` | array | `null` | **Required**; each `{taxa, font_name?, font_style?, font_size?}` |
| `run_name` | string | `null` | Artifact base name |

`font_name` defaults to `Arial`; `font_style` defaults to 0 (0 plain/1 bold/2 italic/3 bold-italic); `font_size` defaults to 12 and must be >0. Returns `fonts_applied`. Errors: `missing_fonts`, `bad_taxa`, `bad_font`.

### T16 `collapse_clade`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `collapses` | array | `null` | **Required**; each `{taxa, label?, collapse_type?}` |
| `run_name` | string | `null` | Artifact base name |

`collapse_type` defaults to `collapse`, optionally `cartoon`. Returns `collapses_applied`. Non-monophyletic or compatibility-warning cases are recorded as `skipped` without failing the whole call. Errors: `missing_collapses`, `bad_taxa`, `bad_collapse_type`.

### T17 `collapse_group`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `groups` | array | `null` | **Required**; each `{"group": str, "label"?: str, "collapse_type"?: "collapse"/"cartoon"}` |
| `strict` | bool | `false` | Fail when a group cannot be resolved, is non-monophyletic, or cannot be collapsed |
| `taxonomy_levels` | string | `null` | Custom rank prefixes |
| `taxonomy_mapping_file` | string | `null` | Whitelisted mapping table |
| `run_name` | string | `null` | Artifact base name |

The signature is `collapse_group(tree_content=None, tree_file=None, groups=[{"group": ..., "label": ..., "collapse_type": ...}], strict=False, taxonomy_levels=None, taxonomy_mapping_file=None, run_name=None)`. Each `group` must be a non-empty group name; omitting `label` keeps the figtreekit default label, and `collapse_type` defaults to `collapse`. Extra fields are ignored (this tool does not validate colors).

Each group is pre-checked with `check_monophyly_by_group` and then collapsed with `collapse_by_group`. Unresolvable or non-monophyletic groups are recorded as `skipped` and the remaining groups are still processed; with `strict=true` the call raises `monophyly_error` with `error_key` `collapse_group_failed` or `collapse_non_monophyletic`. Returns `groups_applied`. Errors: `missing_groups`, `bad_group`, `bad_collapse_type`.

Reproducibility: without a `label` or non-default `collapse_type`, `cli_command` uses `--clade <group>`; when a label or style must be carried it uses the resolved taxon list with `--collapse-taxa`, and warns if exact equivalence is impossible.

### T18 `collapse_rank`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rank` | string | code uses `"class"` when omitted | Rank to collapse |
| `collapse_style` | string | `"collapse"` | `collapse`/`cartoon` |
| `auto_color_rank` | string | `null` | Pre-collapse color rank; falls back to `phylum` |
| `strict` | bool | `false` | Raise `monophyly_error` on failure |
| `taxonomy_levels` | string | `null` | Custom rank prefixes |
| `taxonomy_mapping_file` | string | `null` | Whitelisted mapping table |
| `run_name` | string | `null` | Artifact base name |

The tool first analyzes/colors at `auto_color_rank or "phylum"`, then analyzes `rank` and collapses every monophyletic group. Single-taxon groups are still attempted (CLI parity). Returns extra `collapsed_groups`, `skipped_groups`, and `warnings` when compatibility warnings exist. Errors: `bad_rank`, `bad_collapse_style`; under `strict`, `collapse_strict_failed`.

### T19 `clear_annotations`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `clear_hilights` | bool | `true` | Clear highlights, including embedded `[&!hilight=...]` |
| `clear_collapses` | bool | `true` | Clear collapses/cartoons, including embedded `[&!collapse=...]`/`[&!cartoon=...]` |
| `strip_annotations` | bool | `false` | Strip generic `[&...]` annotations, preserving `[&R]`/`[&U]` root markers |
| `run_name` | string | `null` | Artifact base name |

This tool does **not** clear branch colors or fonts; use `color_clade`/`set_clade_font`. Returns the common fields; `operations_applied` records the actions actually performed. The CLI only offers `--clear-hilights` and has no flag for clearing collapses, so `cli_command` cannot reproduce `clear_collapses` (`config_json` is `"{}"`).

## 8. Rendering tool (T20)

### T20 `render_tree`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nexus_file` | string | `null` | Whitelisted Nexus file; takes precedence over `tree_content` |
| `tree_content` | string | `null` | Tree text; written to `input.nex` in the run directory |
| `format` | string | `null` (PNG) | `PNG`/`PDF`/`SVG`/`JPEG` (case-insensitive) |
| `width` | int | `1600` | Must be >0 |
| `height` | int | `1000` | Must be >0 |
| `background_color` | string | `null` | `#RRGGBB`, raster post-processing |
| `foreground_color` | string | `null` | `#RRGGBB`, raster post-processing |
| `label_color` | string | `null` | `#RRGGBB`, protected label color |
| `jar_path` | string | `null` | Explicit JAR; otherwise server `--jar`/auto-detection |
| `timeout` | int | `null` | When omitted, uses `AppContext.render_timeout` (`--render-timeout`, default 180) |
| `run_name` | string | `null` | Artifact base name |

Returns `ok`, `image` (with `data_uri`/`mime`, plus `width`/`height` for PNG/JPEG), `cli_command`, `config_json`, `reproducible` (bool), `warnings` (array; warns when colors cannot be reproduced), `format`, `width`, `height`, `run_dir`, `ext`.

Errors: no input → `missing_render_input`; bad format → `render_bad_format/bad_render_format`; bad size/timeout → `bad_render_size`/`bad_render_timeout`; `nexus_file` is not a file → `nexus_not_a_file`; missing Java → `java_missing`; missing JAR → `jar_missing`; render failure/timeout → `render_failed`/`render_timeout`.

Notes:

- If both `nexus_file` and `tree_content` are supplied, `nexus_file` is used without a mutual-exclusion error.
- `cli_command` is **display-only**; MCP never executes the string. It uses `python -m figtreekit <input> -o <run_dir>/render.nex --force --render <image> --render-format ... --figtree-jar ...`, writes a companion `render.nex` next to the image (the CLI still requires `-o` in render mode), and cannot reproduce Python-side background/foreground/label post-processing (`reproducible=false` in that case).
- `image.data_uri` is generated only for files ≤512 KiB. PDF also gets a data URI (MIME `application/pdf`) under the same limit.
- All four formats are accepted, but automated tests currently cover PNG/SVG only; PDF/JPEG have no pixel or structural assertions.

## 9. Pass-through tool (T21)

### T21 `run_figtreekit_cli`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `argv` | array | `null` | **Required**; figtreekit arguments, without interpreter/module name |
| `tree_content` | string | `null` | Written to `input.tre` and substituted for `<input>` |
| `input_file` | string | `null` | Whitelisted input file substituted for `<input>` |
| `timeout` | int | `300` | Subprocess timeout in seconds |
| `capture_tail_bytes` | int | `65536` | stdout/stderr tail bytes to keep, max 65536 |

Restrictions:

- `argv` has 1–256 elements; each must be a string of at most 4096 characters.
- `argv[0]` may not be `figtreekit`, `python`, `python3` or `-m`.
- `--figtree-jar` is rejected (`figtree_jar_forbidden`) because it would bypass controlled JAR selection.
- Input whitelisting applies to `--config`, `--taxonomy-mapping-file` and `--sequences` (both `--flag value` and `--flag=value`); positional tokens that resolve to existing relative paths are also checked against the run directory.
- `--table-sep` and `--taxonomy-table-sep` are **value** flags (single-character separators), not file paths, so they are neither whitelisted nor checked for existence; passing a path there simply makes figtreekit reject the argument.
- All output flags `-o`, `--output`, `--out`, `--render`, `--log-file` (including `-oFILE` and `--flag=value`) are forcibly rewritten to a basename inside the run directory, and every rewrite is listed in `rewrites`. Unsafe targets give `bad_output_target` or `output_escape`.
- `tree_content` and `input_file` are mutually exclusive.
- The working directory is this call's `run_dir`; the command is `[sys.executable, "-m", "figtreekit", *argv]` with `shell=False`.
- A non-zero exit gives `cli_failed` with `returncode` and stdout/stderr tails in `details`; a timeout gives `cli_timeout`.

Returns `ok`, `returncode`, `stdout_tail`, `stderr_tail`, `artifacts` (matching `.nex/.png/.pdf/.svg/.jpg/.jpeg/.log/.txt/.json/.newick/.tre` files in the run directory, excluding `input.tre`, with image data URIs), `rewrites`, `elapsed_s`, `run_dir`.

`artifacts` scans all matching files in the run directory rather than a delta; through MCP each call has a fresh directory, so this is usually equivalent. `timeout` defaults to 300 seconds and does **not** read `--cli-timeout` (known gap).

## 10. Resources (3)

| URI | Type | Payload |
|-----|------|---------|
| `figtreekit://version` | JSON | `figtreekit_version`, `mcp_server_version`, `biopython_version`, `python_version`, `mcp_sdk_version`, `pillow`, `java:{ok,version}`, `jar:{ok,path}`, `render_ready`, `workspace_root`, `allowed_read_roots`; may contain `server_warning` if AppContext is not initialized |
| `figtreekit://help` | text/Markdown | A short Chinese note plus the full `figtreekit` CLI `--help` text in a code block |
| `figtreekit://defaults` | JSON | figtreekit's FigTree defaults (figtree block keys); returns `{"error": ...}` if generation fails |

## 11. Prompts (2)

| Name | Arguments (defaults) | Actual behavior |
|------|----------------------|-----------------|
| `create-publication-figure` | `tree_file` (null), `tree_content` (null), `layout` (`"polar"`), `collapse_rank` (`"class"`), `render_formats` (`"PNG,PDF"`) | Returns bilingual long text (Chinese first, English quick reference at the end) guiding T04→T05→T08 (optional)→T10→T20. `tree_file`, `layout`, `collapse_rank` and `render_formats` are interpolated; `tree_content` is represented only as a source note (“inline tree_content provided”/“no tree source supplied”), **not embedded verbatim** |
| `taxonomy-audit` | `tree_file` (null), `tree_content` (null), `rank` (`"phylum"`) | Returns bilingual long text guiding T04→T05→T08→T09→T07→T10. `rank` and the tree-source note are interpolated; `tree_content` is again only a source note |

Prompts are workflow instructions for the model, not tool calls. When no tree source is supplied, the template asks the model to request one from the user.

## 12. Startup options (`_cli.py`)

| Option | Default | Description |
|--------|---------|-------------|
| `--transport` | `stdio` | `stdio`/`sse`/`http`; `http` runs MCP Streamable HTTP (`streamable-http`) |
| `--host` | `127.0.0.1` | SSE/HTTP bind host; loopback by default |
| `--port` | `8777` | SSE/HTTP port, >0 |
| `--allow-remote-bind` | false | Allow non-loopback binding |
| `--workspace-root` | `<cwd>/figtreekit-mcp-workspace` | Writable workspace; created if needed |
| `--allow-read-root DIR` | empty | Read-only root, repeatable |
| `--jar PATH` | null | Explicit JAR path |
| `--content-max-bytes` | `10485760` | `tree_content` limit, >0 |
| `--file-max-bytes` | `209715200` | Whitelisted file limit, >0 |
| `--cli-timeout` | `300` | Pass-through timeout setting (not currently read by `run_figtreekit_cli`, see §9) |
| `--render-timeout` | `180` | Used by `render_tree` when `timeout` is omitted |
| `--setup-timeout` | `600` | `setup_figtree` install timeout |
| `--keep-runs` | `50` | Run directories kept; swept every 16 new runs during long sessions and at shutdown; 0 cleans all old directories |
| `-v` / `--verbose` | 0 | Repeatable; `-v` INFO, `-vv` DEBUG |
| `-q` / `--quiet` | false | ERROR only |
| `--log-file PATH` | null | Append DEBUG-level logs to a file |
| `--self-test` | false | Run diagnostics and exit 0/1 |
| `--version` | — | Prints `figtreekit-mcp 0.1.0` |
| `-h` / `--help` | — | Print help and exit |

Exit codes: 0 success, 1 runtime/self-test failure, 2 usage error, 130 interrupted by SIGINT/SIGTERM. Logs go to stderr; stdout carries MCP protocol frames only (except the terminal output of `--self-test` and `--version`).

## 13. Multi-tree semantics

| Scenario | Behavior |
|----------|----------|
| `summarize_tree` with multiple trees and no selection | Defaults to `first`, returns `multi_tree_hint`, no error |
| `style_tree`/`apply_config` with multiple trees and no selection | Raises `multi_tree_required` unless `tree_index` is given |
| `multi_tree=ask` | Raises `multi_tree_ask` |
| `first`/`last`/`random` | Selects one tree; `style_tree`/`apply_config` export only that tree; use `seed` with `random` |
| `split`/`all` | Preserves all trees but styles only one (index 0 by default, or `tree_index`); a single MCP artifact cannot write one file per tree like the CLI, so a layout-difference warning is returned |
| `tree_index` | 0-based; out of range raises `tree_index_out_of_range`; no CLI equivalent |
| Analysis/validation/clade tools | Internally fixed to `first`; no multi-tree parameters |

## 14. Known limitations and implementation gaps

1. **Real-data tests are conditional**: without `FigTreeKit-参考文件/参考数据-GTDB-R232` or `FigTreeKit-功能展示/输入文件/...`, the relevant tests skip. A skip is not a pass.
2. **Incomplete render coverage**: PNG/PDF/SVG/JPEG are accepted, but automated tests cover PNG/SVG only; the pixel-diff probe compares PNG only. PDF/JPEG have no structural or pixel assertions.
3. **`--cli-timeout` is not wired**: it is parsed and stored, but `run_figtreekit_cli` defaults to 300 seconds independently. Pass `timeout` explicitly.
4. **Prompt `tree_content` is not embedded verbatim**: templates are bilingual; `tree_content` is represented as a source note, while the other main arguments are interpolated.
5. **`clear_annotations` does not clear colors/fonts**: it handles highlights and collapses (including embedded comments) only.
6. **`style_tree` `split/all` is not equivalent to the CLI**: the CLI writes one file per tree; MCP returns one artifact with all trees but styles only the selected one.
7. **`cli_command` uses a literal `python`**: replace it with the actual interpreter; `config_json` is a string.
8. **`run_name` is not a directory name**: it is only the artifact filename base and cannot contain `/`, `\` or `..`.
9. **Errors may arrive as normal results**: the MCP registration layer converts `ToolError` into an `ok:false` envelope, so clients must not rely on `isError` alone.
10. **One AppContext per process**: creating multiple servers in one process is unsupported; tools/resources use the module-level active context.
11. **No network authentication**: SSE/HTTP have no auth/TLS; `--allow-remote-bind` only relaxes the bind guard.
12. **`color` and `color_all` cannot be mixed in one CLI replay**: the CLI `--color-all` is a global switch that applies to every `--color-clade` in the command. When one `style_tree`/`apply_config` call contains both operations, the MCP result is correct but the replayed `cli_command` treats all coloring as `color_all`, and a `warnings` entry is returned.
13. **T07 group-name resolution has edge cases**: names depend on taxonomy embedded in labels, `taxonomy_levels` or a mapping file; GTDB-style labels may fail first and then use the taxonomy fallback; matching strips leading/trailing underscores, so identical names at different ranks may match the first rank traversed; only `LUCA`/`LACA`/`LBCA`/`root` are special (case-sensitive). Pass an exact taxon list when in doubt.
