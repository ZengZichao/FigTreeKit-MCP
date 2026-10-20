# 开发指南

**简体中文** | [English](development_guide_EN.md)

适用版本：**0.1.0**。本指南面向修改 `src/figtreekit_mcp/`、增加工具、调整参数映射或排查行为的开发者。工具/参数的逐项说明见 [`tools_reference_CN.md`](tools_reference_CN.md)，测试命令与验收见 [`testing_and_acceptance_CN.md`](testing_and_acceptance_CN.md)。

## 1. 设计目标

1. **不重复实现树算法**：所有解析、Nexus 生成、分类学分析和 FigTree 渲染都调用 `figtreekit` 公共 API；MCP 只做参数适配、安全边界和结构化输出。
2. **可复现**：样式化/导出/渲染返回等效的 `cli_command` 与 `config_json`；无法精确复现的情况显式警告。
3. **无状态调用**：每次调用使用独立 `run_<uuid8>` 目录和局部对象；不依赖进程级可变状态（`taxonomy_levels` 的全局注入也做了快照/恢复）。
4. **安全默认**：路径白名单、软链接解析、零 shell、输出收敛、内容扫描、大小限额、默认回环绑定。
5. **协议纯净**：stdout 只承载 MCP 协议帧；所有日志写 stderr。

## 2. 目录与模块

```text
src/figtreekit_mcp/
├── __init__.py          包元数据、惰性导出 create_server/main
├── __main__.py          python -m figtreekit_mcp
├── _version.py          静态版本 0.1.0
├── _cli.py              启动参数、传输、信号、--self-test、退出码
├── server.py            FastMCP 组装、AppContext、工具注册、异步工作线程包装
├── resources.py         3 个资源
├── prompts.py           2 个 Prompt
├── _core.py             树源解析、styler 工厂、多树选择、taxonomy 注入、批量配色/折叠
├── _workspace.py        白名单、run 目录、产物注册、清理
├── _errors.py           错误码、ToolError、信封、异常映射、guard
├── _logging.py          stderr/文件日志、ISO 时间戳、stdout 禁令
├── _concurrency.py      全局 RLock；server._threaded_tool 在每次工具调用中获取
├── params.py            ParamSpec：校验、to_cli_args、to_config_dict
├── cli_command.py       可复现命令与 shell 引号
└── tools/
    ├── __init__.py      registry、get_app、require_run、公共助手
    ├── environment.py   T01–T03
    ├── validate.py      T04–T06
    ├── analyze.py       T07–T09
    ├── style.py         T10–T12 + apply_mcp_styling/apply_operations
    ├── clade.py         T13–T19
    ├── render.py        T20
    └── passthrough.py   T21
```

### 2.1 关键对象

| 对象 | 位置 | 职责 |
|------|------|------|
| `AppContext` | `server.py` | 工作区、只读根、版本、Java/JAR、限额、超时；`get_active_app()` 返回当前实例 |
| `Workspace` | `_workspace.py` | `assert_readable`/`assert_writable`、大小检查、`new_run`、`cleanup` |
| `RunStorage` | `_workspace.py` | 单个 run 目录、`file_path` 名称校验、`register` 产物描述符（含 data URI/尺寸） |
| `ParamSpec` | `params.py` | `style_tree`/`apply_config` 的参数面与三个派生视图 |
| `StyleResult` | `_core.py` | 配置好的 `FigTreeStyler` + 源文本 + 树数/选中索引 + 警告 |
| `TOOLS` | `tools/__init__.py` | 名称 → 同步 handler 的注册表（21 项） |
| `ToolError` | `_errors.py` | 稳定错误码 + `error_key` + 详情 |
| `_threaded_tool` | `server.py` | 把同步 handler 包装成 AnyIO 工作线程协程，并把异常转为信封 |

## 3. 请求生命周期

```text
客户端 call_tool(name, args)
  → FastMCP 参数校验/类型转换
  → server._threaded_tool 包装的异步函数
  → anyio.to_thread.run_sync(handler, abandon_on_cancel=True)
  → worker 获取 _concurrency.serialized()（全局 RLock）
  → handler:
       get_app(ctx)                  读取 AppContext
       require_run(ctx)              首次调用分配 run_<uuid8>
       参数校验（ToolError）         失败即抛出
       resolve_tree_source           白名单 + 大小 + 异常内容扫描
       make_styler / 业务处理        figtreekit 调用
       run.register / export         产物登记
       ok_envelope(...)              成功信封
  → 异常 → envelope_from_exception(...) → ok:false 信封
  → MCP 结果（通常 isError=false）
```

要点：

- **为什么用工作线程**：FastMCP 对同步 handler 会在事件循环内直接执行；渲染/解析可能持续数秒到数分钟，会阻塞所有请求。`_threaded_tool` 把 handler 放到 AnyIO 工作线程，并用 `abandon_on_cancel=True` 让客户端取消立即返回。
- **Schema 稳定性**：注册时从原始同步 handler 复制 `inspect.signature(..., eval_str=True)` 与类型提示，因此 FastMCP 生成的 21 个输入 schema 与 handler 签名一致；包装器不增加、不重命名参数。
- **为什么预加载 `Bio.Phylo`**：`figtreekit.load_content` 首次调用会惰性导入 `Bio.Phylo`（进而导入 numpy）。在 Windows 上，于运行中的 asyncio 事件循环内导入 numpy 可能死锁；`server.py` 在模块导入时预加载，避免首个 `summarize_tree` 卡住。
- **单活动上下文**：`_APP_HOLDER` 保存进程级 `AppContext`，`get_active_app()`/资源使用它。同一进程创建多个服务器不受支持；并发 `create_server` 只保证发布操作的原子性，不隔离上下文。
- **测试路径**：测试直接调用 `TOOLS[name]`（传入 `ctx` 与工具参数），因此看到的是 `ToolError` 异常；E2E 测试通过真实 stdio 子进程，看到的是 `ok:false` 信封。

## 4. 参数模型与等价性契约

### 4.1 单一事实来源

`params.ParamSpec` 是 `style_tree` 参数面的唯一定义。它提供：

- `validate()`：枚举、颜色、数值范围、`tree_index`/`seed`、`run_name`、`operations` 子结构校验；失败抛 `ToolError("invalid_argument", ..., error_key="param_validation_failed")`，`details` 逐字段。
- `to_cli_args()`：按 CLI 的执行顺序生成 argv（外观 → 布局 → 树属性 → 标签 → 比例尺 → 极坐标/放射/矩形 → 图例 → `--set` → 操作 → 自动配色/折叠 → 分类学上下文 → 多树/seed）。
- `to_config_dict()`：生成 FigTree block 键值（角度会换算为内部单位），供 `config_json` 使用。

进程内应用逻辑在 `tools/style.py`：

- `apply_mcp_styling(styler, spec)`：按与 `to_cli_args` 相同的顺序调用 `set_appearance`、`set_layout` 等；
- `apply_operations(styler, operations)`：执行有序 clade 操作，返回逐项记录；
- `_auto_color_and_collapse(...)`：实现 `auto_color_rank` 与 `collapse_rank` 的 CLI 语义（`collapse_rank` 总会先做门级配色）；
- `split_operations(...)`：把标注操作与折叠操作分开，保证 CLI 顺序。

`to_cli_args`、`to_config_dict`、`apply_mcp_styling` 三者必须同步修改；任何新增参数至少要在前三处以及文档中体现。

### 4.2 “等价”的含义

对 `style_tree`/`apply_config`/`export_nexus`：

- 返回的 `cli_command` 应能在同一环境中重新生成 **逐字节相同** 的 `.nex`；
- `config_json` 应能表达对应的 FigTree block 设置；
- `operations_applied` 应记录实际执行/跳过的操作。

但以下情况**不保证**逐字节等价，代码会返回 `warnings`：

- `multi_tree=split/all`：CLI 每棵树输出一个文件，MCP 单产物保留全部树但只样式化选中树；
- `multi_tree=random` 未提供 `seed`：重放会随机选另一棵树；
- 仅用 `tree_index` 选择：CLI 没有按索引选择的参数；
- 同时使用 `color` 与 `color_all`：`--color-all` 是全局开关，命令会把 `--color-all` 应用于所有 `--color-clade`；
- `collapse_group` 的 `label`/非默认 `collapse_type`：CLI 没有完全等价的 `--clade` 表达；
- 渲染的 background/foreground/label 后处理：`render_tree` 的 `cli_command` 只能复现布局/尺寸/格式，`reproducible=false`。

**证据边界**：等价性探针在 700 末端展示树上验证了 6 组黄金集合——MCP `.nex` 与 CLI 逐字节一致，归一化树名/索引后与 Python API 基准语义一致。该验证不覆盖 GTDB 数据，也不覆盖 render 的 Python 侧配色后处理；本项目不宣称 PNG/PDF/JPEG 的像素级等价。

### 4.3 命令生成

`cli_command.build_figtreekit_command` 生成：

```text
python -m figtreekit "<input>" -o "<output>" --force <args...>
```

- `python` 是字面量，不是 `sys.executable`；这是给用户重放的展示命令，MCP 不会执行该字符串。
- 路径和十六进制颜色通过 `shlex.quote`/安全字符白名单处理，`#RRGGBB` 会被引号包住，避免被 shell 当作注释。
- `render_tree` 的命令是 `python -m figtreekit <input> -o <run_dir>/render.nex --force --render ... --figtree-jar ...`，会在图像旁写一个伴随 `render.nex`；该字符串只读展示。

## 5. 新增一个工具

1. **选择模块与名称**：在 `tools/` 下已有模块或新模块中实现；工具名应稳定、动词开头、与文档一致。
2. **实现同步 handler**：
   ```python
   @tool("my_tool")
   def my_tool(ctx: Context, tree_content: Optional[str] = None, ...) -> Dict[str, Any]:
       app = get_app(ctx)
       run = require_run(ctx)
       content, node = resolve_tree_source(tree_content, tree_file, app.workspace)
       ...
       return ok_envelope(..., run_dir=run.name)
   ```
   - 用 `get_app(ctx)` 获取上下文，禁止依赖模块级全局状态；
   - 需要产物时用 `require_run(ctx)`（同一次调用复用同一目录）；
   - 参数错误抛 `ToolError(code, message, error_key=...)`；
   - 成功用 `ok_envelope(...)`；
   - 不要在 handler 中 `print` 到 stdout；日志用 `_logging.get_logger()`。
3. **注册模块**：在 `server._register_tools` 中 `import figtreekit_mcp.tools.<module>`（副作用注册）；`@tool` 会检查重名。
4. **更新自检**：`_cli.run_self_test` 的 `expected` 集合和“恰 21 个”断言需要同步；如果工具数变化，README/测试中的 21 也要更新。
5. **更新 E2E**：`tests/test_server_smoke.py` 的 `EXPECTED_TOOLS`/计数。
6. **添加测试**：
   - 单元：参数校验、错误键、边界；
   - 工具层：用 `conftest.call` 调用真实 handler；
   - 安全：新增路径/输出/大小写攻击面；
   - 若涉及等价性：在 `test_params.py` 覆盖 `to_cli_args`/`to_config_dict`。
7. **更新文档**：README 工具表与 `docs/tools_reference_*`。

### 5.1 错误与信封

- 错误信封的稳定字段：`ok:false`、`code`、`error_key`、`error`（中文可读消息）、`error_detail`（技术细节）、`details`（结构化上下文）与 `run_dir`（可用时）。
- `ToolError.code` 必须在 `ERROR_CODES`（或 `cancelled`）内，否则归一化为 `internal_error`。
- `error_key` 默认等于 `code`；需要区分具体原因时显式给出（如 `outside_roots`）。
- `_errors.guard` 装饰器可以把任意异常转成信封，但**当前工具注册没有使用它**；注册层 `_threaded_tool` 负责转换。直接调用 handler 的测试代码应捕获 `ToolError`。
- 不要把 traceback 写到 stdout；`internal_error` 的堆栈摘要放在 `stack_summary` 字段。

### 5.2 资源与 Prompt

- 资源在 `resources.py` 用 `@mcp.resource("figtreekit://...")` 注册，返回字符串；JSON 用 `json.dumps(..., ensure_ascii=False)`。
- Prompt 在 `prompts.py` 用 `@mcp.prompt(name=...)` 注册，参数类型建议 `Optional[str]`；模板插值参数必须实际出现在正文中，避免“接收但忽略”。
- 资源/Prompt 的数量和名称要与自检、E2E 和文档一致（当前 3/2）。

## 6. 安全模型

| 控制 | 实现 | 说明 |
|------|------|------|
| 工作区 | `Workspace.root` | 唯一的可写根；启动时创建 |
| 只读根 | `Workspace.read_roots` | 工作区 + `--allow-read-root`；可重复 |
| 路径规范化 | `assert_within_roots` | `Path.resolve()` 跟随软链接；最终必须位于根内 |
| `..` 拒绝 | `_reject_parent_tokens` | 解析前拒绝任何 `..` 段 |
| 大小限额 | `check_content_size`/`check_file_size` | 默认 10 MiB / 200 MiB |
| 异常内容 | `_scan_anomalous` | 控制字符、Unicode 双向覆盖字符 |
| 输出收敛 | `RunStorage.file_path`/`_rewrite_output_args` | 只允许运行目录内的纯文件名 |
| 零 shell | `subprocess.run(..., shell=False)` | 参数数组，不做 shell 解释 |
| 透传限制 | `_validate_argv`/`_verify_inputs` | 禁解释器、禁 `--figtree-jar`、输入白名单、输出改写 |
| 网络 | 默认回环 + `--allow-remote-bind` | 无内置认证/TLS |
| stdout 纯净 | 静态扫描 + 日志写 stderr | SEC-12 |

详细策略与报告方式见 [`SECURITY_CN.md`](../SECURITY_CN.md)。修改路径/透传逻辑时，必须同步更新 `tests/test_security.py` 和 `tests/test_workspace.py`/`test_workspace_hardening.py`。

## 7. 并发模型

- 每个请求在 AnyIO 工作线程中执行；`server._threaded_tool` 在 worker 内获取 `_concurrency.serialized()`（进程级 `threading.RLock`）。因此工具调用**一次只运行一个**，事件循环仍保持可响应。这样保护了 figtreekit 的全局 taxon 前缀/警告过滤器和 Java/CLI 子进程。
- 串行化降低吞吐但保证确定性；测试中的直接 handler 调用（不经过 `_threaded_tool`）不会自动获取该锁，因此并发测试需要显式使用 `serialized()`。
- `abandon_on_cancel=True` 让客户端取消立即返回，但工作线程可能继续运行到 handler 结束，并在此期间继续持有全局锁；这是当前取消语义的限制。
- 每次调用通过 `require_run` 分配独立 `run_<uuid8>`；`Workspace.new_run` 使用 UUID，天然隔离。
- `taxonomy_levels` 是 figtreekit 的模块级全局状态；`_core.temporary_rank_prefixes` 在调用前后快照/恢复，避免并发串扰。`style_tree`/`apply_config` 把整个加载+分析包在该上下文内；`tests/test_taxonomy_concurrency.py` 覆盖该隔离。
- 服务器在长期会话中每 16 次新 run（由 `require_run` 触发一次 `workspace.cleanup()`）以及关闭时的 `lifespan` 中，按 `keep_runs` 删除旧目录；`--keep-runs 0` 删除全部旧目录。
- 进程级只有一个活动 `AppContext`；不要在同一进程创建多个 `create_server` 并期望隔离。

## 8. 错误映射

`_errors.EXCEPTION_TO_CODE` 按“最具体优先”映射：

| 异常 | 错误码 |
|------|--------|
| `figtreekit.RenderError` | `render_failed` |
| `figtreekit.ExportError` | `export_failed` |
| `figtreekit.MonophylyError` | `monophyly_error` |
| `figtreekit.TaxonomyConflictError` | `taxonomy_conflict` |
| `figtreekit.PhyloFormatError` / `ParseError` | `tree_parse_error` |
| `figtreekit.ValidationError` | `validation_failed` |
| `FileNotFoundError` / `PermissionError` | `access_denied` |
| `ValueError` | `invalid_argument` |
| 其他 | `internal_error`（附 `stack_summary`） |

`ToolError` 自身保留 `code`/`error_key`/`details`。`CompatibilityWarning` 单独映射为 `validation_failed/compatibility_warning`。

## 9. 代码风格与约定

- 每个源文件首部有 `# SPDX-License-Identifier: GPL-2.0-or-later` 和版权说明。
- 使用 `from __future__ import annotations`、类型标注、`dataclass`；公共函数写 docstring。
- 4 空格缩进；现有代码大致控制在 100 列左右。`pyproject.toml` 提供 ruff/mypy 配置，它们也随 `[dev]` 安装，但不是验收门禁，可按需运行。
- 用户可见错误消息用中文，`error_key`/`code` 用英文稳定标识；日志可中英混合，但必须写 stderr。
- 禁止裸 `print()` 写 stdout（`_cli.py`/`__main__.py` 的终端输出除外）；`--self-test` 的静态扫描会检查。
- 新依赖必须加入 `pyproject.toml` 并说明许可证；不要引入需要联网运行的核心依赖。

## 10. 开发命令

以下命令在项目根目录、已激活虚拟环境（或使用解释器绝对路径）下运行：

```bash
# 安装（含测试/渲染依赖）
python -m pip install -e ".[dev,render]"

# 运行全部测试
python -m pytest

# 只跑单元/工具层（排除慢速等价性和真实 stdio E2E）
python -m pytest --ignore=tests/test_equivalence.py --ignore=tests/test_server_smoke.py

# 只跑慢速测试（等价性探针/真实渲染）
python -m pytest -m slow

# 覆盖率（目标 80%，配置在 pyproject.toml）
python -m pytest --cov=figtreekit_mcp --cov-report=term-missing

# 自检
python -m figtreekit_mcp --self-test

# 查看测试收集数量
python -m pytest --collect-only -q
```

- `pytest`/`pytest-asyncio`/`hypothesis`/`pytest-cov`/`pytest-timeout` 在 `[dev]` extra 中。
- `ruff` 与 `mypy` 也随 `[dev]` 安装，但配置只用于开发辅助，不是 CI/验收门禁。
- 完整测试可能因缺少 GTDB/展示数据而跳过部分用例；跳过不是失败，也不是通过。详见测试指南。

## 11. 打包与发布注意事项

- `pyproject.toml` 的 `readme = "README_EN.md"`：构建元数据的长描述是**英文** README；中文 README 不会自动进入 PyPI 描述。
- 运行时依赖：`figtreekit>=1.1.4,<2`、`mcp>=1.29,<2`；可选 `render = pillow>=10.0`。
- 版本源：`_version.VERSION = "0.1.0"`；`server.create_server` 会把 FastMCP 底层 server 的版本显式设为 `0.1.0`，否则初始化可能报告 MCP SDK 版本。
- 发布前运行 `--self-test` 与 pytest，并更新 `CITATION.cff` 的版本与日期。

## 12. 已知限制（开发视角）

1. `--cli-timeout` 已解析但未接入 `run_figtreekit_cli` 的默认值；新增超时逻辑时请统一。
2. 工具调用由全局 RLock 串行化；吞吐受限，且取消后的 worker 可能继续持有锁直到 handler 返回。
3. 渲染只对 PNG/SVG 有自动化覆盖；PDF/JPEG 需要补充断言。
4. Prompt 模板为中英双语；`tree_content` 只以来源说明体现，不嵌入原文；修改模板时请补测试。
5. `clear_annotations` 不清理颜色/字体；这是有意行为，不要“顺手”扩展。
6. `apply_config` 的 `config_json` 不包含 `auto_color_rank`/`collapse_rank` 的 block 键；它们通过命令行和 `operations_applied` 表达。
7. 单一活动 `AppContext`；不支持同进程多服务器。
8. 无网络认证/TLS；远程部署必须自行加固。
9. 真实数据测试是条件性的；不要在没有数据时宣称 GTDB/展示数据验收通过。
