# Testing and Acceptance

[简体中文](testing_and_acceptance_CN.md) | **English**

Applies to version **0.1.0**. This guide covers the test layout, commands, coverage, self-test, equivalence probe, GTDB acceptance script, debug client, and how to reproduce AC/SEC checks. **A skipped test is not a pass.** Without real data, the corresponding acceptance claims are unverified.

## 1. Test layout

`tests/` uses pytest. `pyproject.toml` sets `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and registers one custom marker: `slow`.

| File | Coverage |
|------|----------|
| `conftest.py` | Shared fixtures: small/taxonomy/multi-tree/FASTA/FASTQ text, temporary workspace, `AppContext`, fake `Context`, `call` helper, real-data discovery and skips |
| `test_environment_tools.py` | T01–T03: version shape, Java/JAR probes, check/setup with `check_only` |
| `test_validate_tools.py` | T04–T06: Newick/Nexus/FASTA/FASTQ, negative branches, multi-tree, cross-validation, translate block |
| `test_analyze_tools.py` | T07–T09: taxon/group lists, strict mode, mapping tables, conditional GTDB tests |
| `test_style_tools.py` | T10–T12: export, `cli_command`, `config_json`, polar, multi-tree, run_name, showcase/GTDB conditional tests |
| `test_clade_tools.py` | T13–T19: highlights/colors/fonts/collapse/clear, error keys, conditional GTDB tests |
| `test_render_tools.py` | T20: input validation, envelopes; real PNG/SVG rendering (skipped without Java) |
| `test_passthrough.py` | T21: argv limits, output rewriting, zero shell, real styling command, `--help`, failure envelopes, input whitelist |
| `test_params.py` | `ParamSpec` validation, `to_cli_args`, `to_config_dict`, operation rendering, enum stability |
| `test_cli_command.py` | Command assembly, `#RRGGBB` quoting, `shlex` round trip |
| `test_errors.py` | 19 error codes, exception mapping, envelope shape, `guard` |
| `test_logging.py` | Levels, stderr, `--log-file`, ISO timestamps, handler deduplication |
| `test_cli_entry.py` | Startup defaults, loopback guard, `--version`, `--self-test`, exit codes |
| `test_workspace.py` | Roots, whitelist, symlinks, `..`, size limits, run cleanup, artifact registration |
| `test_workspace_hardening.py` | Additional workspace/path hardening boundaries |
| `test_security.py` | SEC-1…SEC-12 (see §7) |
| `test_concurrency.py` | Global lock primitive, concurrent styling/CLI, run-directory isolation |
| `test_taxonomy_concurrency.py` | Concurrent isolation and restoration of taxonomy rank-prefix scopes (no global-state leakage) |
| `test_property_hypothesis.py` | Hypothesis properties: validation only raises `ToolError`; arbitrary colors/operations do not crash |
| `test_server_smoke.py` | Real stdio subprocess E2E: handshake, 21 tools, resources/prompts, typical calls, error path, cancellation, shutdown, stdout purity |
| `test_equivalence.py` | Six golden parameter sets, slow, requires showcase data |

The test count changes with development. Use `python -m pytest --collect-only -q` for the current number; do not treat a historical count as a constant.

## 2. Running tests

Install development dependencies first (see the development guide):

```bash
python -m pip install -e ".[dev,render]"
```

Common commands:

```bash
# Full suite
python -m pytest -q

# Exclude slow tests
python -m pytest -q -m "not slow"

# Slow tests only (equivalence/real rendering)
python -m pytest -q -m slow

# E2E protocol only
python -m pytest -q tests/test_server_smoke.py

# Security gate only
python -m pytest -q tests/test_security.py

# Coverage (configured target 80%)
python -m pytest -q --cov=figtreekit_mcp --cov-report=term-missing

# Self-test
python -m figtreekit_mcp --self-test

# Collection count
python -m pytest --collect-only -q
```

On Windows, if `pytest` is not on `PATH`, use `python -m pytest`, or `<python> -m pytest` when the environment is not active. On Chinese Windows, if `PYTHONIOENCODING=utf-8` is set, also set `PYTHONUTF8=1` so parent and child processes use the same UTF-8 encoding.

`pyproject.toml` sets `timeout = 1800` and `timeout_method = "thread"`: each test gets at most 1800 seconds, so slow JVM rendering is not mistaken for a hang while genuinely stuck tests are still bounded.

## 3. Coverage

`pyproject.toml` contains:

```toml
[tool.coverage.run]
source = ["figtreekit_mcp"]
omit = ["*/tests/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

The target is **80%**. Notes:

- `--self-test`, E2E subprocesses and XML/stdio protocol paths may not be counted by in-process coverage.
- Coverage of a subset that excludes slow/E2E tests differs from full-suite coverage; state the command in any report.
- The coverage gate is **80%**; actual values depend on the command and test subset, so re-measure and state the command in any report.
- Meeting the coverage target does not prove correctness; review skips and real-data tests as well.

## 4. `--self-test`

```bash
python -m figtreekit_mcp --self-test \
  --workspace-root "<workspace>"
```

Checks:

1. Importable dependencies: `mcp`, `figtreekit`, `Bio`;
2. Exactly 21 registered tools with the complete expected name set;
3. No bare `print()` to stdout in package source (terminal output in `_cli.py`/`__main__.py` is exempt);
4. Java probe (missing is `[WARN]`, not failure);
5. JAR probe (missing is `[WARN]`, not failure);
6. `style_tree` → `.nex` round trip on a small tree;
7. Workspace writable + out-of-root path rejected;
8. PNG render when Java is available (`[WARN] skipped` otherwise).

All pass → exit 0; any failure → 1. Missing Java/JAR affects only rendering.

## 5. Test data and skip semantics

### 5.1 Discovery paths

`tests/conftest.py` searches up to six parent levels from `tests/` for:

- GTDB: `FigTreeKit-参考文件/参考数据-GTDB-R232/`
  - expects `ar53_r232.tree`, `ar53_r232_taxonomy.tsv`, `ar53_r232_class.tree`, `ar53_r232_phylum.tree`, etc.;
- Showcase: `FigTreeKit-功能展示/输入文件/FigTree_withLACA_CLK_95CI.tree.recover` and `.tsv`.

Typical layout:

```text
<parent>/
├── <repo>/                      ← this repository
├── FigTreeKit-参考文件/
│   └── 参考数据-GTDB-R232/
└── FigTreeKit-功能展示/
    └── 输入文件/
        ├── FigTree_withLACA_CLK_95CI.tree.recover
        └── FigTree_withLACA_CLK_95CI.tsv
```

If a directory is absent, the fixture calls `pytest.skip(...)`. Depending on fixture order you may see “GTDB directory missing” or “ar53_r232_phylum.tree missing”; both mean the real data is unavailable.

### 5.2 Skip types

| Skip reason | Impact |
|-------------|--------|
| GTDB directory/files missing | GTDB integration tests in T07–T09, T10, T17/T18 skip |
| Showcase tree/TSV missing | Showcase style/validate tests and `test_equivalence.py` skip |
| Java unavailable | PNG/SVG real-render tests in `test_render_tools.py` skip |
| Render dependencies missing | SEC-9 real render-timeout test skips |
| Marker selection | e.g. `-m "not slow"` deselects slow tests |

**A skip is not a pass.** Reports should list passed / failed / skipped separately with reasons. Without data, AC-4/5/6/12 can only be called “unverified”.

### 5.3 Supplying data manually

- Place the data at the relative locations above; or
- Adjust fixtures (not recommended to edit tests permanently); or
- Pass explicit `--read-root` / `--allow-read-root` to standalone scripts.

`tools/gtdb_acceptance.py` resolves data from `--read-root`, `FIGTREEKIT_GTDB_DIR`, `FIGTREEKIT_MCP_GTDB_DIR`, or a sibling directory; `tools/mcp_debug_client.py` takes read roots from repeated `--allow-read-root` or `FIGTREEKIT_MCP_READ_ROOTS`. For reproducibility, **always pass `--read-root`/`--allow-read-root` explicitly.**

## 6. Debug client `tools/mcp_debug_client.py`

Starts the server as a real stdio subprocess with the official `mcp` client:

```bash
# List the 21 tools
python tools/mcp_debug_client.py --list-tools \
  --workspace-root "<workspace>" \
  --allow-read-root "<data-dir>"

# Call a tool with JSON arguments
python tools/mcp_debug_client.py --call summarize_tree \
  '{"tree_content":"(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"}' \
  --workspace-root "<workspace>"

# Read a resource
python tools/mcp_debug_client.py --read-resource figtreekit://version \
  --workspace-root "<workspace>"

# Dump every tool's JSON Schema
python tools/mcp_debug_client.py --dump-schema --workspace-root "<workspace>"

# Fetch a prompt
python tools/mcp_debug_client.py --prompt create-publication-figure \
  --workspace-root "<workspace>"
```

- The second `--call` argument is a JSON string; use `{}` for an empty object.
- `--allow-read-root` is repeatable. Without it the script reads `FIGTREEKIT_MCP_READ_ROOTS` (separated by `os.pathsep`) or uses no roots; pass it explicitly for reproducibility.
- Output is `{"isError": ..., "content": [...]}`. Error envelopes may be inside `content[0]` with `isError=false`; parse the JSON.
- Exit codes: 0 success, 1 tool returned `isError=true`, 2 usage error; `KeyboardInterrupt` returns 130.

## 7. SEC-1…SEC-12 mapping

`tests/test_security.py` currently covers:

| ID | Check | Test focus |
|----|-------|------------|
| SEC-1 | Path traversal | `../../../../etc/passwd` rejected with `access_denied` |
| SEC-2 | Symlink escape | A symlink inside a read root pointing outside is rejected |
| SEC-3 | `run_name` traversal | `../../evil` triggers `param_validation_failed` |
| SEC-4 | Output rewriting | `-o /tmp/x.nex`, `-o ../../escaped.nex` rewritten into the run directory and disclosed |
| SEC-5 | Control/bidi characters | NUL and `U+202E` rejected with `anomalous_content` |
| SEC-6 | Size limit | 11 MiB content triggers `input_too_large` |
| SEC-7 | Zero shell | `;`/`$(...)`/`|`/`&&` are literal arguments and never execute |
| SEC-8 | Concurrency isolation | 8 styling + 2 CLI calls in parallel, each with its own run directory |
| SEC-9 | Render timeout | Deterministic injected timeout error, asserted as `render_timeout`; skipped when Java/JAR are missing |
| SEC-10 | Missing Java | `java_missing` with hints |
| SEC-11 | Missing JAR | `jar_missing` with `setup_figtree` hints |
| SEC-12 | stdout purity | Static scan finds no bare `print()` |

Run:

```bash
python -m pytest -q tests/test_security.py
```

## 8. Equivalence probe `tools/equivalence_probe.py`

For six golden parameter sets it compares:

1. **API baseline**: direct figtreekit Python API;
2. **CLI baseline**: `python -m figtreekit`;
3. **MCP baseline**: the `style_tree` handler;
4. asserts MCP `.nex` is **byte-identical** to CLI `.nex`;
5. asserts MCP/CLI are semantically identical to the API baseline after normalizing tree names/indices;
6. optionally compares MCP-rendered PNG with a direct `java -jar` PNG by pixel statistics (difference <0.5%).

Usage:

```bash
python tools/equivalence_probe.py \
  "<showcase-tree>" \
  "<taxonomy.tsv>" \
  "<workspace>"
```

Requirements:

- showcase tree and TSV must exist (for example `FigTreeKit-功能展示/输入文件/FigTree_withLACA_CLK_95CI.*`);
- the render comparison needs Java + JAR + Pillow; without them it returns “render skipped” and counts that check as passing;
- exit code 0 = all checks passed, 1 = failures, 2 = insufficient arguments;
- the CLI does not expose `--only`; `run_probe(..., only=[...])` is available only from Python.

`tests/test_equivalence.py` is the pytest entry point. Both cases are marked `slow`: one with `check_render=False`, one with `check_render=True`. Without showcase data the fixture skips; with data the run can be long, so allow enough time.

## 9. GTDB five-step acceptance `tools/gtdb_acceptance.py`

```bash
python tools/gtdb_acceptance.py \
  --read-root "<GTDB-R232-dir>" \
  --workspace-root "<workspace>"
# Skip the render step without Java/JAR
python tools/gtdb_acceptance.py \
  --read-root "<GTDB-R232-dir>" \
  --workspace-root "<workspace>" --no-render
```

The input directory must contain `ar53_r232.tree` and `ar53_r232_taxonomy.tsv`. The directory is resolved from `--read-root`, `FIGTREEKIT_GTDB_DIR`, `FIGTREEKIT_MCP_GTDB_DIR`, or a sibling directory; if none is found the script prints `[SKIP]` and returns **3** (not a failure). `--workspace-root` defaults to a temporary directory; `--no-render` explicitly skips step 4 (use it without Java/JAR).

What the five steps **actually** assert:

| Step | Call | Actual assertion |
|------|------|------------------|
| 1 | `validate_tree` | `ok=true` and `leaf_count >= 700` |
| 2 | `analyze_taxonomy(rank=class)` | Parses `figtreekit --analyze-taxonomy class` and compares `total_labels`, `mapped_labels`, `total_groups`, `monophyletic`, `non_monophyletic`, `monophyly_rate` |
| 3 | `style_tree(polar, phylum)` | Requires `cli_command` to contain `--taxonomy-levels`/`--taxonomy-mapping-file`; reruns it and compares the `.nex` **byte-for-byte** |
| 4 | `render_tree(PNG 2400×1600 + PDF)` | PNG dimensions, non-blank checks (non-white ratio and grayscale standard deviation); PDF starts with `%PDF-`. Missing Java/JAR fails this step; use `--no-render` to skip explicitly |
| 5 | `collapse_rank(class)` | Requires `collapsed_groups > 0` and `!collapse` in the `.nex`; generates an equivalent CLI `.nex` and compares **byte-for-byte** |

Thus, when data is present, AC-12 includes byte-for-byte CLI comparison. When data is absent the script prints `[SKIP]` and exits 3, and AC-12 cannot be claimed as passing. The script uses a temporary workspace by default; pass the data directory explicitly for reproducibility.

## 10. Reproducing AC-1…AC-12

| AC | Command/evidence | Notes |
|----|------------------|-------|
| AC-1 | `python -m figtreekit_mcp --self-test`; `python -c "import mcp, figtreekit, Bio, PIL"` | Imports; Pillow is optional |
| AC-2 | `python tools/mcp_debug_client.py --list-tools ...`; `pytest tests/test_server_smoke.py -q` | 21 tools + 3 resources + 2 prompts |
| AC-3 | `pytest tests/test_server_smoke.py -q` | Handshake/list/call/resources; error path see §11 |
| AC-4/5 | With GTDB data: `pytest tests/test_analyze_tools.py tests/test_validate_tools.py -q` | Skips without data |
| AC-6 | With showcase data: `pytest tests/test_equivalence.py -m slow -q`, or run the probe | Slow; byte + normalized API comparison |
| AC-7 | `pytest tests/test_render_tools.py -q`; `--self-test` | `render_tree` accepts PNG/PDF/SVG/JPEG and returns a CLI recipe; no pixel-level equivalence is claimed; Python-side color post-processing is not CLI-reproducible; PDF/JPEG have no automated assertions |
| AC-8 | `pytest tests/test_passthrough.py -q`; `mcp_debug_client --call run_figtreekit_cli '{"argv":["--help"]}'` | Real styling command and self-test path |
| AC-9 | `pytest tests/test_security.py -q` | SEC-1…12 |
| AC-10 | `pytest --cov=figtreekit_mcp --cov-report=term-missing`; `--self-test` | 80% target; use the latest output |
| AC-11 | Compare this bilingual documentation set with the source | Requires manual review |
| AC-12 | `python tools/gtdb_acceptance.py --read-root ... --workspace-root ...` | Needs GTDB data; with data it performs CLI number and byte comparisons; without data it returns 3 and `[SKIP]` |

## 11. Known gaps and cautions

1. **MCP errors are ordinary results**: the server converts `ToolError` into an `ok:false` envelope and `CallToolResult.isError` is usually `false`. The E2E tests now assert this contract; clients must inspect `ok`/`code`/`error_key` (plus `error_detail`/`details`), not only `isError`.
2. **The slow equivalence probe is expensive**: on Windows with a large tree, Java rendering/analysis can approach ten minutes. Allow enough time.
3. **The GTDB script needs data**: without data it returns 3 and prints `[SKIP]`, so AC-12 cannot be claimed as passing. With data it performs CLI number and `.nex` byte comparisons (see §9).
4. **No automated PDF/JPEG assertions**: `render_tree` accepts them, but tests cover PNG/SVG only.
5. **`--cli-timeout` is not wired**: pass-through defaults to 300 seconds; pass `timeout` explicitly in timeout tests.
6. **Data/read-root sources**: `gtdb_acceptance.py` supports `--read-root` and `FIGTREEKIT_GTDB_DIR`/`FIGTREEKIT_MCP_GTDB_DIR`; `mcp_debug_client.py` supports `--allow-read-root` and `FIGTREEKIT_MCP_READ_ROOTS`. Explicit arguments are the most reproducible option.
7. **Prompt template arguments**: templates are bilingual; `tree_content` is represented as a source note rather than embedded verbatim; `render_formats`, `tree_file`, `rank` and similar arguments are interpolated.
8. **Test data location**: the repository does not ship GTDB/showcase data. The discovery logic depends on sibling-directory layout; re-place the data if you move the repository.

## 12. Related documentation

- [`development_guide_EN.md`](development_guide_EN.md)
- [`tools_reference_EN.md`](tools_reference_EN.md)
- [`deployment_and_client_setup_EN.md`](deployment_and_client_setup_EN.md)
- [`README_EN.md`](README_EN.md)
