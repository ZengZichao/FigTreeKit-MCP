# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Integration tests for environment tools (T01-T03).

These invoke the registered handlers directly through the shared ``TOOLS``
registry with a real AppContext over a temporary workspace, exercising the
in-process (non-shell) path.  ``check_figtree`` / ``setup_figtree`` may touch
the JVM, so those tests are guarded by the availability of java / the jar
unless testing the error envelope.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp.tools import environment as environment_tools
from figtreekit_mcp.tools.environment import (
    probe_java,
    probe_jar,
    render_ready,
    _java_version,
)

from conftest import SMALL_TREE  # noqa: F401  (keep import parity)


# --------------------------------------------------------------------------- #
# helper-level
# --------------------------------------------------------------------------- #
class TestJavaVersionParsing:
    def test_lts_format(self):
        assert _java_version('java version "17.0.8" 2023-07-18') == "17.x"

    def test_jdk_vendor_format(self):
        assert _java_version('openjdk version "11.0.20" 2023-07-20') == "11.x"

    def test_unknown(self):
        assert _java_version("") == "unknown"
        assert _java_version("not-a-java-version").startswith("not-a-java-version")


# --------------------------------------------------------------------------- #
# get_environment
# --------------------------------------------------------------------------- #
class TestGetEnvironment:
    def test_returns_version_block(self, call):
        res = call("get_environment")
        assert res["ok"] is True
        assert res["figtreekit_version"]
        assert res["biopython_version"]
        assert res["python_version"]
        assert res["mcp_sdk_version"]
        # Pillow may or may not be installed; must be a dict either way.
        assert isinstance(res["pillow"], dict)
        assert isinstance(res["allowed_read_roots"], list)
        assert res["workspace_root"].endswith("ws")
        assert "render_ready" in res

    def test_java_and_jar_probed(self, call):
        res = call("get_environment")
        assert res["java"]["ok"] is True  # the dev env always has Java
        assert "version" in res["java"]
        assert isinstance(res["jar"], dict)
        assert "ok" in res["jar"]

    def test_read_roots_listed(self, call, app):
        res = call("get_environment")
        assert str(app.workspace.root) in res["allowed_read_roots"]


# --------------------------------------------------------------------------- #
# probe_java / render_ready (no JAR required)
# --------------------------------------------------------------------------- #
class TestProbeJava:
    def test_java_present(self):
        info = probe_java()
        assert info["ok"] is True
        assert info["version"]

    def test_render_ready_shape(self, app):
        env = render_ready(app)
        assert set(env) == {"java", "jar", "render_ready"}


# --------------------------------------------------------------------------- #
# check_figtree (error envelope when JAR missing is acceptable)
# --------------------------------------------------------------------------- #
class TestCheckFigTree:
    def test_missing_jar_raises(self, call):
        # No JAR is configured in the fresh app → should raise ToolError
        # (or return ok:false if the environment already has a jar on disk).
        try:
            call("check_figtree")
        except ToolError as exc:
            assert exc.code in ("jar_missing", "java_missing")
        else:
            # A jar was found on disk in this environment → fine.
            pass

    def test_explicit_missing_jar_path(self, call, reads_dir):
        # A path inside the whitelisted root that does not exist → jar_missing.
        fake = str(reads_dir / "no_such.jar")
        with pytest.raises(ToolError) as ei:
            call("check_figtree", jar_path=fake)
        assert ei.value.code == "jar_missing"


# --------------------------------------------------------------------------- #
# setup_figtree (check_only path — no download side effects)
# --------------------------------------------------------------------------- #
class TestSetupFigTree:
    def test_check_only_is_passive(self, call):
        # check_only probes directly and returns a full envelope.
        res = call("setup_figtree", check_only=True)
        assert res["ok"] is True
        assert "jar_path" in res
        assert {"java_ok", "jar_ok", "render_ready", "hints"} <= set(res)

    def test_explicit_whitelisted_jar_skips_compile(
        self, call, app, reads_dir, monkeypatch
    ):
        jar = reads_dir / "custom.jar"
        jar.write_bytes(b"fake-jar")

        def _fail_setup(*a, **k):
            raise AssertionError("explicit jar must not trigger download/compile")

        monkeypatch.setattr(environment_tools._figtree_setup, "setup_figtree", _fail_setup)
        res = call("setup_figtree", jar_path=str(jar))
        assert res["ok"] is True
        assert res["jar_path"] == str(jar.resolve())
        assert any("使用已有" in line for line in res["status"])

    def test_auto_detected_jar_skips_compile(self, call, monkeypatch):
        monkeypatch.setattr(environment_tools, "probe_jar", lambda *a, **k: {
            "ok": True, "path": "/bundled/figtree.jar", "hints": []})

        def _fail_setup(*a, **k):
            raise AssertionError("bundled jar must not trigger download/compile")

        monkeypatch.setattr(environment_tools._figtree_setup, "setup_figtree", _fail_setup)
        res = call("setup_figtree")
        assert res["ok"] is True
        assert res["jar_path"] == "/bundled/figtree.jar"

    def test_explicit_jar_outside_roots_rejected(self, call, tmp_path):
        outside = tmp_path / "outside.jar"
        outside.write_bytes(b"fake-jar")
        with pytest.raises(ToolError) as ei:
            call("setup_figtree", jar_path=str(outside))
        assert ei.value.code == "access_denied"

    def test_setup_timeout_guards_compile(self, call, app, monkeypatch):
        monkeypatch.setattr(environment_tools, "probe_jar", lambda *a, **k: {
            "ok": False, "path": None, "hints": []})

        def _timeout(*a, **k):
            raise environment_tools.subprocess.TimeoutExpired(cmd="figtreekit-setup", timeout=1)

        # The installer runs in an isolated child process; simulate the
        # deadline instead of patching the library function in this process.
        monkeypatch.setattr(environment_tools.subprocess, "run", _timeout)
        app.setup_timeout = 1
        with pytest.raises(ToolError) as ei:
            call("setup_figtree")
        assert ei.value.code == "figtree_setup_failed"
        assert ei.value.error_key == "setup_timeout"


class TestProbeJarOutsideRoots:
    def test_returns_hint_instead_of_raising(self, app, tmp_path):
        app.jar_path = str(tmp_path / "outside.jar")
        info = probe_jar(app)
        assert info["ok"] is False
        assert info["path"]
        assert info["hints"]
