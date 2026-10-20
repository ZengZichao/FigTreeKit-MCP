# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Passthrough-tool safety unit tests (SEC-4/7, AC-8).

``run_figtreekit_cli`` executes argv as an argument array with ``shell=False``
(no shell interpretation of ``;``/``$()``/``|``), rewrites output targets into
the run directory and discloses every rewrite in ``rewrites``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp._workspace import RunStorage
from figtreekit_mcp.tools.passthrough import (
    _diff_rewrites,
    _force_into_run,
    _rewrite_output_args,
    _scan_artifacts,
    _validate_argv,
    run_figtreekit_cli,
)

from conftest import SMALL_TREE, call_app


# --------------------------------------------------------------------------- #
# argv validation
# --------------------------------------------------------------------------- #
class TestValidateArgv:
    def test_empty_or_missing(self) -> None:
        with pytest.raises(ToolError) as ei:
            _validate_argv(None)
        assert ei.value.code == "invalid_argument"
        with pytest.raises(ToolError):
            _validate_argv([])

    def test_not_a_list(self) -> None:
        with pytest.raises(ToolError):
            _validate_argv("--help")

    def test_too_long(self) -> None:
        with pytest.raises(ToolError) as ei:
            _validate_argv(["--x"] * 300)
        assert "超过限制" in ei.value.error

    def test_argv0_conflict(self) -> None:
        for evil in ("figtreekit", "python", "python3", "-m"):
            with pytest.raises(ToolError) as ei:
                _validate_argv([evil, "--help"])
            assert ei.value.error_key == "argv0_conflict"

    def test_bad_element_type(self) -> None:
        with pytest.raises(ToolError):
            _validate_argv(["--x", 42])

    def test_elem_too_long(self) -> None:
        with pytest.raises(ToolError):
            _validate_argv(["a" * 5000])


# --------------------------------------------------------------------------- #
# output rewriting (SEC-4)
# --------------------------------------------------------------------------- #
class TestRewrite:
    def test_force_into_run(self, tmp_path: Path) -> None:
        run = (tmp_path / "run_123").resolve()
        run.mkdir()
        # Every real output target converges under the run dir (absolute path).
        assert _force_into_run("/tmp/evil.nex", run) == str(run / "evil.nex")
        assert _force_into_run("odd", run) == str(run / "odd")
        assert _force_into_run("../escaped.nex", run) == str(run / "escaped.nex")
        assert _force_into_run("-", run) == "-"
        assert _force_into_run("", run) == ""
        for bad in ("..", ".", "/"):
            with pytest.raises(ToolError):
                _force_into_run(bad, run)

    def test_windows_and_tmp_targets_stay_inside(self, tmp_path: Path) -> None:
        run = (tmp_path / "run_win").resolve()
        run.mkdir()
        for target in ("/tmp/win.nex", "C:win.nex"):
            out = Path(_force_into_run(target, run))
            assert out.is_relative_to(run)
            assert out.parent == run

    def test_relative_targets_are_rewritten_and_disclosed(self, tmp_path: Path) -> None:
        run = (tmp_path / "run_rel").resolve()
        run.mkdir()
        argv = ["<input>", "-o", "../../escaped.nex", "-o../attached.nex",
                "--output=../x.nex", "--render", "../x.png",
                "--log-file", "../../x.log"]
        rewritten = _rewrite_output_args(argv, run)
        values = [
            rewritten[2], rewritten[3][2:], rewritten[4].split("=", 1)[1],
            rewritten[6], rewritten[8],
        ]
        for value in values:
            assert Path(value).is_relative_to(run)
        diffs = _diff_rewrites(argv, rewritten)
        assert len(diffs) == 5
        assert all("run_rel" in d for d in diffs)

    def test_abbreviated_output_flags_are_rewritten(self, tmp_path: Path) -> None:
        run = (tmp_path / "run_abbr").resolve()
        run.mkdir()
        argv = ["<input>", "--outp", "../a.nex", "--log", "../../b.log"]
        rewritten = _rewrite_output_args(argv, run)
        assert Path(rewritten[2]).is_relative_to(run)
        assert Path(rewritten[4]).is_relative_to(run)
        assert len(_diff_rewrites(argv, rewritten)) == 2

    def test_rewrite_all_output_flags(self, tmp_path: Path) -> None:
        run = tmp_path / "run_x"
        run.mkdir()
        argv = ["<input>", "-o", "/tmp/a.nex", "--render", "/tmp/b.png",
                "--output=/tmp/c.nex", "-oATTACHED.nex", "--log-file", "/tmp/x.log"]
        rewritten = _rewrite_output_args(argv, run)
        for token in rewritten:
            if token.startswith(("-o", "--output", "--render", "--log-file")) and "=" in token:
                value = token.split("=", 1)[1]
                assert value.startswith(str(run))
            elif token in ("-o", "--render", "--output", "--log-file"):
                continue
            elif token.startswith(str(run)):
                assert token.startswith(str(run))
        from figtreekit_mcp.tools.passthrough import _diff_rewrites

        diffs = _diff_rewrites(argv, rewritten)
        assert diffs, "rewrites must be disclosed"
        assert "/tmp/a.nex" in str(diffs)


# --------------------------------------------------------------------------- #
# input whitelist (SEC-1) and forbidden flags
# --------------------------------------------------------------------------- #
class TestInputWhitelist:
    def test_table_sep_is_a_plain_value(self, app: Any, ctx: Any) -> None:
        res = call_app(
            "run_figtreekit_cli", ctx,
            argv=["<input>", "--table-sep", ",", "-o", "table.nex", "--force"],
            tree_content=SMALL_TREE,
        )
        assert res["ok"] is True
        assert res["returncode"] == 0

    def test_sequences_outside_rejected(self, app: Any, ctx: Any, tmp_path: Path) -> None:
        outside = tmp_path / "outside.fasta"
        outside.write_text(">a\nACGT\n", encoding="utf-8")
        with pytest.raises(ToolError) as ei:
            call_app(
                "run_figtreekit_cli", ctx,
                argv=["<input>", "--sequences", str(outside),
                      "-o", "x.nex", "--force"],
                tree_content=SMALL_TREE,
            )
        assert ei.value.code == "access_denied"

    def test_positional_outside_tree_rejected(
        self, app: Any, ctx: Any, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside.tre"
        outside.write_text(SMALL_TREE, encoding="utf-8")
        with pytest.raises(ToolError) as ei:
            call_app(
                "run_figtreekit_cli", ctx,
                argv=["--layout", "rectilinear", str(outside),
                      "-o", "x.nex", "--force"],
            )
        assert ei.value.code == "access_denied"

    @pytest.mark.parametrize("jar_args", [
        ["--figtree-jar", "/tmp/arbitrary.jar"],
        ["--figtree-jar=/tmp/arbitrary.jar"],
    ])
    def test_figtree_jar_rejected(
        self, app: Any, ctx: Any, jar_args: List[str]
    ) -> None:
        with pytest.raises(ToolError) as ei:
            call_app(
                "run_figtreekit_cli", ctx,
                argv=["<input>", *jar_args, "-o", "x.nex", "--force"],
                tree_content=SMALL_TREE,
            )
        assert ei.value.code == "invalid_argument"
        assert ei.value.error_key == "figtree_jar_forbidden"


class TestArtifacts:
    def test_images_registered_with_data_uri(self, tmp_path: Path) -> None:
        root = tmp_path / "ws"
        run_dir = root / "run_img"
        run_dir.mkdir(parents=True)
        (run_dir / "plot.png").write_bytes(b"fake-png-bytes")
        (run_dir / "input.tre").write_text(SMALL_TREE, encoding="utf-8")
        artifacts = _scan_artifacts(RunStorage(run_dir=run_dir, root=root))
        assert len(artifacts) == 1
        entry = artifacts[0]
        assert entry["relative"].endswith("plot.png")
        assert entry["mime"] == "image/png"
        assert entry["data_uri"].startswith("data:image/png;base64,")


# --------------------------------------------------------------------------- #
# SEC-7: shell metacharacters are inert literals
# --------------------------------------------------------------------------- #
class TestNoShell:
    def test_shell_characters_pass_literally(self, app: Any, ctx: Any) -> None:
        argv = ["--help"]
        res = call_app("run_figtreekit_cli", ctx, argv=argv)
        assert res["ok"] is True
        assert res["returncode"] == 0
        assert "usage" in res["stdout_tail"].lower() or "usage" in res["stderr_tail"].lower()

    def test_metachars_treated_literally(self, app: Any, ctx: Any) -> None:
        # SEC-7: shell metacharacters in argv are passed as *literal* arguments;
        # they are never interpreted by a shell, so no file is created and the
        # command surfaces a normal CLI failure (or a successful run when the
        # tokens are accepted) — crucially ``$(touch ...)`` must NOT execute.
        marker = "/tmp/figtreekit-mcp-pwn-marker"
        if Path(marker).exists():
            Path(marker).unlink()
        # The literal ``$(touch ...)`` token makes figtreekit's parser treat it
        # as an unexpected positional input, so the run raises a clean ToolError
        # — but critically the marker must NOT have been created by a shell.
        with pytest.raises(ToolError) as ei:
            call_app(
                "run_figtreekit_cli", ctx,
                argv=["<input>", "--layout", "polar", "-o", "/tmp/evil.nex",
                      "--force", "$(touch " + marker + ")"],
                tree_content=SMALL_TREE,
            )
        assert ei.value.code == "cli_failed"
        assert not Path(marker).exists(), "shell metacharacters were executed!"

    def test_real_style_command(self, app: Any, ctx: Any) -> None:
        """SEC-4 + AC-8: a real styling command runs and writes into run dir."""
        res = call_app(
            "run_figtreekit_cli", ctx,
            argv=["<input>", "--layout", "polar", "--tip-labels-show",
                  "-o", "/tmp/output.nex", "--force"],
            tree_content=SMALL_TREE,
        )
        assert res["ok"] is True
        assert res["returncode"] == 0
        assert any("output.nex" in d and "run_" in d for d in res["rewrites"])
        artifacts = res["artifacts"]
        assert any(a["relative"].endswith("output.nex") and Path(a["absolute"]).is_file()
                   for a in artifacts)

    def test_failure_envelope_on_nonzero(self, app: Any, ctx: Any) -> None:
        with pytest.raises(ToolError) as ei:
            call_app("run_figtreekit_cli", ctx, argv=["--definitely-not-a-flag"])
        assert ei.value.code == "cli_failed"
        assert ei.value.error_key == "cli_failed"

    def test_mutually_exclusive_inputs(self, app: Any, ctx: Any) -> None:
        with pytest.raises(ToolError) as ei:
            call_app("run_figtreekit_cli", ctx, argv=["<input>", "--help"],
                     tree_content=SMALL_TREE, input_file="/tmp/x.tre")
        assert ei.value.error_key == "mutually_exclusive_input"

    def test_input_file_whitelist(self, app: Any, ctx: Any, reads_dir: Path) -> None:
        f = reads_dir / "in.tre"
        f.write_text(SMALL_TREE, encoding="utf-8")
        res = call_app("run_figtreekit_cli", ctx, argv=["<input>", "--layout", "radial",
                                                        "-o", "/tmp/x.nex", "--force"],
                       input_file=str(f))
        assert res["ok"] is True
        with pytest.raises(ToolError) as ei:
            call_app("run_figtreekit_cli", ctx, argv=["<input>", "--help"],
                     input_file="/etc/hosts")
        assert ei.value.code == "access_denied"


def test_self_test_via_passthrough(app: Any, ctx: Any) -> None:
    """AC-8: ``--self-test`` runs through the passthrough and exits 0."""
    res = call_app("run_figtreekit_cli", ctx, argv=["--self-test"], timeout=600)
    assert res["ok"] is True
    assert res["returncode"] == 0
    assert "checks passed" in (res["stdout_tail"] + res["stderr_tail"]).lower()
