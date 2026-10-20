# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Reproducible command-line generation with shell-safe quoting.

``cli_command`` strings are **for humans** (AI → user → terminal).  They are
built with field-level quoting so they can be pasted into zsh and re-run
byte-for-byte.  They are never re-parsed for execution — the MCP handlers run
the equivalent argv list directly.  Hex colours
``#RRGGBB`` are quoted because a leading ``#`` would otherwise start a shell
comment; this mirrors Studio's ``_quote_arg`` semantics.
"""

from __future__ import annotations

import shlex
from typing import Iterable, List, Optional

from ._logging import get_logger

_log = get_logger()

# Characters a POSIX shell takes verbatim inside a word (Studio parity).
_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@%+=:,./_-")


def quote_arg(text: str) -> str:
    """Shell-quote one argument (keeps hex colours runnable)."""
    s = str(text)
    if s and all(ch in _SAFE_CHARS for ch in s):
        return s
    return shlex.quote(s)


def build_figtreekit_command(
    input_path: str,
    output_path: str,
    args_list: Iterable[str],
    *,
    force: bool = True,
    python: Optional[str] = None,
    module: str = "figtreekit",
) -> str:
    """Build ``python -m figtreekit <input> -o <output> [--force] <args>``.

    Args:
        input_path: Input tree file (absolute path).
        output_path: Output Nexus file (absolute path).
        args_list: Styling argv produced by ``ParamSpec.to_cli_args()``.
        force: Add ``--force`` (yes by default — the MCP always writes into a
            fresh run directory, so overwrite semantics are safe).
        python: Interpreter path; defaults to ``python``.
    """
    cmd = [quote_arg(python or "python"), "-m", module, quote_arg(input_path),
           "-o", quote_arg(output_path)]
    if force:
        cmd.append("--force")
    cmd += [quote_arg(a) for a in args_list]
    return " ".join(cmd)


def build_java_render_command(
    nexus_path: str,
    output_path: str,
    fmt: str,
    width: int,
    height: int,
    jar_path: str,
    *,
    java: str = "java",
) -> str:
    """Build ``java -jar <jar> -graphic FMT -width W -height H <in> <out>``."""
    parts = [
        quote_arg(java), "-jar", quote_arg(jar_path),
        "-graphic", str(fmt).upper(),
        "-width", str(width),
        "-height", str(height),
        quote_arg(nexus_path),
        quote_arg(output_path),
    ]
    return " ".join(parts)


def join_commands(commands: Iterable[str]) -> str:
    """Join several reproducible commands with `` && `` (all-or-nothing)."""
    return " && ".join(c for c in commands if c)


def bash_repr(value: object) -> str:
    """Render a Python value as a shell-friendly literal (for docs/tests)."""
    return quote_arg(str(value))


# Round-trip helper for tests: verify a built command re-parses exactly.
def split_for_check(command: str) -> List[str]:
    """Split a built command with shlex (verification only, never execution)."""
    return shlex.split(command)
