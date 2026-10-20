#!/usr/bin/env sh
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
#
# setup_env.sh - install / repair the Python environment for FigTreeKit-MCP.
#
# Portable POSIX sh: no micromamba, no hard-coded interpreter paths.
# Everything is installed into the interpreter you select with $PYTHON.
#
# Usage:
#   bash scripts/setup_env.sh
#   PYTHON=/path/to/python3.11 bash scripts/setup_env.sh
#   FIGTREEKIT_SRC=/path/to/FigTreeKit bash scripts/setup_env.sh
#
# Environment variables:
#   PYTHON          Python 3.11+ interpreter (default: python3)
#   ENV_PY          Fallback name for PYTHON (kept for compatibility)
#   FIGTREEKIT_SRC  Optional path to a FigTreeKit checkout; when set it is
#                   installed editable (--no-deps) before this project.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

PYTHON_BIN=${PYTHON:-${ENV_PY:-python3}}

say() {
    printf '%s\n' "$*"
}

fail() {
    printf '[setup][ERROR] %s\n' "$*" >&2
    exit 1
}

say "[setup] Project root : $PROJECT_ROOT"
say "[setup] Interpreter  : $PYTHON_BIN"

# --------------------------------------------------------------------------- #
# 0) Check the interpreter
# --------------------------------------------------------------------------- #
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    fail "Python interpreter '$PYTHON_BIN' was not found.
       Install Python 3.11+ and rerun, or point PYTHON at it:
         PYTHON=/path/to/python3.11 bash scripts/setup_env.sh"
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "$("$PYTHON_BIN" -c 'import sys; print(sys.version)') is too old.
       FigTreeKit-MCP requires Python >= 3.11."
fi

"$PYTHON_BIN" -m pip --version >/dev/null 2>&1 || fail \
    "pip is not available for '$PYTHON_BIN'.
       Create a virtual environment first, for example:
         python3.11 -m venv .venv
         PYTHON=.venv/bin/python bash scripts/setup_env.sh
       (Windows: py -3.11 -m venv .venv; set PYTHON=.venv\\Scripts\\python.exe)"

say "[setup] Python       : $("$PYTHON_BIN" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# --------------------------------------------------------------------------- #
# 1) Optional: install a FigTreeKit checkout in editable mode
# --------------------------------------------------------------------------- #
if [ "${FIGTREEKIT_SRC:-}" != "" ]; then
    if [ ! -f "$FIGTREEKIT_SRC/pyproject.toml" ] && [ ! -f "$FIGTREEKIT_SRC/setup.py" ]; then
        fail "FIGTREEKIT_SRC does not look like a FigTreeKit checkout: $FIGTREEKIT_SRC
       Expected pyproject.toml or setup.py in that directory."
    fi
    say "[setup] Step 1/4: installing figtreekit editable (--no-deps) from FIGTREEKIT_SRC"
    "$PYTHON_BIN" -m pip install --no-deps -e "$FIGTREEKIT_SRC" || fail \
        "Could not install figtreekit from '$FIGTREEKIT_SRC'."
else
    say "[setup] Step 1/4: FIGTREEKIT_SRC not set - checking installed figtreekit"
    "$PYTHON_BIN" -c 'import figtreekit' 2>/dev/null || fail \
        "figtreekit is not importable.
       Either install it (pip install 'figtreekit>=1.1.4') or set:
         FIGTREEKIT_SRC=/path/to/FigTreeKit bash scripts/setup_env.sh"
fi

# --------------------------------------------------------------------------- #
# 2) Runtime and development dependencies
# --------------------------------------------------------------------------- #
say "[setup] Step 2/4: installing runtime dependency mcp>=1.29,<2"
"$PYTHON_BIN" -m pip install "mcp>=1.29,<2" || fail "Could not install mcp."

say "[setup] Step 3/4: installing test / render extras (pytest, hypothesis, pillow)"
"$PYTHON_BIN" -m pip install \
    "pytest>=7.5" \
    "pytest-asyncio>=0.23" \
    "hypothesis>=6.0" \
    "pytest-cov>=4.0" \
    "pytest-timeout>=2.0" \
    "pillow>=10.0" || fail "Could not install the test / render extras."

# --------------------------------------------------------------------------- #
# 3) This project (editable, --no-deps: dependencies were installed above)
# --------------------------------------------------------------------------- #
say "[setup] Step 4/4: installing figtreekit-mcp editable (--no-deps): $PROJECT_ROOT"
"$PYTHON_BIN" -m pip install --no-deps -e "$PROJECT_ROOT" || fail \
    "Could not install figtreekit-mcp from '$PROJECT_ROOT'."

# --------------------------------------------------------------------------- #
# 4) Verify
# --------------------------------------------------------------------------- #
say "[setup] Verifying imports and entry point"
"$PYTHON_BIN" - <<'PY' || exit 1
from importlib.metadata import version

import Bio  # biopython
import figtreekit
import mcp
import PIL  # pillow

print("  mcp        ", getattr(mcp, "__version__", version("mcp")))
print("  figtreekit ", figtreekit.__version__)
print("  biopython  ", Bio.__version__)
print("  pillow     ", PIL.__version__)
PY

"$PYTHON_BIN" -m figtreekit_mcp --version || fail \
    "figtreekit-mcp entry point failed. Check the editable install above."

say ""
say "[setup] Done."
say "        Start the server with:   python -m figtreekit_mcp --transport stdio --workspace-root \"$PROJECT_ROOT/figtreekit-mcp-workspace\""
say "        Run the examples with:   python examples/01_validate_and_summarize.py"
