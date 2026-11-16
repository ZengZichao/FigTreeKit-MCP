#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""stdio debug client for FigTreeKit-MCP.

Drives a real server subprocess over the official ``mcp`` client SDK:

* ``--list-tools``                    list all tools;
* ``--call <tool> '<json-args>'``     call a tool with JSON arguments;
* ``--read-resource <uri>``           read one of the resources;
* ``--dump-schema``                   dump the JSON Schema for every tool;
* ``--prompt <name>``                 fetch a prompt.

The client is the same code path used by ``tests/test_server_smoke.py`` (E2E,
no mock).  It never contains author-specific paths:

* the workspace defaults to ``$FIGTREEKIT_MCP_WORKSPACE`` or
  ``<repo>/figtreekit-mcp-workspace``;
* read roots come from repeated ``--allow-read-root`` options or from
  ``$FIGTREEKIT_MCP_READ_ROOTS`` (``os.pathsep``-separated, ``;`` on Windows,
  ``:`` on POSIX).

Usage::

    python tools/mcp_debug_client.py --list-tools
    python tools/mcp_debug_client.py --read-resource figtreekit://version
    python tools/mcp_debug_client.py \\
        --allow-read-root /path/to/tree/data \\
        --call summarize_tree '{"tree_file": "/path/to/tree/data/tree.nwk"}'

Exit codes: 0 = success, 1 = tool returned ``isError`` / client failure,
2 = usage error or missing dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List

# --------------------------------------------------------------------------- #
# Resolve the checkout (package lives under src/) for script execution.
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (_ROOT, _ROOT / "src"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

try:  # pragma: no cover - exercised by running the script
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ModuleNotFoundError as exc:  # pragma: no cover
    print(f"[FAIL] missing dependency {exc.name!r}; run bash scripts/setup_env.sh", file=sys.stderr)
    raise SystemExit(2) from exc

_DEFAULT_WORKSPACE = os.environ.get("FIGTREEKIT_MCP_WORKSPACE") or str(
    _ROOT / "figtreekit-mcp-workspace"
)


def _env_read_roots() -> List[str]:
    raw = os.environ.get("FIGTREEKIT_MCP_READ_ROOTS", "")
    return [item for item in raw.split(os.pathsep) if item.strip()]


def _server_params(workspace_root: str, read_roots: List[str]) -> StdioServerParameters:
    args = ["-m", "figtreekit_mcp", "--transport", "stdio", "--workspace-root", workspace_root]
    for root in read_roots:
        args += ["--allow-read-root", root]

    # Inherit the current environment (JAVA_HOME / PATH) and make the source
    # checkout importable in the server subprocess even without an editable
    # install.
    env = os.environ.copy()
    pythonpath = [str(_ROOT / "src"), str(_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    return StdioServerParameters(
        command=sys.executable,
        args=args,
        env=env,
    )


async def _run() -> int:
    parser = argparse.ArgumentParser(
        prog="mcp_debug_client",
        description="stdio debug client: --call / --list-tools / "
        "--read-resource / --dump-schema / --prompt",
    )
    parser.add_argument(
        "--call", nargs=2, metavar=("TOOL", "JSON"), help="call a tool with JSON arguments"
    )
    parser.add_argument("--list-tools", action="store_true", help="list all tools")
    parser.add_argument("--read-resource", metavar="URI", help="read a resource")
    parser.add_argument("--dump-schema", action="store_true", help="dump every tool's JSON Schema")
    parser.add_argument("--prompt", metavar="NAME", help="fetch a prompt")
    parser.add_argument(
        "--workspace-root",
        default=_DEFAULT_WORKSPACE,
        help="writable workspace (default: $FIGTREEKIT_MCP_WORKSPACE "
        "or <repo>/figtreekit-mcp-workspace)",
    )
    parser.add_argument(
        "--allow-read-root",
        action="append",
        default=None,
        help="read-only whitelist root (repeatable; default: $FIGTREEKIT_MCP_READ_ROOTS)",
    )
    args = parser.parse_args()

    if not (args.call or args.list_tools or args.read_resource or args.dump_schema or args.prompt):
        parser.print_help()
        return 2

    read_roots = list(args.allow_read_root or _env_read_roots())
    params = _server_params(args.workspace_root, read_roots)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            if args.list_tools:
                tools = await session.list_tools()
                print(f"{len(tools.tools)} tools:")
                for tool in tools.tools:
                    print(f"  - {tool.name}: {tool.description.splitlines()[0]}")
                return 0

            if args.read_resource:
                result = await session.read_resource(args.read_resource)
                print(result.contents[0].text)
                return 0

            if args.dump_schema:
                tools = await session.list_tools()
                for tool in tools.tools:
                    print(f"### {tool.name}")
                    print(json.dumps(tool.inputSchema, indent=2, ensure_ascii=False))
                return 0

            if args.prompt:
                prompt = await session.get_prompt(args.prompt)
                print(prompt.description or "")
                for message in prompt.messages:
                    print(message.content.text)
                return 0

            if args.call:
                tool_name, raw_args = args.call
                try:
                    call_args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError as exc:
                    print(f"[usage] invalid JSON arguments: {exc}", file=sys.stderr)
                    return 2
                result = await session.call_tool(tool_name, call_args)
                print(
                    json.dumps(
                        {
                            "isError": result.isError,
                            "content": [content.text for content in result.content],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 1 if result.isError else 0
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
