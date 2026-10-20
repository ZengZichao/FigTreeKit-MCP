# Development Guide

[简体中文](development_guide_CN.md) | **English**

Applies to version **0.1.0**. This guide is for developers modifying `src/figtreekit_mcp/`, adding tools, adjusting parameter mappings or debugging behavior. Per-tool parameters are documented in [`tools_reference_EN.md`](tools_reference_EN.md); test commands and acceptance are in [`testing_and_acceptance_EN.md`](testing_and_acceptance_EN.md).

## 1. Design goals

1. **Do not reimplement tree algorithms**: parsing, Nexus generation, taxonomy analysis and FigTree rendering call the public `figtreekit` API. MCP adds parameter adaptation, a security boundary and structured output.
2. **Reproducibility**: styling/export/render calls return an equivalent `cli_command` and `config_json`; cases that cannot be reproduced exactly are reported explicitly.
3. **Stateless calls**: each call has its own `run_<uuid8>` directory and local objects. The one process-global mutation (`taxonomy_levels`) is snapshot/restored.
4. **Secure defaults**: path whitelist, symlink resolution, zero shell, output containment, content scanning, size limits and loopback binding.
5. **Protocol purity**: stdout carries MCP protocol frames only; all logs go to stderr.

## 2. Layout and modules

```text
src/figtreekit_mcp/
├── __init__.py          package metadata, lazy create_server/main
├── __main__.py          python -m figtreekit_mcp
├── _version.py          static version 0.1.0
├── _cli.py              startup options, transport, signals, --self-test, exit codes
├── server.py            FastMCP assembly, AppContext, tool registration, async worker wrapper
├── resources.py         3 resources
├── prompts.py           2 prompts
├── _core.py             tree-source resolution, styler factory, multi-tree selection, taxonomy injection, bulk color/collapse
├── _workspace.py        whitelist, run directories, artifact registration, cleanup
├── _errors.py           error codes, ToolError, envelopes, exception mapping, guard
├── _logging.py          stderr/file logging, ISO timestamps, stdout ban
├── _concurrency.py      global RLock; acquired per tool call by server._threaded_tool
├── params.py            ParamSpec: validation, to_cli_args, to_config_dict
├── cli_command.py       reproducible commands and shell quoting
└── tools/
    ├── __init__.py      registry, get_app, require_run, shared helpers
    ├── environment.py   T01–T03
    ├── validate.py      T04–T06
    ├── analyze.py       T07–T09
    ├── style.py         T10–T12 + apply_mcp_styling/apply_operations
    ├── clade.py         T13–T19
    ├── render.py        T20
    └── passthrough.py   T21
```

### 2.1 Key objects

| Object | Location | Responsibility |
|--------|----------|----------------|
| `AppContext` | `server.py` | Workspace, read roots, versions, Java/JAR, limits, timeouts; `get_active_app()` returns the current instance |
| `Workspace` | `_workspace.py` | `assert_readable`/`assert_writable`, size checks, `new_run`, `cleanup` |
| `RunStorage` | `_workspace.py` | One run directory, `file_path` name validation, `register` artifact descriptors (data URI/dimensions) |
| `ParamSpec` | `params.py` | `style_tree`/`apply_config` surface and its derived views |
| `StyleResult` | `_core.py` | Configured `FigTreeStyler` + source text + tree count/selected index + warnings |
| `TOOLS` | `tools/__init__.py` | Name → synchronous handler registry (21 entries) |
| `ToolError` | `_errors.py` | Stable code + `error_key` + details |
| `_threaded_tool` | `server.py` | Wraps a sync handler into an AnyIO worker coroutine and converts exceptions to envelopes |

## 3. Request lifecycle

```text
client call_tool(name, args)
  → FastMCP argument validation/coercion
  → async function wrapped by server._threaded_tool
  → anyio.to_thread.run_sync(handler, abandon_on_cancel=True)
  → worker acquires _concurrency.serialized() (global RLock)
  → handler:
       get_app(ctx)                  read AppContext
       require_run(ctx)              allocate run_<uuid8> on first use
       parameter validation          raise ToolError on failure
       resolve_tree_source           whitelist + size + anomaly scan
       make_styler / business logic  figtreekit calls
       run.register / export         artifact registration
       ok_envelope(...)              success envelope
  → exception → envelope_from_exception(...) → ok:false envelope
  → MCP result (usually isError=false)
```

Key points:

- **Why worker threads**: FastMCP executes synchronous handlers inline in the event loop. Parsing/rendering can take seconds to minutes and would block every request. `_threaded_tool` runs the handler in an AnyIO worker and uses `abandon_on_cancel=True` so client cancellation returns immediately.
- **Schema stability**: registration copies `inspect.signature(..., eval_str=True)` and the type hints from the original synchronous handler, so FastMCP's 21 input schemas match the handler signatures; the wrapper neither adds nor renames parameters.
- **Why `Bio.Phylo` is preloaded**: `figtreekit.load_content` lazily imports `Bio.Phylo` (and therefore numpy) on first use. On Windows, importing numpy inside a running asyncio loop can deadlock; `server.py` preloads it at module import so the first `summarize_tree` does not hang.
- **Single active context**: `_APP_HOLDER` stores a process-wide `AppContext` used by `get_active_app()` and resources. Multiple servers in one process are unsupported; concurrency only makes publishing the context atomic.
- **Test path**: tests call `TOOLS[name]` directly (passing `ctx` and tool arguments) and therefore see `ToolError`. E2E tests drive a real stdio subprocess and see `ok:false` envelopes.

## 4. Parameter model and the equivalence contract

### 4.1 Single source of truth

`params.ParamSpec` is the only definition of the `style_tree` parameter surface. It provides:

- `validate()`: enum, color, numeric bounds, `tree_index`/`seed`, `run_name` and `operations` sub-schema validation. Failures raise `ToolError("invalid_argument", ..., error_key="param_validation_failed")` with per-field `details`.
- `to_cli_args()`: argv in CLI execution order (appearance → layout → tree properties → labels → scale → polar/radial/rectilinear → legend → `--set` → operations → auto-color/collapse → taxonomy context → multi-tree/seed).
- `to_config_dict()`: FigTree block keys for `config_json` (angles converted to internal units).

The in-process path lives in `tools/style.py`:

- `apply_mcp_styling(styler, spec)`: applies the same order via `set_appearance`, `set_layout`, etc.;
- `apply_operations(styler, operations)`: executes ordered clade operations and returns per-op records;
- `_auto_color_and_collapse(...)`: implements the CLI semantics for `auto_color_rank`/`collapse_rank` (`collapse_rank` always performs a phylum color pass first);
- `split_operations(...)`: separates annotation ops from collapse ops to match CLI order.

`to_cli_args`, `to_config_dict` and `apply_mcp_styling` must be changed together. A new parameter needs entries in all three views plus the documentation.

### 4.2 What "equivalent" means

For `style_tree`/`apply_config`/`export_nexus`:

- the returned `cli_command` should regenerate a **byte-identical** `.nex` in the same environment;
- `config_json` should express the corresponding FigTree block settings;
- `operations_applied` should record what was applied or skipped.

The following combinations are **not** guaranteed byte-identical and are reported in `warnings`:

- `multi_tree=split/all`: the CLI writes one file per tree; the single MCP artifact preserves all trees but styles only the selected one;
- `multi_tree=random` without `seed`: a replay may select another tree;
- `tree_index` only: the CLI has no index-selection flag;
- mixing `color` and `color_all`: `--color-all` is global and applies to every `--color-clade`;
- `collapse_group` labels/non-default `collapse_type`: there is no exact `--clade` equivalent;
- render background/foreground/label post-processing: `render_tree`'s command reproduces layout/size/format only (`reproducible=false`).

**Evidence boundary**: the equivalence probe verifies six golden sets on the 700-tip showcase tree: MCP `.nex` matches the CLI byte-for-byte, and matches the Python API baseline semantically after normalizing tree names/indices. That verification covers neither GTDB data nor render's Python-side color post-processing; this project does not claim pixel-level equivalence for PNG/PDF/JPEG.

### 4.3 Command generation

`cli_command.build_figtreekit_command` produces:

```text
python -m figtreekit "<input>" -o "<output>" --force <args...>
```

- `python` is a literal, not `sys.executable`. It is a display command for humans; MCP never executes the string.
- Paths and hex colors are quoted with `shlex.quote`/a safe-character whitelist so `#RRGGBB` is not treated as a shell comment.
- `render_tree` emits `python -m figtreekit <input> -o <run_dir>/render.nex --force --render ... --figtree-jar ...`, which writes a companion `render.nex` next to the image; the string is display-only.

## 5. Adding a tool

1. **Choose a module and name** under `tools/`. Use a stable verb-first name matching the documentation.
2. **Implement the synchronous handler**:
   ```python
   @tool("my_tool")
   def my_tool(ctx: Context, tree_content: Optional[str] = None, ...) -> Dict[str, Any]:
       app = get_app(ctx)
       run = require_run(ctx)
       content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
       ...
       return ok_envelope(..., run_dir=run.name)
   ```
   - Use `get_app(ctx)`; do not rely on module globals.
   - Use `require_run(ctx)` for artifacts (one directory per call).
   - Raise `ToolError(code, message, error_key=...)` for parameter errors.
   - Return `ok_envelope(...)` on success.
   - Never `print` to stdout from a handler; use `_logging.get_logger()`.
3. **Register the module** by importing it in `server._register_tools` (side-effect registration). `@tool` rejects duplicate names.
4. **Update self-test**: add the name to `_cli.run_self_test`'s `expected` set and adjust the "exactly 21" assertion; update README/tests if the count changes.
5. **Update E2E**: add the name to `EXPECTED_TOOLS` and the count in `tests/test_server_smoke.py`.
6. **Add tests**:
   - unit: validation, error keys, boundaries;
   - tool-level: call the real handler through `conftest.call`;
   - security: new path/output/size attack surface;
   - equivalence: cover `to_cli_args`/`to_config_dict` in `test_params.py`.
7. **Update documentation**: README tool table and `docs/tools_reference_*`.

### 5.1 Errors and envelopes

- Stable envelope fields: `ok:false`, `code`, `error_key`, `error` (human-readable Chinese message), `error_detail` (technical detail), `details` (structured context) and `run_dir` (when available).
- `ToolError.code` must be in `ERROR_CODES` (or `cancelled`); otherwise it becomes `internal_error`.
- `error_key` defaults to `code`; provide one when a more specific reason is useful (e.g. `outside_roots`).
- `_errors.guard` can convert arbitrary exceptions to an envelope, but tool registration does **not** use it; `_threaded_tool` performs the conversion. Tests that call handlers directly should catch `ToolError`.
- Never write tracebacks to stdout; `internal_error` puts a stack summary in `stack_summary`.

### 5.2 Resources and prompts

- Resources are registered in `resources.py` with `@mcp.resource("figtreekit://...")` and return strings; JSON uses `json.dumps(..., ensure_ascii=False)`.
- Prompts are registered in `prompts.py` with `@mcp.prompt(name=...)`; use `Optional[str]` arguments and make sure every accepted argument is actually interpolated.
- Resource/prompt counts and names must match self-test, E2E and documentation (currently 3/2).

## 6. Security model

| Control | Implementation | Notes |
|---------|----------------|-------|
| Workspace | `Workspace.root` | The only writable root; created at startup |
| Read roots | `Workspace.read_roots` | Workspace + `--allow-read-root`; repeatable |
| Canonical paths | `assert_within_roots` | `Path.resolve()` follows symlinks; final target must be inside a root |
| `..` rejection | `_reject_parent_tokens` | Any `..` segment is rejected before resolution |
| Size limits | `check_content_size`/`check_file_size` | Defaults 10 MiB / 200 MiB |
| Anomalous content | `_scan_anomalous` | Control characters and Unicode bidi overrides |
| Output containment | `RunStorage.file_path`/`_rewrite_output_args` | Only basenames inside the run directory |
| Zero shell | `subprocess.run(..., shell=False)` | Argument arrays, no shell interpretation |
| Pass-through limits | `_validate_argv`/`_verify_inputs` | No interpreter, no `--figtree-jar`, input whitelist, output rewriting |
| Network | loopback + `--allow-remote-bind` | No built-in auth/TLS |
| stdout purity | static scan + stderr logging | SEC-12 |

See [`SECURITY.md`](../SECURITY.md) for the full policy. Changes to path/pass-through logic must update `tests/test_security.py` and `tests/test_workspace.py`/`test_workspace_hardening.py`.

## 7. Concurrency model

- Each request runs in an AnyIO worker thread, and `server._threaded_tool` acquires `_concurrency.serialized()` (a process-global `threading.RLock`) inside that worker. **Tool calls therefore run one at a time**, while the event loop stays responsive. This protects figtreekit's global rank-prefix/warning-filter state and Java/CLI child processes.
- Serialization reduces throughput but improves determinism. Direct handler calls in tests (which bypass `_threaded_tool`) do not acquire the lock automatically; concurrency tests must use `serialized()` explicitly.
- `abandon_on_cancel=True` makes client cancellation return immediately, but the worker may keep running until the handler returns and continues to hold the global lock. This is a limitation of the current cancellation semantics.
- Each call gets its own `run_<uuid8>` through `require_run`; `Workspace.new_run` uses UUIDs for isolation.
- `taxonomy_levels` is module-global state in figtreekit. `_core.temporary_rank_prefixes` snapshots and restores it around a call. `style_tree`/`apply_config` keep the context active for the whole load+analysis pipeline; `tests/test_taxonomy_concurrency.py` covers the isolation.
- During long sessions, every 16th new run (`require_run` triggers one `workspace.cleanup()`) and the shutdown `lifespan` delete old directories according to `keep_runs`; `--keep-runs 0` deletes all old ones.
- Only one active `AppContext` exists per process. Do not create multiple `create_server` instances in one process and expect isolation.

## 8. Error mapping

`_errors.EXCEPTION_TO_CODE` is ordered most-specific first:

| Exception | Code |
|-----------|------|
| `figtreekit.RenderError` | `render_failed` |
| `figtreekit.ExportError` | `export_failed` |
| `figtreekit.MonophylyError` | `monophyly_error` |
| `figtreekit.TaxonomyConflictError` | `taxonomy_conflict` |
| `figtreekit.PhyloFormatError` / `ParseError` | `tree_parse_error` |
| `figtreekit.ValidationError` | `validation_failed` |
| `FileNotFoundError` / `PermissionError` | `access_denied` |
| `ValueError` | `invalid_argument` |
| anything else | `internal_error` (with `stack_summary`) |

`ToolError` keeps its own `code`/`error_key`/`details`. `CompatibilityWarning` is mapped separately to `validation_failed/compatibility_warning`.

## 9. Style and conventions

- Every source file starts with `# SPDX-License-Identifier: GPL-2.0-or-later` and a copyright note.
- Use `from __future__ import annotations`, type hints and `dataclass`; public functions need docstrings.
- Four-space indentation; existing code generally stays around 100 columns. `pyproject.toml` provides ruff/mypy configuration and both come with `[dev]`, but they are **not** gating acceptance checks; do not claim ruff/mypy are fully clean, and do not assume they must be run.
- User-facing error messages are Chinese; `error_key`/`code` are stable English identifiers. Logs may mix languages but must go to stderr.
- Bare `print()` to stdout is forbidden (terminal output in `_cli.py`/`__main__.py` is exempt); `--self-test` scans for it.
- New dependencies must be added to `pyproject.toml` with a license note; avoid network-dependent core dependencies.

## 10. Development commands

Run from the repository root with the virtual environment active (or use the interpreter path):

```bash
# Install (including test/render extras)
python -m pip install -e ".[dev,render]"

# Full test suite
python -m pytest

# Unit/tool-level only (excluding slow equivalence and real stdio E2E)
python -m pytest --ignore=tests/test_equivalence.py --ignore=tests/test_server_smoke.py

# Slow tests only (equivalence probe/real rendering)
python -m pytest -m slow

# Coverage (80% target configured in pyproject.toml)
python -m pytest --cov=figtreekit_mcp --cov-report=term-missing

# Self-test
python -m figtreekit_mcp --self-test

# Collection count
python -m pytest --collect-only -q
```

- `pytest`/`pytest-asyncio`/`hypothesis`/`pytest-cov`/`pytest-timeout` are in the `[dev]` extra.
- `ruff` and `mypy` also come with `[dev]`, but their configuration is development aid only; they are not CI/acceptance gates.
- The full suite may skip cases when GTDB/showcase data is missing. A skip is neither a failure nor a pass; see the testing guide.

## 11. Packaging and release notes

- `pyproject.toml` sets `readme = "README_EN.md"`, so the built package metadata uses the **English** README as its long description. The Chinese README is not included automatically.
- Runtime dependencies: `figtreekit>=1.1.4,<2`, `mcp>=1.29,<2`; optional `render = pillow>=10.0`.
- Version source: `_version.VERSION = "0.1.0"`. `server.create_server` sets the underlying FastMCP server version to `0.1.0`; otherwise initialization may report the MCP SDK version.
- Before a release, run `--self-test` and pytest, and update the version and date in `CITATION.cff`.

## 12. Known limitations (developer view)

1. `--cli-timeout` is parsed but not wired into `run_figtreekit_cli`'s default; unify this when adding timeout logic.
2. Tool calls are serialized by a global RLock; throughput is limited, and a cancelled worker may continue to hold the lock until the handler returns.
3. Automated rendering coverage is PNG/SVG only; PDF/JPEG assertions are missing.
4. Prompt templates are bilingual; `tree_content` is represented as a source note rather than embedded verbatim. Add tests when changing templates.
5. `clear_annotations` intentionally does not clear colors/fonts.
6. `apply_config`'s `config_json` omits `auto_color_rank`/`collapse_rank` block keys; they are represented in the command line and `operations_applied`.
7. One active `AppContext`; multiple servers in one process are unsupported.
8. No network authentication/TLS; remote deployments must add their own controls.
9. Real-data tests are conditional; do not claim GTDB/showcase acceptance without the data.
