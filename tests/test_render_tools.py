# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Integration tests for render tool (T20) and environment JAR detection.

Actual JVM rendering requires a figtree_patched.jar and Java; tests that need
them are skipped when unavailable, while input-validation error envelopes and
the JAR-detection probes always run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp.tools import render as render_tools
from figtreekit_mcp.tools.environment import probe_java, probe_jar

from conftest import SMALL_TREE, call_app


def _java_ready() -> bool:
    return probe_java()["ok"]


def _fake_render_deps(monkeypatch, jar: str = "fake.jar") -> None:
    """Patch dependency probes so validation/output tests need no JVM."""
    monkeypatch.setattr(
        render_tools,
        "probe_java",
        lambda: {"ok": True, "version": "17.x", "message": "", "hints": []},
    )
    monkeypatch.setattr(
        render_tools, "probe_jar", lambda *a, **k: {"ok": True, "path": jar, "hints": []}
    )


def _fake_render(monkeypatch, captured: dict) -> None:
    def fake_render(input_file, output_file, **kwargs):
        captured.update(kwargs)
        Path(output_file).write_bytes(b"fake-png")
        return True

    monkeypatch.setattr(render_tools.figtreekit, "render_with_figtree", fake_render)


# --------------------------------------------------------------------------- #
# input-validation (no JAR needed — error envelopes)
# --------------------------------------------------------------------------- #
class TestRenderTreeValidation:
    def test_missing_input(self, call):
        with pytest.raises(ToolError) as ei:
            call("render_tree")
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "missing_render_input"

    def test_bad_format(self, call):
        with pytest.raises(ToolError) as ei:
            call("render_tree", tree_content=SMALL_TREE, format="GIF")
        assert ei.value.code == "render_bad_format"
        assert ei.value.error_key == "bad_render_format"

    def test_bad_size(self, call):
        with pytest.raises(ToolError) as ei:
            call("render_tree", tree_content=SMALL_TREE, width=0)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_render_size"

    def test_bad_timeout(self, call):
        with pytest.raises(ToolError) as ei:
            call("render_tree", tree_content=SMALL_TREE, timeout=0)
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "bad_render_timeout"


# --------------------------------------------------------------------------- #
# output metadata / validation without a JVM
# --------------------------------------------------------------------------- #
class TestRenderOutputMetadata:
    def test_directory_nexus_file_clean_error(self, app, ctx, reads_dir, monkeypatch):
        _fake_render_deps(monkeypatch)
        with pytest.raises(ToolError) as ei:
            call_app("render_tree", ctx, nexus_file=str(reads_dir))
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "nexus_not_a_file"

    def test_cli_command_and_config(self, app, ctx, monkeypatch):
        _fake_render_deps(monkeypatch)
        app.render_timeout = 321
        captured: dict = {}
        _fake_render(monkeypatch, captured)
        res = call_app(
            "render_tree", ctx, tree_content=SMALL_TREE, format="PNG", width=600, height=400
        )
        cmd = res["cli_command"]
        assert "--figtree-jar" in cmd
        assert " --render " in cmd
        assert " --render-format PNG" in cmd
        assert " --render-width 600" in cmd
        assert " --render-height 400" in cmd
        assert " --jar " not in cmd
        assert "command" not in res
        config = json.loads(res["config_json"])
        assert config["format"] == "PNG"
        assert config["width"] == 600
        assert config["height"] == 400
        assert config["jar"] == "fake.jar"
        assert res["reproducible"] is True
        assert res["warnings"] == []
        assert captured["timeout"] == 321

    def test_colour_post_processing_not_reproducible(self, app, ctx, monkeypatch):
        _fake_render_deps(monkeypatch)
        _fake_render(monkeypatch, {})
        res = call_app("render_tree", ctx, tree_content=SMALL_TREE, background_color="#FFFFFF")
        assert res["ok"] is True
        assert res["reproducible"] is False
        assert res["warnings"]
        assert json.loads(res["config_json"])["colors"]["background_color"] == "#FFFFFF"

    def test_explicit_timeout_is_used(self, app, ctx, monkeypatch):
        _fake_render_deps(monkeypatch)
        captured: dict = {}
        _fake_render(monkeypatch, captured)
        call_app("render_tree", ctx, tree_content=SMALL_TREE, timeout=42)
        assert captured["timeout"] == 42


# --------------------------------------------------------------------------- #
# dependency-gated real rendering
# --------------------------------------------------------------------------- #
class TestRenderTreeReal:
    @pytest.mark.skipif(not _java_ready(), reason="Java 不可用，跳过真实渲染")
    def test_render_png(self, call, app):
        # If no jar is available this raises jar_missing; otherwise renders.
        try:
            res = call("render_tree", tree_content=SMALL_TREE, format="PNG", width=600, height=400)
        except ToolError as exc:
            assert exc.code == "jar_missing"
            return
        assert res["ok"] is True
        assert res["format"] == "PNG"
        assert res["image"]["relative"].endswith("output.png")
        # data_uri preview is present for small PNGs.
        assert res["image"]["data_uri"] and res["image"]["data_uri"].startswith("data:image/png")

    @pytest.mark.skipif(not _java_ready(), reason="Java 不可用，跳过真实渲染")
    def test_render_svg(self, call, app):
        try:
            res = call("render_tree", tree_content=SMALL_TREE, format="SVG", width=600, height=400)
        except ToolError as exc:
            assert exc.code == "jar_missing"
            return
        assert res["ok"] is True
        assert res["image"]["relative"].endswith("output.svg")


# --------------------------------------------------------------------------- #
# JAR detection probes (no JVM needed)
# --------------------------------------------------------------------------- #
class TestJarProbe:
    def test_probe_jar_shape(self, app):
        info = probe_jar(app)
        assert "ok" in info
        assert "path" in info
        assert isinstance(info["hints"], list)

    def test_probe_jar_missing_explicit(self, app, reads_dir):
        # Path inside the whitelisted root that does not exist → ok:false.
        info = probe_jar(app, jar_path=str(reads_dir / "nope.jar"))
        assert info["ok"] is False
        assert "hints" in info
