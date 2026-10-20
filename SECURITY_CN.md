# 安全策略

[English](SECURITY.md) | **简体中文**

## 支持版本

| 版本 | 是否支持 |
|------|----------|
| 0.1.x | 是 |
| < 0.1 | 否 |

仅最新的 0.1.x 版本会获得安全修复。本项目在本地运行，最有效的缓解措施通常是升级到最新提交或版本，并重启 MCP 客户端。

## 报告安全问题

请优先使用 GitHub 的私密漏洞报告（Security → Report a vulnerability）：

<https://github.com/ZengZichao/FigTreeKit-MCP/security/advisories/new>

该渠道仅你与维护者可见。若无法使用该渠道，可邮件联系 <zengzichao@sjtu.edu.cn>，标题请注明 `[SECURITY] FigTreeKit-MCP`。

建议尽量提供：

- 受影响的版本或提交；
- 操作系统与 Python/Java 版本；
- 最小复现步骤（工具名、参数、输入文件；请先移除敏感数据）；
- 观察到的结果，以及你认为的影响。

在修复或缓解方案达成一致前，请**不要**公开提交 issue。本项目是科研软件，确认与修复均尽力而为，不承诺固定的响应时限。

## 范围

属于范围：

- `tree_file`、`sequences_file`、`taxonomy_mapping_file`、`nexus_file`、`jar_path`、`input_file` 或 CLI 透传参数中的路径穿越、软链接逃逸；
- 向配置的工作区之外写入；
- 通过 `run_figtreekit_cli` 进行 shell 注入或参数注入；
- 绕过异常内容扫描或大小限制；
- 通过正常工具调用即可触发的、由不可信树/序列内容导致的崩溃或资源耗尽；
- 读取允许根目录之外的文件。

不属于范围（请向相应上游报告）：

- Java、FigTree/FigTreeKit、Biopython、Pillow 或 MCP SDK 自身的漏洞；
- `--transport sse` / `--transport http` 没有身份认证（这是已记录的设计选择，见下文）；
- 使用 `--allow-remote-bind` 绑定非回环地址、却没有认证反向代理或网络隔离的部署；
- 攻击者已经控制 MCP 客户端、Python 解释器、工作区或本地账户的前提下才能利用的问题。

## 安全模型（v0.1.0）

FigTreeKit-MCP 是一个面向本地 stdio 的服务器，主要控制措施如下：

1. **两级文件系统白名单**：一个可写工作区根（`--workspace-root`）和零到多个只读根（`--allow-read-root`）。工作区根本身可读。
2. **规范化路径检查**：输入经 `Path.resolve()` 解析（跟随软链接），最终目标必须位于已注册根目录内；含 `..` 的路径在解析前即被拒绝；根目录内指向外部的软链接会被拒绝。
3. **产物收敛**：所有工具写入工作区下全新的 `run_<uuid8>` 目录。`style_tree`/`apply_config`/`export_nexus` 对 `run_name` 限制为字母、数字、`_` 和 `-`（1–64 字符）；其他工具通过 `RunStorage.file_path` 限制为运行目录内的纯文件名。透传的输出参数（`-o`、`--output`、`--out`、`--render`、`--log-file`）会被改写为运行目录内的纯文件名，并在 `rewrites` 字段中披露。
4. **零 shell**：`run_figtreekit_cli` 通过 `subprocess.run(..., shell=False)` 执行参数数组，shell 元字符只作为普通数据。`argv[0]` 不得为 `figtreekit`、`python`、`python3` 或 `-m`；透传中禁止 `--figtree-jar`，以防执行任意 JAR；输入文件参数会经过白名单检查。
5. **内容检查与限额**：树/序列文本在解析前扫描控制字符与 Unicode 双向覆盖字符。默认限额：`tree_content` 为 10 MiB（`--content-max-bytes`），文件为 200 MiB（`--file-max-bytes`）。
6. **默认仅回环**：SSE 与 Streamable HTTP 默认绑定 `127.0.0.1:8777`；如需其他主机/端口需显式指定；绑定非回环地址必须加 `--allow-remote-bind`。

服务器**不会**对 `figtreekit`/FigTree 代码、JVM 或 Python 本身做沙箱隔离。它假定工作区、已安装的 `figtreekit` 包与 JAR 是可信的。

## 网络传输

`--transport sse` 与 `--transport http` **没有身份认证，也没有 TLS**。它们只适合本机客户端，或位于认证反向代理/VPN 之后的可信网络。使用 `--allow-remote-bind` 时，访问控制、TLS 终止、限流和监控均由你负责。不要把服务器直接暴露到公网。部署清单见 [`docs/deployment_and_client_setup_CN.md`](docs/deployment_and_client_setup_CN.md)。

## 处理不可信数据

- 把第三方树/序列文件与分类映射表视为不可信输入。
- 优先使用 `tree_content` 或专门设置的只读根，而不是授予宽泛的文件系统访问权限。
- 将工作区放在专用目录；分享 `run_*` 产物前先检查或删除。
- 日志文件可能包含绝对路径和命令输出片段，请按敏感信息保护。
- 使用能够读取目标数据、写入工作区的最小权限账户运行服务器。

## 已知限制（与安全相关）

- 工具调用由进程级可重入锁串行化（`server._threaded_tool` 在 AnyIO 工作线程内获取 `_concurrency.serialized`）。这保护 figtreekit 的全局分类学状态与 Java/CLI 执行，但同一时刻只能运行一个工具。被取消调用的工作线程可能继续运行到 handler 返回，并仍持有该锁。
- `setup_figtree` 可能在子进程中下载或编译 JAR；请只在允许此类网络/构建活动的环境中使用。
- 错误信封包含中文可读消息和技术细节，可能带有绝对路径；这是按设计返回给 MCP 客户端的。
- 服务器设计为每个进程只有一个活动 `AppContext`；不支持在同一进程中嵌入多个服务器。

## 披露策略

修复可用后，报告者与维护者可协商协调披露。本项目没有漏洞赏金计划。如报告者愿意，安全公告中会致谢。
