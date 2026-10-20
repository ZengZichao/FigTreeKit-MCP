# Security Policy

**English** | [简体中文](SECURITY_CN.md)

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

Only the latest 0.1.x release receives security fixes. Because this project runs locally, the most effective mitigation is often to upgrade to the latest commit or release and restart the MCP client.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security → Report a vulnerability):

<https://github.com/ZengZichao/FigTreeKit-MCP/security/advisories/new>

This channel is visible only to you and the maintainer. If that channel is unavailable, email <zengzichao@sjtu.edu.cn> with the subject `[SECURITY] FigTreeKit-MCP`.

Include, where possible:

- affected version or commit;
- operating system and Python/Java versions;
- a minimal reproduction (tool name, arguments and input files, with sensitive data removed);
- the observed result and the impact you believe it has.

Please do **not** open a public issue for a vulnerability before a fix or mitigation has been agreed. Acknowledgement and remediation are best-effort; no response-time SLA is offered for this research software.

## Scope

In scope:

- path traversal or symlink escapes in `tree_file`, `sequences_file`, `taxonomy_mapping_file`, `nexus_file`, `jar_path`, `input_file`, or CLI pass-through arguments;
- writes outside the configured workspace;
- shell injection or argument injection through `run_figtreekit_cli`;
- bypasses of the content/anomaly scan or of the size limits;
- crashes or resource exhaustion caused by untrusted tree/sequence content that are reachable through normal tool calls;
- leakage of files outside the allowed read roots.

Out of scope (report upstream where appropriate):

- vulnerabilities in Java, FigTree/FigTreeKit, Biopython, Pillow or the MCP SDK themselves;
- the absence of authentication on `--transport sse` / `--transport http` (this is a documented design choice; see below);
- deployments that bind a non-loopback address with `--allow-remote-bind` without an authenticating reverse proxy or network isolation;
- vulnerabilities that require the attacker to already control the MCP client, the Python interpreter, the workspace, or the local user account.

## Security model (v0.1.0)

FigTreeKit-MCP is a local stdio-oriented server. Its main controls are:

1. **Two-tier filesystem whitelist.** One writable workspace root (`--workspace-root`) and zero or more read-only roots (`--allow-read-root`). The workspace root is implicitly readable.
2. **Canonical path checks.** Inputs are resolved with `Path.resolve()` (following symlinks) and must remain inside a registered root. Paths containing `..` are rejected before resolution. A symlink inside a root that points outside the root is rejected.
3. **Output containment.** Every tool writes into a fresh `run_<uuid8>` directory under the workspace. `style_tree`/`apply_config`/`export_nexus` restrict `run_name` to letters, digits, `_` and `-` (1–64 characters); other tools pass artifact names through `RunStorage.file_path`, which permits only a basename inside the run directory. Pass-through output flags (`-o`, `--output`, `--out`, `--render`, `--log-file`) are rewritten to a basename inside the run directory, and rewrites are reported in the `rewrites` field.
4. **No shell.** `run_figtreekit_cli` executes an argument vector through `subprocess.run(..., shell=False)`. Shell metacharacters are literal data. `argv[0]` may not name `figtreekit`, `python`, `python3` or `-m`; `--figtree-jar` is rejected in pass-through to prevent execution of an arbitrary JAR; input-file flags are whitelist-checked.
5. **Content checks and limits.** Tree/sequence text is scanned for control characters and Unicode bidirectional overrides before parsing. Default limits: 10 MiB for `tree_content` (`--content-max-bytes`) and 200 MiB for files (`--file-max-bytes`).
6. **Loopback by default.** SSE and Streamable HTTP bind to `127.0.0.1:8777` unless a different host/port is requested. Non-loopback hosts require the explicit `--allow-remote-bind` flag.

The server does **not** sandbox the `figtreekit`/FigTree code, the JVM, or Python itself. It assumes that the workspace, the installed `figtreekit` package and the JAR are trusted.

## Network transports

`--transport sse` and `--transport http` have **no authentication and no TLS**. They are intended for a local client on the same machine, or for a trusted network behind an authenticating reverse proxy/VPN. If you use `--allow-remote-bind`, you are responsible for access control, TLS termination, rate limiting and monitoring. Do not expose the server directly to the public Internet. See [`docs/deployment_and_client_setup_EN.md`](docs/deployment_and_client_setup_EN.md) for a deployment checklist.

## Handling untrusted data

- Treat tree/sequence files and taxonomy tables from third parties as untrusted input.
- Prefer passing data through `tree_content` or a dedicated read-only root rather than granting broad filesystem access.
- Keep the workspace on a dedicated directory; review or delete `run_*` artifacts before sharing them.
- Log files may contain absolute paths and fragments of command output; protect them accordingly.
- Run the server with the least-privileged account that can read the intended data and write the workspace.

## Known limitations (security-relevant)

- Tool calls are serialized by a process-global re-entrant lock (`_concurrency.serialized`, acquired inside the AnyIO worker in `server._threaded_tool`). This protects figtreekit's global taxonomy state and Java/CLI execution, but limits throughput to one tool at a time. A cancelled call's worker may continue until the handler returns and still holds the lock.
- `setup_figtree` may download or compile a JAR in a child process; only run it in an environment where that network/build activity is acceptable.
- Error envelopes contain Chinese human-readable messages and technical details that may include absolute paths. They are returned to the MCP client by design.
- The server is designed for one active `AppContext` per process; embedding multiple servers in one process is not supported.

## Disclosure policy

Once a fix is available, the reporter and maintainer may agree on a coordinated disclosure. There is no bug bounty program. Credit will be given in the security advisory if the reporter wishes.
