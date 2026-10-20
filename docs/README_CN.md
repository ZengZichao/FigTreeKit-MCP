# FigTreeKit-MCP 文档索引

**简体中文** | [English](README_EN.md)

本目录收录 FigTreeKit-MCP v0.1.0 的技术文档。每篇文档均有中英文对照版本：中文为默认阅读语言，英文用于国际协作与发布。工具参数以 `src/figtreekit_mcp/tools/*.py` 的函数签名、`params.py` 的 `ParamSpec` 与 `_cli.py` 的启动参数为准。

## 阅读路线

| 你的目标 | 建议顺序 |
|----------|----------|
| 第一次安装并接入客户端 | 根目录 [`README.md`](../README.md) → [`deployment_and_client_setup_CN.md`](deployment_and_client_setup_CN.md) |
| 查询某个工具的参数、返回值与错误键 | [`tools_reference_CN.md`](tools_reference_CN.md) |
| 修改源码、增加工具或排查测试 | [`development_guide_CN.md`](development_guide_CN.md) → [`testing_and_acceptance_CN.md`](testing_and_acceptance_CN.md) |
| 做真实数据验收或复现 AC/SEC 检查 | [`testing_and_acceptance_CN.md`](testing_and_acceptance_CN.md) |
| 运行示例脚本 | [`../examples/README_CN.md`](../examples/README_CN.md) |
| 了解许可证、引用与安全边界 | [`../LICENSE_CN.md`](../LICENSE_CN.md)、[`../CITATION_CN.md`](../CITATION_CN.md)、[`../SECURITY_CN.md`](../SECURITY_CN.md) |

## 核心文档（中英对照）

| 文档 | 中文 | English | 内容 |
|------|------|---------|------|
| 工具参考 | [`tools_reference_CN.md`](tools_reference_CN.md) | [`tools_reference_EN.md`](tools_reference_EN.md) | 21 个工具（T01–T21）的参数、类型、默认值、返回键与错误键；3 个资源与 2 个 Prompt；CLI 启动参数；多树语义；已知限制 |
| 开发指南 | [`development_guide_CN.md`](development_guide_CN.md) | [`development_guide_EN.md`](development_guide_EN.md) | 架构与模块划分、请求生命周期、新增工具、等价性契约、安全模型、并发与错误映射、开发命令 |
| 部署与客户端接入 | [`deployment_and_client_setup_CN.md`](deployment_and_client_setup_CN.md) | [`deployment_and_client_setup_EN.md`](deployment_and_client_setup_EN.md) | 三平台安装、Java/JAR 准备、Claude Desktop/Cursor/VS Code 配置、SSE/Streamable HTTP、故障排查 |
| 测试与验收 | [`testing_and_acceptance_CN.md`](testing_and_acceptance_CN.md) | [`testing_and_acceptance_EN.md`](testing_and_acceptance_EN.md) | pytest/覆盖率/自检、测试数据、跳过语义、等价性探针、GTDB 验收、AC/SEC 复现步骤 |

## 根目录文档

| 文件 | 中文 | English | 说明 |
|------|------|---------|------|
| 项目说明 | [`README.md`](../README.md) | [`README_EN.md`](../README_EN.md) | 项目介绍、安装、启动、工具总表、质量与验证 |
| 引用 | [`CITATION_CN.md`](../CITATION_CN.md) | [`CITATION_EN.md`](../CITATION_EN.md)、[`CITATION.cff`](../CITATION.cff) | 引用方式与机器可读元数据 |
| 第三方声明 | [`NOTICE_CN.md`](../NOTICE_CN.md) | [`NOTICE`](../NOTICE) | 第三方组件归属；英文为正式版 |
| 许可证 | [`LICENSE_CN.md`](../LICENSE_CN.md) | [`LICENSE`](../LICENSE) | GPL 中文说明与正式许可证文本 |
| 安全策略 | [`SECURITY_CN.md`](../SECURITY_CN.md) | [`SECURITY.md`](../SECURITY.md) | 安全边界与漏洞报告方式 |

## 示例、脚本与工具说明

| 目录 | 中文 | English | 内容 |
|------|------|---------|------|
| 示例 | [`examples/README_CN.md`](../examples/README_CN.md) | [`examples/README_EN.md`](../examples/README_EN.md) | 可运行示例与配套说明 |
| 示例 01：校验与摘要 | [`examples/01_validate_and_summarize_CN.md`](../examples/01_validate_and_summarize_CN.md) | [`examples/01_validate_and_summarize_EN.md`](../examples/01_validate_and_summarize_EN.md) | 验证 + 摘要工作流 |
| 示例 02：分类学审计 | [`examples/02_taxonomy_audit_CN.md`](../examples/02_taxonomy_audit_CN.md) | [`examples/02_taxonomy_audit_EN.md`](../examples/02_taxonomy_audit_EN.md) | 批量单系性审计 |
| 示例 03：出版级出图 | [`examples/03_publication_figure_CN.md`](../examples/03_publication_figure_CN.md) | [`examples/03_publication_figure_EN.md`](../examples/03_publication_figure_EN.md) | 样式化 + 渲染 |
| 脚本 | [`scripts/README_CN.md`](../scripts/README_CN.md) | [`scripts/README_EN.md`](../scripts/README_EN.md) | 环境安装与启动脚本 |
| 工具 | [`tools/README_CN.md`](../tools/README_CN.md) | [`tools/README_EN.md`](../tools/README_EN.md) | 等价性探针、GTDB 验收、MCP 调试客户端、参考测试生成器 |

## 版本与写作约定

- 文档对应 **v0.1.0**（`src/figtreekit_mcp/_version.py`）。
- 工具参数以函数签名为准；默认值同时受 `params.py` 的 `ParamSpec` 与 `server.py` 的 `AppContext` 影响。
- 命令行示例中的 `<project-root>`、`<python>`、`<data-dir>`、`<workspace>` 均为占位符，请替换为实际路径；含空格的路径必须加引号。
- 错误信封中的 `error` 是中文可读消息，`error_key` 是稳定的机器可读标识；程序化处理请使用 `code` / `error_key`。
- 真实数据测试可能因缺少 GTDB/展示数据而跳过；文档中的“通过”只指实际运行过的检查。
