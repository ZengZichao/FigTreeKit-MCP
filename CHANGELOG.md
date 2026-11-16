# Changelog

本文件记录 FigTreeKit-MCP 的版本变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v0.1.0] - 2026-10-20

### 新增（Added）

- **21 个 MCP 工具（T01–T21）**：环境检查与安装、校验、分类学分析、样式化与导出、
  类群操作、渲染，以及完整的 FigTreeKit CLI 透传。
- **3 个资源**：`figtreekit://version`、`figtreekit://help`、`figtreekit://defaults`。
- **2 个 Prompt**：`create-publication-figure`、`taxonomy-audit`。
- **可复现性红线**：`style_tree`、`apply_config`、`export_nexus` 返回等效的
  `cli_command` 与 `config_json`，可在 zsh 中逐字节复现。
- **安全边界**：可写工作区 + 零到多个只读根、`Path.resolve()` 软链收束、拒绝 `..`
  与盘符相对路径、零 shell 列表执行、输出强制重定向到 `run_<uuid8>`。
- **三种传输**：stdio（默认）、SSE、Streamable HTTP。
- **并发**：同步 handler 在 AnyIO 工作线程中运行，全局 `RLock` 串行化 CLI/JAR 执行。
- **测试**：20 个测试文件，覆盖单元、工具层集成、E2E 协议、SEC-1..12 安全、
  hypothesis 属性、并发与工作区加固。
- **工具脚本**：`tools/equivalence_probe.py`、`tools/ref_test_gen.py`、
  `tools/gtdb_acceptance.py`、`tools/mcp_debug_client.py`。
- **文档**：中英双语 `README` 与 `docs/`、`examples/`、`scripts/`、`tools/` 说明，
  以及 `SECURITY.md`、`CITATION.cff`、`NOTICE`。
- **打包**：`pyproject.toml`（setuptools、`py.typed`、render/dev 可选依赖）与 `MANIFEST.in`。

### 变更（Changed）

- 无（首个公开发布版本）。

### 修复（Fixed）

- 无（首个公开发布版本）。
