# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Security tests: SEC-1 … SEC-12.

Automates the full whitelist / shell / content / DoS / concurrency / timeout
matrix against the real handlers (in-process, where structured error envelopes
are observable).  Some cases double-cover unit suites; they are consolidated
here as the SEC acceptance gate (AC-9).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, List

import pytest

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp.tools import TOOLS
from figtreekit_mcp.tools import render as render_tools

from conftest import SMALL_TREE, _fake_ctx, call_app

BIG_CONTENT = "x" * (11 * 1024 * 1024)  # 11 MiB > 10 MiB default


# --------------------------------------------------------------------------- #
# SEC-1 / SEC-2 / SEC-3 : file access control
# --------------------------------------------------------------------------- #
class TestAccessControl:
    def test_sec1_traversal_tree_file_denied(self, app: Any, ctx: Any) -> None:
        """SEC-1: ``../../../../etc/passwd`` is rejected as outside the root."""
        with pytest.raises(ToolError) as ei:
            call_app("summarize_tree", ctx, tree_file="../../../../etc/passwd")
        assert ei.value.code == "access_denied"
        assert ei.value.error_key in ("path_traversal", "outside_roots")

    def test_sec2_symlink_escape_denied(self, tmp_path: Path, app: Any, ctx: Any) -> None:
        """SEC-2: a symlink inside a read root pointing outside is rejected."""
        read_root = tmp_path / "reads"
        read_root.mkdir(parents=True, exist_ok=True)
        victim = tmp_path / "secret.tre"
        victim.write_text("((A:1,B:1):1,C:2);", encoding="utf-8")
        link = read_root / "innocent.tre"
        link.symlink_to(victim)
        with pytest.raises(ToolError) as ei:
            call_app("summarize_tree", ctx, tree_file=str(link))
        assert ei.value.code == "access_denied"

    def test_sec3_run_name_traversal(self, app: Any, ctx: Any) -> None:
        """SEC-3: ``run_name="../../evil"`` is invalid_argument (write clamp)."""
        with pytest.raises(ToolError) as ei:
            call_app("style_tree", ctx, tree_content=SMALL_TREE, run_name="../../evil")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "param_validation_failed"


# --------------------------------------------------------------------------- #
# SEC-4 / SEC-7 : output rewrite + zero shell
# --------------------------------------------------------------------------- #
class TestOutputRewriteAndShell:
    def test_sec4_output_rewritten_into_run(self, app: Any, ctx: Any) -> None:
        """SEC-4: ``-o /tmp/x.nex`` is rewritten into the run dir and disclosed."""
        res = call_app(
            "run_figtreekit_cli",
            ctx,
            argv=["<input>", "--layout", "polar", "-o", "/tmp/x.nex", "--force"],
            tree_content=SMALL_TREE,
        )
        assert res["ok"] is True
        rewrites = res["rewrites"]
        assert rewrites, "rewrites must be non-empty"
        assert any("/tmp/x.nex" in d for d in rewrites)
        # The produced artifact lives under the workspace, never /tmp.
        for a in res["artifacts"]:
            assert "run_" in a["relative"]

    def test_sec4_relative_escape_contained(self, app: Any, ctx: Any, tmp_path: Path) -> None:
        """SEC-4: ``-o ../../escaped.nex`` cannot write outside the workspace."""
        res = call_app(
            "run_figtreekit_cli",
            ctx,
            argv=["<input>", "--layout", "polar", "-o", "../../escaped.nex", "--force"],
            tree_content=SMALL_TREE,
        )
        assert res["ok"] is True
        assert res["rewrites"], "rewrites must be disclosed"
        assert not (tmp_path / "escaped.nex").exists()
        run_dir = app.workspace.root / res["run_dir"]
        assert (run_dir / "escaped.nex").is_file()

    def test_sec7_metachars_never_executed(self, app: Any, ctx: Any) -> None:
        """SEC-7: ``;`` / ``$(...)`` / ``|`` are literal argv, no shell runs."""
        marker = "/tmp/figtreekit-mcp-sec7-marker"
        if Path(marker).exists():
            Path(marker).unlink()
        for evil in (
            "; touch " + marker,
            "$(touch " + marker + ")",
            "|touch " + marker,
            "&&touch " + marker,
        ):
            try:
                call_app(
                    "run_figtreekit_cli",
                    ctx,
                    argv=["<input>", "--layout", "polar", "-o", "/tmp/x.nex", "--force", evil],
                    tree_content=SMALL_TREE,
                )
            except ToolError:
                pass
        assert not Path(marker).exists(), "shell metacharacters executed!"


# --------------------------------------------------------------------------- #
# SEC-5 / SEC-6 : content safety + size limits
# --------------------------------------------------------------------------- #
class TestContentSafety:
    def test_sec5_null_and_bidi_rejected(self, app: Any, ctx: Any) -> None:
        """SEC-5: control char ``\\x00`` and bidi override ``\\u202E``."""
        for evil in ("(((A:1,B:1):1,C:2)\x00);", "((A:1,B:1)\u202e);"):
            with pytest.raises(ToolError) as ei:
                call_app("validate_tree", ctx, tree_content=evil)
            assert ei.value.code == "anomalous_content"
            assert ei.value.error_key == "anomalous_content_found"

    def test_sec6_content_too_large(self, app: Any, ctx: Any) -> None:
        """SEC-6: 11 MiB tree_content → input_too_large."""
        with pytest.raises(ToolError) as ei:
            call_app("validate_tree", ctx, tree_content=BIG_CONTENT)
        assert ei.value.code == "input_too_large"


# --------------------------------------------------------------------------- #
# SEC-8 : concurrency (8 style_tree + 2 run_cli)
# --------------------------------------------------------------------------- #
class TestConcurrency:
    def test_sec8_concurrent_isolation(self, app: Any) -> None:
        results: List[Any] = []
        lock = threading.Lock()

        def style_work() -> None:
            try:
                ctx = _fake_ctx(app)
                res = call_app(
                    "style_tree",
                    ctx,
                    tree_content=SMALL_TREE,
                    layout="polar",
                    operations=[{"op": "highlight", "taxa": ["A", "B"], "color": "#FF0000"}],
                )
                with lock:
                    results.append(res)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    results.append(exc)

        def cli_work() -> None:
            try:
                ctx = _fake_ctx(app)
                res = call_app("run_figtreekit_cli", ctx, argv=["--help"])
                with lock:
                    results.append(res)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    results.append(exc)

        threads = [threading.Thread(target=style_work) for _ in range(8)]
        threads += [threading.Thread(target=cli_work) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        for r in results:
            assert not isinstance(r, Exception)
            assert r.get("ok") is True
        # Every call got its own run dir (no artifact interleaving).
        run_dirs = [r["run_dir"] for r in results]
        assert len(set(run_dirs)) == 10


# --------------------------------------------------------------------------- #
# SEC-9 / SEC-10 / SEC-11 : render timeout + dependency guidance
# --------------------------------------------------------------------------- #
class TestRenderDependencies:
    def test_sec10_no_java_gives_java_missing(self, app: Any, ctx: Any, monkeypatch: Any) -> None:
        """SEC-10: probe_java reports missing → java_missing guidance."""
        # Patch the names *bound inside* render.py (imported at module load).
        monkeypatch.setattr(
            render_tools,
            "probe_java",
            lambda: {
                "ok": False,
                "version": "",
                "message": "java not found",
                "hints": ["Java 8+ 未安装。请安装 JDK/JRE 8+。"],
            },
        )
        with pytest.raises(ToolError) as ei:
            call_app("render_tree", ctx, tree_content=SMALL_TREE, format="PNG")
        assert ei.value.code == "java_missing"
        assert "Java" in ei.value.error

    def test_sec11_no_jar_gives_jar_missing(self, app: Any, ctx: Any, monkeypatch: Any) -> None:
        """SEC-11: java present but JAR missing → jar_missing + setup hint."""
        monkeypatch.setattr(
            render_tools,
            "probe_java",
            lambda: {"ok": True, "version": "8.x", "message": "", "hints": []},
        )
        monkeypatch.setattr(
            render_tools,
            "probe_jar",
            lambda *a, **k: {
                "ok": False,
                "path": None,
                "hints": ["figtree_patched.jar 未找到。运行 setup_figtree 安装。"],
            },
        )
        with pytest.raises(ToolError) as ei:
            call_app("render_tree", ctx, tree_content=SMALL_TREE, format="PNG")
        assert ei.value.code == "jar_missing"
        assert "setup_figtree" in ei.value.error_detail or "setup_figtree" in ei.value.error

    @pytest.mark.slow
    def test_sec9_render_timeout(self, app: Any, ctx: Any, monkeypatch: Any) -> None:
        """SEC-9: a JVM render that overruns its budget → render_timeout.

        A real JVM is required; if the environment lacks Java+JAR the test is
        skipped rather than failed (dependency-guidance path already covered by
        SEC-10/11).
        """
        from figtreekit_mcp.tools.environment import render_ready

        probe = render_ready(app)
        if not probe["render_ready"]:
            pytest.skip("渲染依赖缺失，跳过 SEC-9 渲染超时映射")
        # A 300x200 render can legitimately finish inside one second, so a real
        # JVM subprocess makes this assertion timing-dependent.  Exercise the
        # deterministic error mapping instead: the library's timeout message
        # must become render_timeout (the JVM's own timeout is covered by the
        # library test suite).
        import figtreekit

        import figtreekit_mcp.tools.render as render_mod

        def _timeout(*_a: Any, **_k: Any) -> None:
            raise figtreekit.RenderError("FigTree rendering timed out after 1 seconds")

        monkeypatch.setattr(render_mod.figtreekit, "render_with_figtree", _timeout)
        with pytest.raises(ToolError) as ei:
            call_app(
                "render_tree",
                ctx,
                tree_content=SMALL_TREE,
                format="PNG",
                width=300,
                height=200,
                timeout=1,
            )
        assert ei.value.code == "render_timeout"


# --------------------------------------------------------------------------- #
# SEC-12 : stdout purity (static scan)
# --------------------------------------------------------------------------- #
def test_sec12_no_bare_print_in_src() -> None:
    """SEC-12: no bare ``print(`` writing to MCP stdout in package source."""
    from figtreekit_mcp._cli import _scan_no_stdout_print

    src = Path(__file__).resolve().parent.parent / "src" / "figtreekit_mcp"
    issues = _scan_no_stdout_print(src)
    assert not issues, f"stdout pollution: {issues}"


# --------------------------------------------------------------------------- #
# Cross-cutting: every tool handler returns an envelope on unexpected input
# --------------------------------------------------------------------------- #
def test_all_tools_are_callable() -> None:
    for name in TOOLS:
        assert callable(TOOLS[name])
