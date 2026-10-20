#!/usr/bin/env sh
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
#
# figtreekit-mcp.sh - portable launcher for MCP clients that do not inherit a
# shell environment (Claude Desktop, Cursor, ...).
#
# The project root is derived from this script's own location, so the script
# can be moved with the checkout.  The Python interpreter is selected with
# $PYTHON (default: python3); no author-specific absolute paths are used.
#
# Usage:
#   bash scripts/figtreekit-mcp.sh [server args...]
#   PYTHON=/path/to/python3.11 bash scripts/figtreekit-mcp.sh \
#       --allow-read-root /path/to/tree/data
#
# Extra arguments are forwarded to `python -m figtreekit_mcp`; the default
# transport is stdio.  The workspace can be overridden with
# $FIGTREEKIT_MCP_WORKSPACE or by passing --workspace-root.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

PYTHON_BIN=${PYTHON:-${ENV_PY:-python3}}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    printf '[figtreekit-mcp][ERROR] Python interpreter "%s" not found.\n' "$PYTHON_BIN" >&2
    printf '  Set PYTHON=/path/to/python3.11 or install Python 3.11+.\n' >&2
    exit 1
fi

WORKSPACE_ROOT=${FIGTREEKIT_MCP_WORKSPACE:-"$PROJECT_ROOT/figtreekit-mcp-workspace"}

exec "$PYTHON_BIN" -m figtreekit_mcp \
    --transport stdio \
    --workspace-root "$WORKSPACE_ROOT" \
    "$@"
