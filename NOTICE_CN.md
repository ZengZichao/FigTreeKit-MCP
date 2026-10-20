# 第三方组件声明（中文说明）

**简体中文** | [English (canonical)](NOTICE)

> **法律效力说明**：英文版 [`NOTICE`](NOTICE) 是正式版本；本文件是其中文翻译与摘要，仅便于理解。若中英文表述不一致，以英文 `NOTICE` 为准。项目自身代码的许可证以根目录 [`LICENSE`](LICENSE) 中的 GNU GPL 全文为准；本文件不能替代该许可证，也不构成法律意见。

## 项目本身

FigTreeKit-MCP<br>
Copyright (C) 2026 Zeng Zichao

本程序为自由软件：你可以依据自由软件基金会发布的 GNU 通用公共许可证（GPL）第 2 版或（由你选择）任何更新版本重新发布和/或修改它。本程序按“现状”提供，不附带任何明示或默示担保，包括但不限于适销性或特定用途适用性的担保。详见 [`LICENSE`](LICENSE)。

FigTreeKit-MCP 是一个 MCP（Model Context Protocol）服务器，把 FigTreeKit 的系统发育树流程（校验、分析、样式化、导出、渲染）暴露给 AI 助手。树计算与渲染全部委托给 FigTreeKit 内核；本仓库不内置、也不修改 FigTree 的 Java 源码。

## 第三方组件

| 组件 | 用途 | 许可证 | 说明 |
|------|------|--------|------|
| **FigTreeKit** | 计算内核（`figtreekit>=1.1.4,<2`） | GPL-2.0-or-later | Copyright (C) 2024-2026 Zeng Zichao，<https://github.com/ZengZichao/FigTreeKit> |
| **FigTree** | FigTreeKit 的部分基础（v1.4.4） | GPL-2.0-or-later | Copyright (C) 2006-2014 Andrew Rambaut，<https://github.com/rambaut/figtree>；FigTreeKit 随附经过源码修改的 `figtree_patched.jar`，细节见 FigTreeKit 的 NOTICE |
| **iText** | FigTree JAR 的 PDF 导出依赖（`com.itextpdf.text.*`） | AGPL-3.0 | 若重新分发该 JAR，需单独评估并遵守 iText 的 AGPL-3.0 义务；这部分义务独立于本项目的 GPL-2.0-or-later |
| **Biopython** | 树与序列解析（经 FigTreeKit 使用） | BSD-3-Clause | |
| **MCP Python SDK** | MCP 协议、FastMCP、传输与测试客户端（`mcp` 包） | MIT | <https://github.com/modelcontextprotocol/python-sdk> |
| **Pillow** | 可选 `render` extra：图像尺寸读取与 base64 预览；等价性探针的像素统计 | HPND | <https://python-pillow.org/>，仅在安装 `[render]` 时引入 |

## 源码获取

- FigTreeKit-MCP：<https://github.com/ZengZichao/FigTreeKit-MCP>
- FigTreeKit：<https://github.com/ZengZichao/FigTreeKit>
- FigTree：<https://github.com/rambaut/figtree>

## 免责声明

本程序按“现状”分发，不附带任何担保；详细法律条款见 [`LICENSE`](LICENSE)。第三方组件仍受各自许可证约束，上文仅为摘要，不替代相应许可证原文。

> 本中文文件不是法律文件，也不构成法律建议。需要确定具体合规义务时，请查阅相应许可证原文并咨询专业人士。
