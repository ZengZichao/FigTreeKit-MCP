# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""FigTreeKit-MCP: MCP server exposing FigTreeKit capabilities to AI assistants.

The server exposes 21 MCP Tools, 3 Resources and 2 Prompts covering the full
FigTreeKit pipeline — validate, analyze, style, export and render phylogenetic
trees — with every invocation returning an equivalent ``figtreekit`` CLI
command and JSON configuration for byte-for-byte reproducibility.

Typical usage::

    python -m figtreekit_mcp --transport stdio
"""

# Copyright (C) 2026 Zeng Zichao
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from ._version import __version__

__author__ = "Zeng Zichao"
__email__ = "zengzichao@sjtu.edu.cn"
__license__ = "GPL-2.0-or-later"

__all__ = ["__version__", "create_server", "main"]


def __getattr__(name: str):
    """Expose ``create_server``/``main`` lazily to keep package import light."""
    if name == "create_server":
        from .server import create_server

        return create_server
    if name == "main":
        from ._cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
