# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Regression tests for workspace hardening (path components, cleanup)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp._workspace import Workspace


@pytest.fixture()
def ws(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "ws")


def test_file_path_rejects_dot_components(ws: Workspace) -> None:
    run = ws.new_run()
    for bad in (".", "..", "../../evil.nex", "..\\evil.nex", "name."):
        with pytest.raises(ToolError) as ei:
            run.file_path(bad)
        assert ei.value.error_key == "bad_run_name"


@pytest.mark.skipif(os.name != "nt", reason="Windows reserved device names")
def test_file_path_rejects_windows_device_names(ws: Workspace) -> None:
    run = ws.new_run()
    for bad in ("CON", "NUL", "COM1", "LPT9.txt"):
        with pytest.raises(ToolError) as ei:
            run.file_path(bad)
        assert ei.value.error_key == "bad_run_name"


@pytest.mark.skipif(os.name != "nt", reason="Windows drive-relative semantics")
def test_assert_readable_rejects_drive_relative(ws: Workspace) -> None:
    with pytest.raises(ToolError) as ei:
        ws.assert_readable("C:relative.txt")
    assert ei.value.error_key == "drive_relative_path"


def test_cleanup_unlinks_symlink_without_touching_target(
    ws: Workspace, tmp_path: Path
) -> None:
    run = ws.new_run()
    target = tmp_path / "outside"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    link = ws.root / "run_symlink"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    ws.keep_runs = 0
    ws.cleanup()
    assert not link.exists()
    assert marker.read_text(encoding="utf-8") == "keep"
    assert run.run_dir.exists() is False
