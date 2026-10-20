# FigTreeKit-MCP 工具参考

**简体中文** | [English](tools_reference_EN.md)

适用版本：**0.1.0**。本文件以 `src/figtreekit_mcp/tools/*.py` 的实际函数签名、`params.py` 的 `ParamSpec` 和 `_cli.py` 的启动参数为准。参数默认值中 `null`/`None` 表示“未指定时使用 figtreekit 默认值”，不是空字符串。

## 1. 总览与阅读约定

### 1.1 组件、传输与运行模型

FigTreeKit-MCP v0.1.0 是一个 Python 3.11 MCP 服务器，把 FigTreeKit 的系统发育树流程暴露给 AI 客户端：

- **21 个工具（T01–T21）**：环境（T01–T03）、验证（T04–T06）、分类学分析（T07–T09）、样式化与导出（T10–T12）、类群操作（T13–T19）、渲染（T20）、CLI 透传（T21）。
- **3 个资源**：`figtreekit://version`、`figtreekit://help`、`figtreekit://defaults`（见 §10）。
- **2 个 Prompt**：`create-publication-figure`、`taxonomy-audit`（见 §11）。
- **3 种传输**：`--transport stdio`（默认）、`sse`、`http`。`http` 在 `_cli.py` 中的取值就是 `http`，实际以 MCP 的 **Streamable HTTP**（`streamable-http`）传输运行。

**工作区与读取根**：唯一的可写根由 `--workspace-root` 指定（默认 `<cwd>/figtreekit-mcp-workspace`），所有产物只写入该根；`--allow-read-root DIR` 可重复，追加额外的只读输入根。工作区根始终在可读根列表中。工具参数中的文件路径经 `Path.resolve()`（跟随软链接）后必须落在某个根内，否则返回 `access_denied`；相对路径以工作区根为基准（`run_figtreekit_cli` 的位置参数按本次运行目录解析），含 `..` 的路径直接拒绝。

**每次调用的产物目录**：需要落盘的工具在首次调用时分配 `run_<uuid8>` 目录（8 位十六进制），运行目录内的产物文件名可由 `run_name` 指定，返回描述符包含 `relative`/`absolute`/`size_bytes`。`--keep-runs` 控制保留数量，清理在分配新运行目录时（每 16 次）以及服务器关闭时进行。

**错误信封**：所有工具共用同一形状：成功为 `{"ok": true, ...}`；失败为 `{"ok": false, "code", "error_key", "error", "error_detail", "details", "run_dir"}`。MCP 注册层会把异常转换成普通工具结果返回，因此客户端的 `isError` 不一定为 `true`，应以 `ok`/`code`/`error_key` 为准。

**串行执行**：工具调用在服务端由单把可重入锁串行化。原因是 figtreekit 把分类学等级前缀与警告过滤器保存在**进程级全局状态**中，Java/CLI 子进程也不适合并发；并发请求会排队执行，异步包装器仍在工作线程中运行，事件循环保持响应。

### 1.2 树源：`tree_content` 与 `tree_file`

所有接受树输入的工具都遵循同一规则：

- `tree_content`：直接传入 Newick/Nexus/FASTA/FASTQ 文本；
- `tree_file`：传入白名单根目录内的文件路径（相对路径以工作区根为基准）；
- 二者**互斥**且必须提供其一，否则返回 `invalid_argument`，`error_key` 为 `mutually_exclusive_source` 或 `missing_tree_source`；
- 内容会先做大小检查和异常内容扫描（NUL、控制字符、Unicode 双向覆盖字符），再解析。

`validate_tree`/`summarize_tree` 等工具会在 `run_<uuid8>` 中分配运行目录；即使校验没有生成长期产物，返回中仍可能带 `run_dir`。

### 1.3 返回值与错误

成功时返回 JSON 对象，至少包含 `"ok": true`；失败时返回统一的错误信封：

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

- 工具处理器直接调用时通常**抛出** `ToolError`；通过 MCP 注册层（`server.py` 的异步包装）调用时，异常会转换成上述 `ok:false` 信封并作为普通工具结果返回。因此客户端的 `isError` 可能为 `false`，应以 `ok`、`code`、`error_key` 为准。
- `error` 是中文可读消息；`error_key` 是稳定标识；`error_detail` 可能包含绝对路径等技术信息；`details` 是 `{level, message}` 列表。
- 每个工具条目下列出该工具特有的 `error_key`；通用的路径、大小、参数错误也可能出现在任何工具中。

### 1.4 产物描述符

样式/导出/渲染/透传工具返回的产物通常具有：

```json
{
  "relative": "run_ab12cd34/output.nex",
  "absolute": "<workspace-root>/run_ab12cd34/output.nex",
  "size_bytes": 12345,
  "data_uri": null,
  "mime": null
}
```

- `relative` 相对于工作区根， Windows 上使用反斜杠；
- `RunStorage.register` 的原始条目在图像（`.png`/`.jpg`/`.jpeg`/`.svg`/`.pdf`）且 ≤ **512 KiB** 时附带 base64 `data_uri`，否则为 `null`；
- `nexus_file` 经 `nexus_artifact` 归一化后**只保留** `relative`/`absolute`/`size_bytes`，不含 `data_uri`；
- `render_tree` 的 `image` 与 `run_figtreekit_cli` 的 `artifacts` 是原始注册条目，可能含 `data_uri`/`mime`；PNG/JPEG 在 Pillow 可用时还可能有 `width`/`height`；
- `run_name` 只影响产物文件名，不会创建子目录；默认 `output`。

### 1.5 错误码

稳定错误码共 19 个（`_errors.ERROR_CODES`）：

| 错误码 | 典型触发条件 |
|--------|--------------|
| `invalid_argument` | 参数类型/枚举/范围不合法、缺少必填参数、互斥参数同时提供 |
| `input_too_large` | `tree_content` 或文件超过限额 |
| `access_denied` | 路径越界、软链接逃逸、`..`、父目录不存在、文件不可读 |
| `anomalous_content` | 输入含控制字符或 Unicode 双向覆盖字符 |
| `tree_parse_error` | Newick/Nexus/序列解析失败、无法提取末端标签 |
| `validation_failed` | 深度校验发现 ERROR/CRITICAL、交叉验证失配 |
| `taxonomy_conflict` | 分类学数据冲突（由 figtreekit 异常映射） |
| `monophyly_error` | 非单系类群、类群无法解析、strict 折叠失败 |
| `export_failed` | Nexus 导出失败 |
| `java_missing` | 渲染需要 Java，但 `java` 不可用 |
| `jar_missing` | `figtree_patched.jar` 缺失或不可读 |
| `figtree_setup_failed` | JAR 下载/编译失败或超时 |
| `render_bad_format` | 渲染格式不是 PNG/PDF/SVG/JPEG |
| `render_timeout` | JVM 渲染超时 |
| `render_failed` | FigTree 渲染失败 |
| `cli_failed` | 透传命令返回非零退出码 |
| `cli_timeout` | 透传命令超时 |
| `cancelled` | 客户端取消（错误信封允许该值） |
| `internal_error` | 未映射的异常（附 `stack_summary`，不写 stdout） |

通用 `error_key` 包括：`param_validation_failed`（`style_tree`/`apply_config` 参数校验）、`path_traversal`、`outside_roots`、`content_too_large`、`file_too_large`、`anomalous_content_found`、`multi_tree_required`、`multi_tree_ask`、`tree_index_out_of_range` 等。

## 2. 工具总表（T01–T21）

| 编号 | 工具 | 模块 | 一句话 |
|------|------|------|--------|
| T01 | `get_environment` | environment | 运行时快照 |
| T02 | `check_figtree` | environment | Java/JAR 检查 |
| T03 | `setup_figtree` | environment | 检查、复用或安装 JAR |
| T04 | `validate_tree` | validate | 深度校验 |
| T05 | `summarize_tree` | validate | 树摘要 |
| T06 | `cross_validate` | validate | 树↔序列交叉验证 |
| T07 | `check_monophyly` | analyze | 单系性检查 |
| T08 | `analyze_taxonomy` | analyze | 按等级批量分析 |
| T09 | `taxonomy_completeness` | analyze | 分类完整性 |
| T10 | `style_tree` | style | 核心样式化 + 导出 |
| T11 | `apply_config` | style | 应用 figtree-block 配置 |
| T12 | `export_nexus` | style | 结构转换 |
| T13 | `highlight_clade` | clade | 高亮 |
| T14 | `color_clade` | clade | 着色 |
| T15 | `set_clade_font` | clade | 字体 |
| T16 | `collapse_clade` | clade | 按末端名折叠 |
| T17 | `collapse_group` | clade | 按类群名折叠 |
| T18 | `collapse_rank` | clade | 按等级折叠 |
| T19 | `clear_annotations` | clade | 清除高亮/折叠 |
| T20 | `render_tree` | render | 渲染图像 |
| T21 | `run_figtreekit_cli` | passthrough | CLI 透传 |

所有工具的第一个参数都是 MCP 注入的 `ctx: Context`，不在下表中重复。

## 3. 环境工具（T01–T03）

### T01 `get_environment`

无参数。

返回键：`ok`、`figtreekit_version`、`biopython_version`、`python_version`、`mcp_sdk_version`、`pillow`（`{ok, version}`；未安装时 `ok:false`、`version:null`）、`java`（`{ok, version, message, hints}`）、`jar`（`{ok, path, hints}`）、`workspace_root`、`allowed_read_roots`、`render_ready`。

说明：`allowed_read_roots` 包含工作区根和所有 `--allow-read-root`；该工具不会因 Java/JAR 缺失而失败。

### T02 `check_figtree`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `jar_path` | string | `null` | 显式检查的 JAR；省略时使用服务端 `--jar` 或自动探测 |

返回键：`ok`、`java_ok`、`java_version`（如 `17.x`）、`jar_ok`、`jar_path`、`render_ready`、`hints`。

错误：Java 缺失 → `code=java_missing`；Java 在但 JAR 缺失 → `code=jar_missing`；两者的 `error_key` 都是 `render_deps_missing`，`details` 含提示。

### T03 `setup_figtree`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `jar_path` | string | `null` | 已有 JAR 时直接登记（必须在白名单内且是文件） |
| `check_only` | bool | `false` | 只检查，不下载/编译；不因缺失抛错 |
| `verbose` | bool | `false` | 让 figtreekit 安装过程输出更详细状态 |

行为：

1. `check_only=true`：返回与检查结果等价的 `ok` 信封，包含 `java_ok`、`java_version`、`jar_ok`、`jar_path`、`render_ready`、`hints`、`status`；
2. 提供 `jar_path`：校验路径并登记，返回 `jar_path`、`status`；文件不存在 → `invalid_argument/jar_not_a_file`；
3. 自动探测到已可用 JAR：直接返回；
4. 否则调用 figtreekit 的安装流程（下载/编译），超时由 `--setup-timeout` 控制（默认 600 秒）；失败 → `figtree_setup_failed`，`error_key` 可能为 `setup_timeout`、`setup_failed` 或 `setup_no_jar`。

该工具不暴露 `install_dir`，安装位置由 figtreekit 决定。

## 4. 验证工具（T04–T06）

### T04 `validate_tree`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` | string | `null` | Newick/Nexus/FASTA/FASTQ 文本 |
| `tree_file` | string | `null` | 白名单内的树/序列文件 |
| `mol_type` | string | `null` | `DNA`/`RNA`/`protein`；仅序列输入使用 |
| `skip_length_check` | bool | `false` | FASTA 跳过等长检查 |

返回（树）：`ok`、`valid`、`warnings`、`errors`、`size_bytes`、`run_dir`、`format`（`newick`/`nexus`）、`leaf_count`、`node_count`、`tree_count`。

返回（FASTA）：`format:"fasta"`、`sequence_count`、`alphabet`、`duplicate_ids`、`length_mismatch` 等；FASTQ 返回 `sequence_count`、`alphabet`、`duplicate_ids`。

错误：`mol_type` 非法 → `bad_mol_type`；格式不在支持范围 → `unsupported_format`；存在 ERROR/CRITICAL → `validation_failed`，`error_key=validation_errors`，`details` 逐条列出；文件读取失败 → `tree_parse_error/read_failed`。

说明：Nexus/FASTA/FASTQ 的临时文件写在本次 `run_dir`，返回前删除；不会留下校验产物。`taxonomy_levels` **不是**该工具的参数。

### T05 `summarize_tree`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` | string | `null` | 树文本 |
| `tree_file` | string | `null` | 白名单内文件 |
| `include_tip_labels` | bool | `true` | 是否包含末端标签预览 |
| `tip_labels_limit` | int | `100` | 预览上限，必须 1..10000 |
| `multi_tree` | string | `null` | `first`/`last`/`random`/`split`/`all`/`ask` |
| `tree_index` | int | `null` | 0 基树索引 |

返回：`ok`、`format`、`tree_count`、`selected_tree`、`statistics`（`tips`、`internal_nodes`、`rooted`、`branch_lengths`：`min`/`max`/`has_missing`/`negative`）、`tip_labels_total`、`tip_labels_preview`、`translate_block`（`used`/`entries`）、`warnings`；多树时可能额外有 `multi_tree_hint`。

说明：该工具**不因校验问题失败**；多树文件未指定选择时默认处理第一棵并给出 `multi_tree_hint`，而不是报错。`tip_labels_limit` 非法 → `bad_tip_labels_limit`。

### T06 `cross_validate`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` | string | `null` | 树文本 |
| `tree_file` | string | `null` | 白名单内树文件 |
| `sequences_file` | string | `null` | **必填**，白名单内 FASTA/FASTQ |
| `strict` | bool | `true` | 有失配即失败 |
| `low_memory` | bool | `false` | 为 CLI 兼容保留；当前实现总是惰性读取 ID |

返回：`ok`、`valid`、`matched`、`tree_only`、`seq_only`、`errors`、`warnings`、`sequences_count`。

错误：缺少 `sequences_file` → `missing_sequences_file`；无法提取树末端 → `tree_parse_error/no_tip_labels`；序列读取失败 → `tree_parse_error/seq_read_failed`；`strict=true` 且失配 → `validation_failed/cross_validation_failed`。树始终使用第一棵树。

## 5. 分析工具（T07–T09）

### T07 `check_monophyly`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` / `tree_file` | string | `null` | 树源（互斥） |
| `groups` | array | `null` | **必填**；元素为类群名字符串，或精确末端标签名单 `list[str]`，两者可混用 |
| `taxonomy_levels` | string | `null` | `prefix:rank,...`，如 `d:domain,p:phylum` |
| `strict` | bool | `false` | 任一类群非单系即失败 |

返回：`ok`、`results`（数组）、`notes`。每个结果含 `group`、`is_monophyletic`、`resolved_taxa_count`、`resolved_taxa_preview`（最多 10 个）、`special_identifier`、`warnings`、`mrca_terminals`、`note`。

`groups` 的两种元素语义：

- **类群名（字符串）**：调用 `check_monophyly_by_group`。若该解析器因标签方言（典型是带 superphylum 段的 GTDB 标签）抛 `ValidationError`，服务端会**回退到 taxonomy 分析**：依次按 `domain`…`species` 运行 `analyze_taxonomy`，用去掉首尾下划线后的类群名匹配 `monophyletic`/`non_monophyletic` 的键，再把解析出的末端名单交给 `check_monophyly`。回退成功时结果 `note` 为“通过 taxonomy 分析回退解析类群成员”。两条路径都失败时返回 `monophyly_error/group_not_found`；名单校验本身失败返回 `taxa_check_failed`。
- **精确末端标签名单（`list[str]`）**：必须是**非空**字符串列表，直接作为末端集合交给 `check_monophyly`，不经过 taxonomy 解析；`group` 字段显示为逗号连接的名字（≤10 个）或 `N taxa`。若有末端不在树中，`mrca_terminals` 可能为空并产生“MRCA 未找到”警告。

特殊标识 `LUCA`、`LACA`、`LBCA`、`root` 由 figtreekit 直接解析（`LUCA` 为全部末端，`LACA`/`LBCA` 为对应域的全部末端），结果中 `special_identifier=true` 并在 `note` 说明解析范围。`strict=true` 且有非单系类群 → `monophyly_error/non_monophyletic_groups`。该工具只处理第一棵树。

错误：缺少 `groups` → `missing_groups`；名单为空或含非字符串 → `bad_group_taxa`；元素既不是字符串也不是字符串列表 → `bad_group_entry`；类群解析失败 → `group_not_found`；`check_monophyly` 拒绝名单 → `taxa_check_failed`。

### T08 `analyze_taxonomy`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` / `tree_file` | string | `null` | 树源 |
| `rank` | string | **必填** | `domain`/`superphylum`/`phylum`/`class`/`order`/`family`/`genus`/`species` |
| `taxonomy_mapping_file` | string | `null` | 白名单内 CSV/TSV 映射表 |
| `taxonomy_levels` | string | `null` | 自定义等级前缀 |
| `group_size_min` | int | `1` | 只报告至少含这么多末端的类群；必须 ≥1 |

返回：`ok`、`rank`、`summary`（`total_labels`、`mapped_labels`、`unmapped_labels`、`total_groups`、`single_taxon_groups`、`monophyletic`、`non_monophyletic`、`monophyly_rate` 保留 1 位小数）、`monophyletic`/`non_monophyletic`（每项 `{group, taxa_count}`，按 taxa_count 降序）、`unmapped`（最多 200 个）、`unmapped_total`、`warnings`、`run_dir`。

错误：缺少 rank → `missing_rank`；rank 非法 → `bad_rank`；`group_size_min` 非法 → `bad_group_size_min`。

### T09 `taxonomy_completeness`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` / `tree_file` | string | `null` | 树源 |
| `taxonomy_mapping_file` | string | `null` | 白名单内映射表 |
| `taxonomy_levels` | string | `null` | 自定义等级前缀 |

返回：`ok`、`coverage`（0–100，保留 2 位）、`complete`/`incomplete`/`missing`（各截断至 200 个）、对应的 `*_total`、`rank_coverage`（每个 rank 的覆盖率）。该工具不分配 `run_dir`。

## 6. 样式与导出工具（T10–T12）

### T10 `style_tree`（核心）

**参数面**（全部可选；`null` 表示不覆盖 figtreekit 默认值）：

| 分组 | 参数 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| 树源/分类学 | `tree_content` | string | `null` | 树文本（与 `tree_file` 互斥） |
| | `tree_file` | string | `null` | 白名单内文件 |
| | `taxonomy_levels` | string | `null` | `prefix:rank,...`；在整个加载+分析期间生效 |
| | `taxonomy_mapping_file` | string | `null` | 白名单内映射表 |
| | `table_sep` | string | `null` | 映射表单字符分隔符 |
| | `taxonomy_delimiter_mode` | string | `null` | `reverse`/`greedy`/`segment` |
| 布局 | `layout` | string | `null` | `rectilinear`/`polar`/`radial` |
| | `expansion` | int | `null` | 展开程度，必须 ≥0 |
| | `zoom` | number | `null` | 必须 >0 |
| 树属性 | `rooted` | bool | `null` | 设为有根 |
| | `unrooted` | bool | `null` | 设为无根；与 `rooted` 同时给出时 `unrooted` 优先 |
| | `rooting_type` | string | `null` | `user`/`midpoint` |
| | `transform` | string | `null` | `cladogram`/`phylogram` |
| | `order` | string | `null` | `increasing`/`decreasing` |
| 外观 | `background_color` | string | `null` | `#RRGGBB` |
| | `foreground_color` | string | `null` | `#RRGGBB` |
| | `selection_color` | string | `null` | `#RRGGBB` |
| | `branch_width` | number | `null` | 必须 >0 |
| | `branch_color_attribute` | string | `null` | 分支颜色属性名 |
| 末端标签 | `tip_labels` | string | `null` | `show`/`hide` |
| | `tip_label_font_name` | string | `null` | 字体名 |
| | `tip_label_font_size` | int | `null` | 必须 >0 |
| | `tip_label_font_style` | int | `null` | 0 plain / 1 bold / 2 italic / 3 bold-italic |
| | `label_color` | string | `null` | `#RRGGBB` |
| | `align_tip_labels` | bool | `null` | 是否对齐末端标签 |
| 节点/分支标签 | `node_labels` | string | `null` | `show`/`hide` |
| | `node_display_attribute` | string | `null` | 节点标签显示属性；提供时自动显示节点标签 |
| | `branch_labels` | string | `null` | `show`/`hide` |
| | `branch_display_attribute` | string | `null` | 分支标签显示属性；提供时自动显示分支标签 |
| 比例尺/坐标轴 | `scale_bar` | string | `null` | `show`/`hide` |
| | `scale_axis` | string | `null` | `show`/`hide` |
| | `scale_axis_reverse` | bool | `null` | 反向坐标轴 |
| | `scale_axis_font_size` | int | `null` | 必须 >0 |
| | `scale_axis_significant_digits` | int | `null` | 必须 >0 |
| | `root_age` | number | `null` | 必须 ≥0 |
| | `scale_factor` | number | `null` | 必须 >0 |
| 极坐标 | `polar_angular_range_degrees` | number | `null` | [0, 360] |
| | `polar_root_angle_degrees` | number | `null` | [0, 360] |
| 放射/矩形 | `radial_spread` | number | `null` | ≥0 |
| | `curvature` | int | `null` | ≥0 |
| | `root_length` | int | `null` | ≥0 |
| 图例 | `legend` | string | `null` | `show`/`hide` |
| | `legend_position` | string | `null` | `top`/`bottom`/`left`/`right` |
| 分类驱动 | `auto_color_rank` | string | `null` | 自动按等级配色 |
| | `collapse_rank` | string | `null` | 按等级折叠；设置时**总会**先做一次门级配色 |
| | `collapse_style` | string | `"collapse"` | `collapse`/`cartoon` |
| 操作/高级 | `operations` | array | `null` | 有序 clade 操作，见 §6.1 |
| | `additional_config` | object | `null` | figtree block 键值对，经 `--set` 等价渲染 |
| 多树/产物 | `multi_tree` | string | `null` | `first`/`last`/`random`/`split`/`all`/`ask` |
| | `tree_index` | int | `null` | 0 基；必须是整数、≥0 |
| | `seed` | int | `null` | `multi_tree=random` 的随机种子 |
| | `run_name` | string | `null` | 产物基名，仅字母/数字/`_`/`-`，1–64 字符 |

**返回**：`ok`、`nexus_file`（产物描述符）、`cli_command`、`config_json`（字符串）、`operations_applied`（数组）、`summary`（`tips`、`internal_nodes`、`rooted`、`layout`、`tree_count`、`format`）、`run_dir`；当存在无法由 CLI 完全复现的参数组合时额外返回 `warnings`（字符串数组）。

**错误**：参数校验失败 → `invalid_argument`，`error_key=param_validation_failed`，`details` 逐字段说明；多树未指定 → `multi_tree_required`；`multi_tree=ask` → `multi_tree_ask`；索引越界 → `tree_index_out_of_range`；树源互斥/缺失 → `mutually_exclusive_source`/`missing_tree_source`；分类学冲突 → `taxonomy_conflict`；`taxonomy_levels` 格式错误 → `bad_taxonomy_spec`；`taxonomy_delimiter_mode` 非法 → `bad_delimiter_mode`；映射文件越界/超限 → `access_denied`/`input_too_large`。

**执行顺序**：

1. 加载树并应用基础样式（外观 → 布局 → 树属性 → 标签 → 比例尺 → 极坐标/放射/矩形 → 图例 → `additional_config`）；
2. 普通标注操作（`highlight`/`color`/`color_all`/`font`/`clear_hilights`）；
3. `auto_color_rank` 配色；
4. `collapse_rank`（若设置，总是先做门级配色，再按目标等级折叠）；
5. 折叠类操作（`collapse`/`collapse_group`/`collapse_rank`）；
6. 导出 Nexus，写入 `input.tre` 和产物，生成 `cli_command`/`config_json`。

**多树语义**：

- `first`/`last`/`random`：只样式化并导出选中的一棵（`single_tree=True`）；`random` 建议配合 `seed`；
- `split`/`all`：保留全部树，只对选中树应用样式，返回 `warnings` 提示 CLI 会为每棵树分别输出文件，二者布局不同；
- `tree_index` 没有对应 CLI 参数；与 `multi_tree` 同时使用时的重放命令可能无法按索引复现，会返回 `warnings`。

#### 6.1 `operations` 子结构

| `op` | 必填字段 | 可选字段与默认值 | 说明 |
|------|----------|------------------|------|
| `highlight` | `taxa: list[str]` | `color`（默认 `#804548`）、`width`（默认 4，>0）、`offset`（默认 0，必须是整数） | 背景高亮带 |
| `color` | `taxa: list[str]` | `color`（默认 `#999999`） | 只给 MRCA 分支着色 |
| `color_all` | `taxa: list[str]` | `color`（默认 `#999999`） | 给全部后代分支着色；CLI 的 `--color-all` 是全局开关 |
| `font` | `taxa: list[str]` | `font_name`（默认 `Arial`）、`font_style`（0–3，默认 0）、`font_size`（默认 12，>0） | 设置末端标签字体 |
| `collapse` | `taxa: list[str]` | `label`、`collapse_type`（`collapse`/`cartoon`，默认 `collapse`） | 按精确末端名折叠 |
| `collapse_group` | `group: str` | `label`、`collapse_type` | 按类群名折叠 |
| `collapse_rank` | `rank`（默认 `class`） | `collapse_style`/`collapse_type`（默认 `collapse`）、`auto_color_rank` | 按等级折叠 |
| `clear_hilights` | 无 | 无 | 清除高亮 |

`taxa` 必须是**非空字符串数组**。每个操作的执行结果写入 `operations_applied`，`status` 可能为 `applied`、`skipped`（如非单系、CLI 兼容性警告）、`error`、`noop` 或 `info`（警告汇总）。

#### 6.2 `cli_command` 与 `config_json` 注意点

- `cli_command` 形如 `python -m figtreekit "<input.tre>" -o "<output.nex>" --force ...`，使用**字面量 `python`**，不是服务器解释器路径；在不同环境重放时请替换为实际解释器，或先激活同一虚拟环境。
- 路径和 `#RRGGBB` 颜色经 shell 引号处理，可粘贴到 POSIX shell；Windows `cmd` 的引号/转义规则不同，建议在 Git Bash 或 PowerShell 中按需调整。
- `config_json` 是**字符串**，需再次 `JSON.parse`；它只包含 FigTree block 键，不包含 CLI-only 开关。
- 极坐标角度会换算为 FigTree 内部单位：`polarLayout.angularRange = (360 - polar_angular_range_degrees) * 1000`，`polarLayout.rootAngle = (polar_root_angle_degrees - 180) * 1000`。
- `--color-all` 是全局开关，命令中最多出现一次；同时包含 `color` 和 `color_all` 时，命令无法精确表达逐条语义，会返回 `warnings`。
- `collapse_group` 的 `label`/非默认 `collapse_type` 在 CLI 中没有完全等价的表达；会尽量使用解析出的末端名单，否则给出警告。
- `multi_tree=split/all`、未提供 `seed` 的 `random`、仅 `tree_index` 选择等情况会返回 `warnings`，不要假设命令逐字节等价。

### T11 `apply_config`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` / `tree_file` | string | `null` | 树源 |
| `config` | object | `null` | figtree-block 键值对（点分键） |
| `operations` | array | `null` | 与 `style_tree` 相同的操作 schema |
| `auto_color_rank` | string | `null` | 自动配色等级 |
| `collapse_rank` | string | `null` | 折叠等级 |
| `collapse_style` | string | `"collapse"` | `collapse`/`cartoon` |
| `taxonomy_levels` | string | `null` | 自定义等级前缀；加载与分析均生效 |
| `taxonomy_mapping_file` | string | `null` | 白名单内映射表 |
| `multi_tree` | string | `null` | 多树模式 |
| `tree_index` | int | `null` | 0 基索引 |
| `seed` | int | `null` | `random` 复现种子 |
| `run_name` | string | `null` | 产物基名 |

返回与 `style_tree` 相同的通用字段。`config` 不是对象 → `bad_config_type`；`operations`/枚举/数值校验失败 → `param_validation_failed`；`config` 中的键通过 figtreekit 的 `apply_dict` 直接应用，值会做布尔/数字/`null` 轻量转换。

注意：`config_json` 会合并 `additional_config`，但 `auto_color_rank`/`collapse_rank` 等分类驱动参数不在 `to_config_dict` 的键中；它们主要体现在 `cli_command` 与 `operations_applied` 中。

### T12 `export_nexus`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tree_content` / `tree_file` | string | `null` | 树源 |
| `include_taxa_block` | bool | `true` | 是否输出 TAXA block |
| `run_name` | string | `null` | 产物基名 |

返回：`ok`、`nexus_file`、`cli_command`（无样式参数，带 `--force`）、`config_json`（固定 `"{}"`）、`summary`、`operations_applied`（空数组）、`run_dir`。只做 Newick→Nexus 结构转换，不做样式化；`include_taxa_block=false` 且输入为 Newick 时，figtreekit 会发出兼容性警告，产物可能缺少 taxa block。`run_name` 不合法 → `invalid_argument/bad_run_name`。

## 7. 类群工具（T13–T19）

所有类群工具都返回通用字段：`ok`、`nexus_file`、`cli_command`、`config_json`（`"{}"`）、`operations_applied`、`summary`、`run_dir`，并附加各自的计数。它们都只处理**第一棵树**，不暴露 `multi_tree`/`tree_index`/`seed`。

### T13 `highlight_clade`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `highlights` | array | `null` | **必填**；每项 `{taxa, color?, width?, offset?}` |
| `clear_existing` | bool | `false` | 先清除待应用高亮和内嵌 `[&!hilight=...]` |
| `run_name` | string | `null` | 产物基名 |

每项：`taxa` 非空字符串数组；`color` 默认 `#999999`；`width` 默认 4，必须 >0；`offset` 默认 0，必须是整数（CLI 按 `int()` 解析）。返回额外 `highlights_applied`。错误：缺少列表 `missing_highlights`；`taxa` 非法 `bad_taxa`；颜色非法 `bad_color`；宽度 `bad_width`；偏移 `bad_offset`。

### T14 `color_clade`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `colors` | array | `null` | **必填**；每项 `{taxa, color?, all?}` |
| `run_name` | string | `null` | 产物基名 |

`color` 默认 `#999999`；`all=true` 时给全部后代分支着色，否则只给 MRCA 分支。返回额外 `colors_applied`。错误：`missing_colors`、`bad_taxa`、`bad_color`。

### T15 `set_clade_font`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fonts` | array | `null` | **必填**；每项 `{taxa, font_name?, font_style?, font_size?}` |
| `run_name` | string | `null` | 产物基名 |

`font_name` 默认 `Arial`；`font_style` 默认 0（0 plain/1 bold/2 italic/3 bold-italic）；`font_size` 默认 12，必须 >0。返回 `fonts_applied`。错误：`missing_fonts`、`bad_taxa`、`bad_font`。

### T16 `collapse_clade`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `collapses` | array | `null` | **必填**；每项 `{taxa, label?, collapse_type?}` |
| `run_name` | string | `null` | 产物基名 |

`collapse_type` 默认 `collapse`，可选 `cartoon`。返回 `collapses_applied`。非单系或 figtreekit 兼容性警告会记为 `skipped`，不使整个调用失败。错误：`missing_collapses`、`bad_taxa`、`bad_collapse_type`。

### T17 `collapse_group`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `groups` | array | `null` | **必填**；每项 `{"group": str, "label"?: str, "collapse_type"?: "collapse"/"cartoon"}` |
| `strict` | bool | `false` | 无法解析、非单系或折叠失败时抛错 |
| `taxonomy_levels` | string | `null` | 自定义等级前缀 |
| `taxonomy_mapping_file` | string | `null` | 白名单内映射表 |
| `run_name` | string | `null` | 产物基名 |

签名为 `collapse_group(tree_content=None, tree_file=None, groups=[{"group": ..., "label": ..., "collapse_type": ...}], strict=False, taxonomy_levels=None, taxonomy_mapping_file=None, run_name=None)`。每个 `group` 必须是非空类群名；`label` 省略时使用 figtreekit 的默认标签，`collapse_type` 默认 `collapse`。额外字段会被忽略（本工具不做颜色校验）。

每个类群先用 `check_monophyly_by_group` 做单系预检，再调用 `collapse_by_group`。无法解析或非单系时默认把该条记为 `skipped` 并继续处理后续类群；`strict=true` 时分别抛 `monophyly_error`，`error_key` 为 `collapse_group_failed` 或 `collapse_non_monophyletic`。返回 `groups_applied`。错误：`missing_groups`、`bad_group`、`bad_collapse_type`。

可复现性：无 `label`/非默认 `collapse_type` 时，`cli_command` 用 `--clade <group>` 表示；需要携带标签或样式时改用解析出的末端名单与 `--collapse-taxa`，无法完全等价时给出警告。

### T18 `collapse_rank`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `rank` | string | `"class"` | 要折叠的等级（代码在省略时按 `class` 处理） |
| `collapse_style` | string | `"collapse"` | `collapse`/`cartoon` |
| `auto_color_rank` | string | `null` | 折叠前配色等级；省略时用 `phylum` |
| `strict` | bool | `false` | 折叠失败/非单系时抛 `monophyly_error` |
| `taxonomy_levels` | string | `null` | 自定义等级前缀 |
| `taxonomy_mapping_file` | string | `null` | 白名单内映射表 |
| `run_name` | string | `null` | 产物基名 |

行为：先按 `auto_color_rank or "phylum"` 分析并配色，再按 `rank` 分析并折叠所有单系群；单系群即使只有一个末端也会尝试折叠（与 CLI 一致）。返回额外 `collapsed_groups`、`skipped_groups`，有兼容性警告时加 `warnings`。错误：`bad_rank`、`bad_collapse_style`；`strict` 下 `collapse_strict_failed`。

### T19 `clear_annotations`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `clear_hilights` | bool | `true` | 清除背景高亮（含内嵌 `[&!hilight=...]`） |
| `clear_collapses` | bool | `true` | 清除折叠/卡通（含内嵌 `[&!collapse=...]`/`[&!cartoon=...]`） |
| `strip_annotations` | bool | `false` | 移除通用 `[&...]` 注解，但保留 `[&R]`/`[&U]` 根标记 |
| `run_name` | string | `null` | 产物基名 |

该工具**不**清除分支颜色和字体；请用 `color_clade`/`set_clade_font` 管理。返回通用字段，`operations_applied` 记录实际执行的清除项。CLI 只有 `--clear-hilights`，没有清除折叠的开关，因此 `cli_command` 无法复现 `clear_collapses` 的效果（`config_json` 为 `"{}"`）。

## 8. 渲染工具（T20）

### T20 `render_tree`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `nexus_file` | string | `null` | 白名单内 Nexus 文件；提供时优先于 `tree_content` |
| `tree_content` | string | `null` | 树文本；会先写入运行目录的 `input.nex` |
| `format` | string | `null`（按 PNG） | `PNG`/`PDF`/`SVG`/`JPEG`（大小写不敏感） |
| `width` | int | `1600` | 必须 >0 |
| `height` | int | `1000` | 必须 >0 |
| `background_color` | string | `null` | `#RRGGBB`，栅格后处理 |
| `foreground_color` | string | `null` | `#RRGGBB`，栅格后处理 |
| `label_color` | string | `null` | `#RRGGBB`，保护标签颜色 |
| `jar_path` | string | `null` | 显式 JAR；省略时用服务端 `--jar`/自动探测 |
| `timeout` | int | `null` | 省略时使用 `AppContext.render_timeout`（`--render-timeout`，默认 180） |
| `run_name` | string | `null` | 产物基名 |

返回：`ok`、`image`（含 `data_uri`/`mime`，PNG/JPEG 可能有 `width`/`height`）、`cli_command`、`config_json`、`reproducible`（布尔）、`warnings`（数组；颜色后处理时提示命令无法复现）、`format`、`width`、`height`、`run_dir`、`ext`。

错误：缺少输入 → `missing_render_input`；格式非法 → `render_bad_format/bad_render_format`；尺寸/超时非法 → `bad_render_size`/`bad_render_timeout`；`nexus_file` 不是文件 → `nexus_not_a_file`；Java 缺失 → `java_missing`；JAR 缺失 → `jar_missing`；渲染失败/超时 → `render_failed`/`render_timeout`。

说明：

- `nexus_file` 与 `tree_content` 同时提供时使用 `nexus_file`，不会报互斥错误；
- `cli_command` 是**只读展示**，MCP 不会执行该字符串；它使用 `python -m figtreekit <input> -o <run_dir>/render.nex --force --render <image> --render-format ... --figtree-jar ...`，会在图像旁生成一个伴随 `render.nex`（CLI 在渲染模式下仍要求 `-o`），且无法复现 background/foreground/label 的 Python 后处理（此时 `reproducible=false`）；
- `image.data_uri` 仅在文件 ≤512 KiB 时生成；PDF 也会尝试 data URI（MIME `application/pdf`），但受同一 512 KiB 限制；
- 实际支持 4 种格式，但当前自动化测试只覆盖 PNG/SVG；PDF/JPEG 未做像素或结构断言。

## 9. 透传工具（T21）

### T21 `run_figtreekit_cli`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `argv` | array | `null` | **必填**；figtreekit 的参数数组，不含解释器/模块名 |
| `tree_content` | string | `null` | 写入运行目录 `input.tre`，替换 argv 中的 `<input>` |
| `input_file` | string | `null` | 白名单内输入文件，替换 `<input>` |
| `timeout` | int | `300` | 子进程超时秒数 |
| `capture_tail_bytes` | int | `65536` | 保留的 stdout/stderr 尾部字节数，最大 65536 |

限制：

- `argv` 至少 1 个元素，最多 256 个；每个元素必须是字符串且 ≤4096 字符；
- `argv[0]` 不得为 `figtreekit`、`python`、`python3`、`-m`；
- 不允许 `--figtree-jar`（会绕过受控 JAR 选择，`figtree_jar_forbidden`）；
- 输入文件白名单只作用于 `--config`、`--taxonomy-mapping-file`、`--sequences`（支持 `--flag value` 与 `--flag=value`）；不作为输入的位置参数若指向已存在的相对路径，也会按运行目录解析并检查；
- `--table-sep` 与 `--taxonomy-table-sep` 是**取值参数**（单字符分隔符），不是文件路径，因此不做白名单或文件存在性检查；传错成路径只会让 figtreekit 报参数错误；
- 所有输出参数 `-o`、`--output`、`--out`、`--render`、`--log-file`（含 `-oFILE`、`--flag=value` 形式）都会被强制改写为该运行目录下的纯文件名，改写差异逐条写入 `rewrites`；无法安全改写时返回 `bad_output_target` 或 `output_escape`；
- `tree_content` 与 `input_file` 互斥；
- 执行目录是本次 `run_dir`，命令为 `[sys.executable, "-m", "figtreekit", *argv]`，`shell=False`；
- 非零退出码 → `cli_failed`，`details` 含 `returncode` 和 stdout/stderr 尾部；超时 → `cli_timeout`。

返回：`ok`、`returncode`、`stdout_tail`、`stderr_tail`、`artifacts`（运行目录内 `.nex/.png/.pdf/.svg/.jpg/.jpeg/.log/.txt/.json/.newick/.tre`，排除 `input.tre`，图像含 data URI）、`rewrites`、`elapsed_s`、`run_dir`。

注意：`artifacts` 扫描的是运行目录中的全部匹配文件，不是“本次新增”的差分；通过 MCP 调用时每次都是新目录，因此通常等价。`timeout` 默认 300 秒，不读取 `--cli-timeout`（已知差异）。

## 10. 资源（3）

| URI | 类型 | 内容 |
|-----|------|------|
| `figtreekit://version` | JSON | `figtreekit_version`、`mcp_server_version`、`biopython_version`、`python_version`、`mcp_sdk_version`、`pillow`、`java:{ok,version}`、`jar:{ok,path}`、`render_ready`、`workspace_root`、`allowed_read_roots`；AppContext 未初始化时可能含 `server_warning` |
| `figtreekit://help` | 文本/Markdown | 一段中文说明 + `figtreekit` CLI 的 `--help` 全量文本（代码块） |
| `figtreekit://defaults` | JSON | figtreekit 的 FigTree 默认配置（figtree block 键）；读取失败时返回 `{"error": ...}` |

## 11. Prompt（2）

| 名称 | 参数（默认值） | 实际行为 |
|------|----------------|----------|
| `create-publication-figure` | `tree_file`（null）、`tree_content`（null）、`layout`（`"polar"`）、`collapse_rank`（`"class"`）、`render_formats`（`"PNG,PDF"`） | 返回中英双语长文本（中文为主，末尾英文速查），按 T04→T05→T08（可选）→T10→T20 引导；`tree_file`、`layout`、`collapse_rank`、`render_formats` 会写入正文；`tree_content` 只以“已内联/未提供”的来源说明体现，**不会嵌入整段树文本** |
| `taxonomy-audit` | `tree_file`（null）、`tree_content`（null）、`rank`（`"phylum"`） | 返回中英双语长文本，引导 T04→T05→T08→T09→T07→T10；`rank` 和树源说明会写入正文；`tree_content` 同样只体现为来源说明 |

Prompt 是给模型的工作流说明，不是工具调用本身；未提供树源时，模板会提示向用户索取。

## 12. 启动参数（`_cli.py`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--transport` | `stdio` | `stdio`/`sse`/`http`；`http` 实际运行 Streamable HTTP（`streamable-http`） |
| `--host` | `127.0.0.1` | SSE/HTTP 绑定地址；默认仅回环 |
| `--port` | `8777` | SSE/HTTP 端口，必须 >0 |
| `--allow-remote-bind` | false | 允许非回环绑定 |
| `--workspace-root` | `<cwd>/figtreekit-mcp-workspace` | 可写工作区；会创建目录 |
| `--allow-read-root DIR` | 空 | 只读根，可重复 |
| `--jar PATH` | null | 显式 JAR 路径 |
| `--content-max-bytes` | `10485760` | `tree_content` 最大字节数，必须 >0 |
| `--file-max-bytes` | `209715200` | 白名单文件最大字节数，必须 >0 |
| `--cli-timeout` | `300` | 透传超时配置（当前 `run_figtreekit_cli` 未读取，见 §9） |
| `--render-timeout` | `180` | `render_tree` 未显式传 `timeout` 时使用 |
| `--setup-timeout` | `600` | `setup_figtree` 安装超时 |
| `--keep-runs` | `50` | 保留的 run 目录数量；长期会话中每 16 次新 run 清理一次，关闭时再清理；0 表示清理全部旧目录 |
| `-v` / `--verbose` | 0 | 可重复；`-v` INFO，`-vv` DEBUG |
| `-q` / `--quiet` | false | 仅 ERROR |
| `--log-file PATH` | null | 追加写日志文件（DEBUG 级） |
| `--self-test` | false | 运行自检并退出，返回 0/1 |
| `--version` | — | 输出 `figtreekit-mcp 0.1.0` |
| `-h` / `--help` | — | 输出帮助并退出 |

退出码：0 成功，1 运行失败/自检失败，2 参数用法错误，130 被 SIGINT/SIGTERM 中断。日志只写 stderr；stdout 只用于 MCP 协议帧（`--self-test` 和 `--version` 的终端输出除外）。

## 13. 多树语义汇总

| 场景 | 行为 |
|------|------|
| `summarize_tree` 多树未指定 | 默认 `first`，返回 `multi_tree_hint`，不报错 |
| `style_tree`/`apply_config` 多树未指定 | 抛 `multi_tree_required`（除非提供 `tree_index`） |
| `multi_tree=ask` | 抛 `multi_tree_ask` |
| `first`/`last`/`random` | 选择一棵；`style_tree`/`apply_config` 只导出一棵，`random` 建议给 `seed` |
| `split`/`all` | 保留全部树、只样式化一棵（默认第 0 棵，可用 `tree_index` 指定）；MCP 单产物无法像 CLI 那样每棵树输出一个文件，返回布局差异警告 |
| `tree_index` | 0 基；越界抛 `tree_index_out_of_range`；无 CLI 等价参数 |
| 分析/校验/类群工具 | 内部固定 `first`，不暴露多树参数 |

## 14. 已知限制与实现差异

1. **GTDB/展示数据测试是条件性的**：缺少 `FigTreeKit-参考文件/参考数据-GTDB-R232` 或 `FigTreeKit-功能展示/输入文件/...` 时相关测试跳过；跳过不是通过。
2. **渲染覆盖不完整**：支持 PNG/PDF/SVG/JPEG，但自动化测试只覆盖 PNG/SVG；像素差探针只比较 PNG。PDF/JPEG 尚无结构/像素断言。
3. **`--cli-timeout` 未接入**：启动参数会被解析和保存，但 `run_figtreekit_cli` 的 `timeout` 默认值固定为 300；需要自定义时请在调用中显式传 `timeout`。
4. **Prompt 的 `tree_content` 不嵌入原文**：模板为中英双语；`tree_content` 只以来源说明体现，其余主要参数会插值。
5. **`clear_annotations` 不清理颜色/字体**：它只处理高亮和折叠（含内嵌注释）。
6. **`style_tree` 的 `split/all` 不等价于 CLI**：CLI 每棵树一个文件，MCP 单产物保留全部树但只样式化选中树。
7. **`cli_command` 的 `python` 是字面量**：重放时需替换为实际解释器；`config_json` 是字符串。
8. **`run_name` 不是目录名**：它只作为产物文件名基名；不能包含 `/`、`\` 或 `..`。
9. **错误可能以普通结果返回**：MCP 注册层将 `ToolError` 转为 `ok:false` 信封，客户端不能只依赖 `isError`。
10. **单进程单 AppContext**：同一进程创建多个服务器不受支持；工具/资源通过模块级活动上下文查找。
11. **无网络认证**：SSE/HTTP 无鉴权/TLS；`--allow-remote-bind` 只解除绑定限制，不提供安全防护。
12. **`color` 与 `color_all` 无法在一条 CLI 命令中混用**：CLI 的 `--color-all` 是全局开关，会作用于命令中的每个 `--color-clade`。同一次 `style_tree`/`apply_config` 同时包含两种操作时，MCP 结果正确，但回放的 `cli_command` 会把所有着色都当作 `color_all`，并返回 `warnings`。
13. **T07 类群名解析存在边界情况**：类群名依赖标签中的分类学信息、`taxonomy_levels` 或映射表；GTDB 风格标签可能先失败再走 taxonomy 回退；名称匹配会去掉首尾下划线，不同等级同名时可能匹配到先遍历到的等级；特殊标识只认 `LUCA`/`LACA`/`LBCA`/`root`（大小写敏感）。无法确定时请直接传精确末端名单。
