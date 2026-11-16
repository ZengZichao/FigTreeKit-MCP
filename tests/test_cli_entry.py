# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""CLI entry-point unit tests.

Covers all startup arguments, ``_resolve_bind_host`` policy, ``_config_from_args``,
the stdout-purity static scan and ``--self-test`` / ``--version``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from figtreekit_mcp._cli import (
    _config_from_args,
    _resolve_bind_host,
    _scan_no_stdout_print,
    create_cli_parser,
    main,
)
from figtreekit_mcp._version import __version__


def _parse(*argv: str):
    parser = create_cli_parser()
    return parser.parse_args(list(argv))


class TestParser:
    def test_transport_default(self) -> None:
        assert _parse().transport == "stdio"

    def test_transport_choices(self) -> None:
        assert _parse("--transport", "sse").transport == "sse"
        assert _parse("--transport", "http").transport == "http"
        with pytest.raises(SystemExit) as ei:
            _parse("--transport", "udp")
        assert ei.value.code == 2

    def test_host_port_defaults(self) -> None:
        args = _parse()
        assert args.host == "127.0.0.1"
        assert args.port == 8777

    def test_port_positive(self) -> None:
        with pytest.raises(SystemExit):
            _parse("--port", "0")

    def test_read_roots_repeatable(self) -> None:
        args = _parse("--allow-read-root", "/a", "--allow-read-root", "/b")
        assert args.allow_read_root == ["/a", "/b"]

    def test_timeouts_and_limits(self) -> None:
        args = _parse(
            "--cli-timeout",
            "10",
            "--render-timeout",
            "20",
            "--content-max-bytes",
            "1024",
            "--file-max-bytes",
            "2048",
            "--keep-runs",
            "3",
        )
        assert args.cli_timeout == 10
        assert args.render_timeout == 20
        assert args.content_max_bytes == 1024
        assert args.file_max_bytes == 2048
        assert args.keep_runs == 3

    def test_verbose_quiet_mutually_configured(self) -> None:
        assert _parse("-v").verbose == 1
        assert _parse("-vv").verbose == 2
        assert _parse("-q").quiet is True

    def test_log_file(self) -> None:
        assert _parse("--log-file", "/tmp/x.log").log_file == "/tmp/x.log"

    def test_jar_flag(self) -> None:
        assert _parse("--jar", "/j/fig.jar").jar == "/j/fig.jar"

    def test_self_test_flag(self) -> None:
        assert _parse("--self-test").self_test is True

    def test_workspace_root(self) -> None:
        assert _parse("--workspace-root", "/ws").workspace_root == "/ws"


class TestBindHost:
    def test_loopback_allowed(self) -> None:
        assert _resolve_bind_host("127.0.0.1", False) == "127.0.0.1"
        assert _resolve_bind_host("::1", False) == "::1"
        assert _resolve_bind_host("localhost", False) == "localhost"

    def test_non_loopback_requires_flag(self) -> None:
        with pytest.raises(SystemExit) as ei:
            _resolve_bind_host("0.0.0.0", False)
        assert ei.value.code == 2

    def test_allow_remote(self) -> None:
        assert _resolve_bind_host("0.0.0.0", True) == "0.0.0.0"


class TestConfigFromArgs:
    def test_default_workspace_is_cwd(self, monkeypatch) -> None:
        monkeypatch.chdir(Path("/tmp"))
        cfg = _config_from_args(_parse())
        assert cfg["workspace_root"].endswith("figtreekit-mcp-workspace")
        assert cfg["read_roots"] == []
        assert cfg["jar"] is None
        assert cfg["keep_runs"] == 50
        assert cfg["cli_timeout"] == 300
        assert cfg["render_timeout"] == 180

    def test_explicit_config(self) -> None:
        cfg = _config_from_args(
            _parse(
                "--workspace-root",
                "/ws",
                "--allow-read-root",
                "/r",
                "--jar",
                "/j.jar",
                "--keep-runs",
                "2",
                "--cli-timeout",
                "10",
            )
        )
        assert cfg["workspace_root"] == "/ws"
        assert cfg["read_roots"] == ["/r"]
        assert cfg["jar"] == "/j.jar"
        assert cfg["keep_runs"] == 2
        assert cfg["cli_timeout"] == 10


class TestStdoutPurity:
    def test_scan_finds_no_bare_print(self) -> None:
        src = Path(__file__).resolve().parent.parent / "src" / "figtreekit_mcp"
        issues = _scan_no_stdout_print(src)
        assert issues == [], f"found stdout prints: {issues}"

    def test_scan_ignores_hidden_binary_and_pycache_junk(self, tmp_path: Path) -> None:
        """AppleDouble ``._*.py`` junk and ``__pycache__`` are not Python source."""
        # Binary hidden files must not crash the strict UTF-8 decode.
        (tmp_path / "._binary.py").write_bytes(b"\x00\x01\xfe\xff\x80not-text")
        (tmp_path / ".___init__.py").write_bytes(b"\x00\x01\xffbinary")
        cache = tmp_path / "pkg" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "junk.py").write_bytes(b"\xff\xfe")
        (tmp_path / "pkg" / "ok.py").write_text("value = 1\n", encoding="utf-8")
        (tmp_path / "pkg" / "bad.py").write_text("print('oops')\n", encoding="utf-8")

        issues = _scan_no_stdout_print(tmp_path)
        assert len(issues) == 1
        assert "bad.py" in issues[0]


class TestMain:
    def test_version_flag(self, capsys) -> None:
        with pytest.raises(SystemExit) as ei:
            main(["--version"])
        assert ei.value.code == 0
        assert capsys.readouterr().out.strip() == f"figtreekit-mcp {__version__}"
        assert __version__ == "0.1.0"

    def test_self_test_exits_zero(self, tmp_path: Path) -> None:
        rc = main(["--self-test", "--workspace-root", str(tmp_path / "ws")])
        assert rc == 0

    def test_self_test_prints_pass_table(self, tmp_path: Path, capsys) -> None:
        main(["--self-test", "--workspace-root", str(tmp_path / "ws2")])
        out = capsys.readouterr().out
        assert "ALL PASS" in out

    def test_self_test_warns_when_java_and_jar_missing(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        """Absent Java/render is a WARN, never a self-test failure."""
        from figtreekit_mcp.tools import environment

        monkeypatch.setattr(
            environment,
            "probe_java",
            lambda: {"ok": False, "version": "", "message": "java missing", "hints": []},
        )
        monkeypatch.setattr(
            environment,
            "probe_jar",
            lambda app, jar_path=None: {"ok": False, "path": None, "hints": []},
        )
        rc = main(["--self-test", "--workspace-root", str(tmp_path / "ws")])
        out = capsys.readouterr().out
        assert rc == 0
        assert "[WARN]" in out
        assert "ALL PASS" in out

    def test_real_cli_self_test_exits_zero_under_temp(self) -> None:
        """The console entry point works with a workspace under %TEMP%."""
        workspace = Path(tempfile.mkdtemp(prefix="figmcp-selftest-"))
        try:
            src = Path(__file__).resolve().parent.parent / "src"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "figtreekit_mcp",
                    "--self-test",
                    "--workspace-root",
                    str(workspace),
                ],
                capture_output=True,
                text=True,
                timeout=240,
                env=env,
            )
            assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            assert "ALL PASS" in proc.stdout
        finally:
            import shutil

            shutil.rmtree(workspace, ignore_errors=True)

    def test_bad_args_usage_error(self) -> None:
        with pytest.raises(SystemExit) as ei:
            main(["--transport", "bogus"])
        assert ei.value.code == 2

    def test_non_loopback_rejected(self) -> None:
        with pytest.raises(SystemExit):
            main(["--host", "0.0.0.0", "--port", "8000"])

    def test_invalid_positive(self) -> None:
        with pytest.raises(SystemExit):
            main(["--port", "-1"])
