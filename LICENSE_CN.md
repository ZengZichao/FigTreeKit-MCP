# GPL-2.0-or-later 中文说明

**简体中文** | [English (canonical LICENSE)](LICENSE)

> **重要说明**
>
> - 本文件是对项目许可证的**中文解释**，**不是**许可证正式文本，也**不能替代** [`LICENSE`](LICENSE)。
> - 根目录 [`LICENSE`](LICENSE) 中的英文 GNU General Public License 全文是唯一具有法律效力的许可证文本。若本文件与 `LICENSE` 有任何不一致，以 `LICENSE` 为准。
> - 本文件不构成法律意见。涉及具体分发或商业使用时，请查阅许可证原文并咨询专业人士。

## 1. 项目采用的许可证

FigTreeKit-MCP 采用 **GNU General Public License, version 2 or later**，SPDX 标识符为：

```
GPL-2.0-or-later
```

“or later” 的含义是：你可以选择按 GPL 第 2 版使用本项目，也可以选择按自由软件基金会发布的任何更新版本（例如 GPLv3）使用。无论选择哪个版本，都应遵守该版本的全部条款。

项目元数据中的声明位置：

- `pyproject.toml`：`license = { text = "GPL-2.0-or-later" }`
- `src/figtreekit_mcp/__init__.py`：`__license__ = "GPL-2.0-or-later"`
- 每个 Python 源文件首部的 SPDX 标识：`SPDX-License-Identifier: GPL-2.0-or-later`

## 2. 你可以做什么

在遵守 GPL 的前提下，你可以：

- 为任何目的运行本程序；
- 研究本程序的实现，并按需要修改；
- 再分发本程序的副本；
- 分发你修改后的版本。

GPL 不限制你将该软件用于商业环境，也不要求你公开自己独立开发的、与本程序没有组合关系的软件。

## 3. 分发时必须注意什么

如果你**分发**本程序（包括修改版）的二进制或源码，通常需要：

1. **提供许可证文本**：随分发物附带 GPL 全文（本仓库的 `LICENSE`）以及版权、许可证声明；
2. **提供对应源码**：按 GPL 的要求提供完整、可构建的对应源码，或提供许可证允许的书面获取方式；
3. **保留声明**：不得删除或修改版权声明、许可证声明、免责声明，以及 `NOTICE` 中的第三方归属信息；
4. **同一许可证**：修改版整体仍须按 GPL 授权，不能附加额外限制；
5. **标明修改**：如果修改了文件，应显著标明修改过，并保留修改日期；
6. **不提供额外担保**：不得以任何方式暗示原作者为你分发的版本提供担保。

通过网络提供二进制下载也属于分发，同样触发上述义务。

## 4. 网络服务与 AGPL 的区别

GPLv2 本身没有类似 AGPL 的“网络使用即触发源码提供”条款。如果你只是**运行**未修改的 FigTreeKit-MCP 并通过 SSE/HTTP 向内部或外部提供服务，GPLv2 不会仅因网络交互而要求你公开自己的服务端代码。但请注意：

- 如果你分发修改后的服务器，仍须遵守 GPL 的源码提供义务；
- 如果服务中组合使用了 AGPL 组件（例如重新分发包含 iText 的 FigTree JAR），需要单独评估 AGPL 义务；
- 本项目不附带任何网络服务的安全或合规保证；SSE/HTTP 默认无鉴权，只应绑定回环地址。

## 5. 第三方组件

本项目的第三方依赖有各自许可证，**不受**本项目 GPL 覆盖，也不会因为与本项目一起分发而自动改变：

- FigTreeKit：GPL-2.0-or-later
- FigTree（FigTreeKit 的一部分基础）：GPL-2.0-or-later
- iText（FigTree JAR 中的 PDF 库）：AGPL-3.0
- Biopython：BSD-3-Clause
- MCP Python SDK：MIT
- Pillow（可选）：HPND

完整归属与说明见英文 [`NOTICE`](NOTICE) 及中文摘要 [`NOTICE_CN.md`](NOTICE_CN.md)。其中 iText 的 AGPL-3.0 义务需要特别注意；如果你重新分发 `figtree_patched.jar`，应确认自己满足 AGPL-3.0 的相应要求。

## 6. 无担保

本程序按“现状”提供，不附带任何明示或默示担保，包括但不限于适销性、特定用途适用性和不侵权的担保。使用本程序产生的任何风险由使用者自行承担。完整免责条款以 [`LICENSE`](LICENSE) 为准。

## 7. 如何获取源码

本仓库即完整源码：

<https://github.com/ZengZichao/FigTreeKit-MCP>

如果你收到的是二进制分发物，请向分发者索取对应源码，或从上述仓库获取对应版本（v0.1.0）的源码。

## 8. 相关文件

- [`LICENSE`](LICENSE)：GPL 正式英文全文（唯一具法律效力的许可证文本）
- [`NOTICE`](NOTICE)：英文第三方组件声明（正式版本）
- [`NOTICE_CN.md`](NOTICE_CN.md)：第三方组件中文说明
- [`CITATION_EN.md`](CITATION_EN.md) / [`CITATION_CN.md`](CITATION_CN.md)：引用方式
- [`SECURITY.md`](SECURITY.md) / [`SECURITY_CN.md`](SECURITY_CN.md)：安全策略
