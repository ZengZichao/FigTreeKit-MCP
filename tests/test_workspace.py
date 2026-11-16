# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Workspace / whitelist unit tests (SEC-1/2/3).

Covers canonicalisation, symlink-escape rejection, ``run_<uuid8>``
uniqueness, artifact registration and the keep-N cleanup policy.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp._workspace import (
    RunStorage,
    Workspace,
    assert_within_roots,
    resolve_root,
)


# --------------------------------------------------------------------------- #
# resolve_root / assert_within_roots
# --------------------------------------------------------------------------- #
class TestRootResolution:
    def test_resolve_root_creates(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b"
        root = resolve_root(target)
        assert root.is_dir()
        assert root.is_absolute()

    def test_assert_within_roots_ok(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        f = root / "x.tree"
        f.write_text("();", encoding="utf-8")
        resolved = assert_within_roots(f, [root])
        assert resolved == f

    def test_assert_rejects_outside(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        outside = tmp_path / "secret.txt"
        outside.write_text("s", encoding="utf-8")
        with pytest.raises(ToolError) as ei:
            assert_within_roots(outside, [root])
        assert ei.value.code == "access_denied"
        assert "白名单" in ei.value.error

    def test_assert_rejects_parent_tokens(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        with pytest.raises(ToolError) as ei:
            assert_within_roots(str(tmp_path / ".." / "etc" / "passwd"), [root])
        assert ei.value.error_key == "path_traversal"

    def test_assert_rejects_symlink_escape(self, tmp_path: Path) -> None:
        """SEC-2: a symlink inside the root pointing outside is rejected."""
        root = resolve_root(tmp_path / "ws")
        victim = tmp_path / "target.txt"
        victim.write_text("data", encoding="utf-8")
        link = root / "escape.tre"
        link.symlink_to(victim)
        with pytest.raises(ToolError) as ei:
            assert_within_roots(link, [root])
        assert ei.value.code == "access_denied"

    def test_assert_writable_parent_must_exist(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        missing = root / "no_such_dir" / "out.nex"
        with pytest.raises(ToolError):
            assert_within_roots(missing, [root], writable=True)

    def test_assert_writable_ok_in_existing_dir(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        sub = root / "run_x"
        sub.mkdir()
        target = sub / "out.nex"
        assert assert_within_roots(target, [root], writable=True) == target

    def test_relative_path_requires_base(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        with pytest.raises(ToolError):
            assert_within_roots("elsewhere/file", [root])

    def test_relative_path_resolved_via_base(self, tmp_path: Path) -> None:
        root = resolve_root(tmp_path / "ws")
        target = root / "rel.tre"
        target.write_text("();", encoding="utf-8")
        resolved = assert_within_roots("rel.tre", [root], base_dir=root)
        assert resolved == target

    def test_no_roots_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ToolError) as ei:
            assert_within_roots(tmp_path / "x", [])
        assert ei.value.error_key == "no_roots"


# --------------------------------------------------------------------------- #
# Workspace high-level API
# --------------------------------------------------------------------------- #
class TestWorkspace:
    def test_read_roots_include_writable_root(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        assert ws.root in ws.read_roots
        assert ws.read_roots[0] == ws.root

    def test_assert_readable_read_root(self, tmp_path: Path) -> None:
        read = tmp_path / "reads"
        read.mkdir()
        f = read / "in.tre"
        f.write_text("();", encoding="utf-8")
        ws = Workspace(tmp_path / "ws", [read])
        assert ws.assert_readable(f) == f
        with pytest.raises(ToolError):
            ws.assert_readable(tmp_path / "outside.tre")

    def test_check_file_size_limit(self, tmp_path: Path) -> None:
        read = tmp_path / "reads"
        read.mkdir()
        f = read / "big.tre"
        f.write_text("x" * 100, encoding="utf-8")
        ws = Workspace(tmp_path / "ws", [read], file_max_bytes=50)
        with pytest.raises(ToolError) as ei:
            ws.check_file_size(f)
        assert ei.value.code == "input_too_large"

    def test_check_content_size_limit(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", content_max_bytes=100)
        with pytest.raises(ToolError) as ei:
            ws.check_content_size("y" * 101)
        assert ei.value.code == "input_too_large"
        ws.check_content_size("y" * 100)

    def test_new_run_unique(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        a = ws.new_run()
        b = ws.new_run()
        assert a.name != b.name
        assert a.name.startswith("run_")
        assert len(a.name) == len("run_") + 8
        assert a.run_dir.is_dir() and b.run_dir.is_dir()

    def test_cleanup_keeps_recent_n(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", keep_runs=3)
        runs = [ws.new_run() for _ in range(5)]
        # mtime tie-break: force distinct, ordered mtimes
        for i, r in enumerate(runs):
            os.utime(r.run_dir, (1000 + i, 1000 + i))
        removed = ws.cleanup()
        assert removed == 2
        remaining = sorted(p.name for p in ws.root.glob("run_*"))
        assert len(remaining) == 3
        assert remaining == sorted(r.name for r in runs[-3:])

    def test_cleanup_removes_all_when_zero(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", keep_runs=0)
        for _ in range(2):
            ws.new_run()
        assert ws.cleanup() == 2
        assert list(ws.root.glob("run_*")) == []

    def test_cleanup_older_than(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        ws.new_run()
        # newest run has future mtime → survives an age-based sweep
        removed = ws.cleanup_older_than(age_seconds=3600)
        assert removed == 0
        assert len(list(ws.root.glob("run_*"))) == 1


# --------------------------------------------------------------------------- #
# RunStorage
# --------------------------------------------------------------------------- #
class TestRunStorage:
    def test_file_path_rejects_traversal(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        run = ws.new_run()
        with pytest.raises(ToolError) as ei:
            run.file_path("../../evil.nex")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_run_name"

    def test_file_path_accepts_nexus(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        run = ws.new_run()
        assert run.file_path("output.nex").name == "output.nex"

    def test_register_png_data_uri_and_dims(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        run = ws.new_run()
        png = run.run_dir / "out.png"
        # 1x1 red PNG (smallest valid file)
        import base64

        png.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
            )
        )
        entry = run.register(png)
        assert entry["data_uri"].startswith("data:image/png;base64,")
        assert entry["mime"] == "image/png"
        assert entry["width"] == 1 and entry["height"] == 1
        assert entry["size_bytes"] > 0

    def test_register_nexus_no_data_uri(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        run = ws.new_run()
        nex = run.run_dir / "out.nex"
        nex.write_text("#NEXUS\nbegin trees;\nend;\n", encoding="utf-8")
        entry = run.register(nex)
        assert entry["data_uri"] is None
        assert entry["mime"] is None

    def test_register_rejects_outside(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        run = ws.new_run()
        with pytest.raises(ToolError):
            run.register(tmp_path / "outside.nex")

    def test_keep_runs_constructor_default(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws")
        assert ws.keep_runs == 50
        assert ws.content_max_bytes == 10 * 1024 * 1024
        assert ws.file_max_bytes == 200 * 1024 * 1024


def test_runstorage_module_constants() -> None:
    """Smoke: the module still exposes the pieces the tools import."""
    from figtreekit_mcp import _workspace as w

    assert callable(w.resolve_root)
    assert callable(w.assert_within_roots)
    assert w.RunStorage is RunStorage
