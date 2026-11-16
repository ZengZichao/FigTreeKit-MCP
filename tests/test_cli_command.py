# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Reproducible-command unit tests.

``cli_command`` strings must be shell-safe (hex colours quoted so a leading
``#`` never starts a comment), segmented with `` && `` and re-runnable in zsh
— verified via a ``shlex.split`` round trip.
"""

from __future__ import annotations

import shlex

from figtreekit_mcp.cli_command import (
    bash_repr,
    build_figtreekit_command,
    build_java_render_command,
    join_commands,
    quote_arg,
    split_for_check,
)


class TestQuoteArg:
    def test_plain_word_unchanged(self) -> None:
        assert quote_arg("poland123") == "poland123"

    def test_hex_colour_quoted(self) -> None:
        quoted = quote_arg("#FF0000")
        assert quoted.startswith("'")
        assert quoted.endswith("'")
        assert shlex.split(quoted) == ["#FF0000"]

    def test_spaces_quoted(self) -> None:
        assert shlex.split(quote_arg("a b")) == ["a b"]

    def test_special_shell_chars_quoted(self) -> None:
        for evil in ("; rm -rf /", "$(id)", "`touch x`", "a|b", "a&b", "a>b"):
            assert shlex.split(quote_arg(evil)) == [evil]


class TestBuildCommands:
    def test_figtreekit_command_shape(self) -> None:
        cmd = build_figtreekit_command("/in/tree.tre", "/out/o.nex", ["--layout", "polar"])
        assert cmd == ("python -m figtreekit /in/tree.tre -o /out/o.nex --force --layout polar")

    def test_figtreekit_command_quotes_hex(self) -> None:
        cmd = build_figtreekit_command("i.tre", "o.nex", ["--background-color", "#FAFAFA"])
        assert "--background-color '#FAFAFA'" in cmd
        assert shlex.split(cmd)[-1] == "#FAFAFA"

    def test_force_false(self) -> None:
        cmd = build_figtreekit_command("i.tre", "o.nex", [], force=False)
        assert "--force" not in cmd

    def test_custom_python_and_module(self) -> None:
        cmd = build_figtreekit_command(
            "i.tre", "o.nex", [], python="/opt/py/bin/python", module="figtreekit"
        )
        assert cmd.startswith("/opt/py/bin/python -m figtreekit")

    def test_java_render_command(self) -> None:
        cmd = build_java_render_command("/a/o.nex", "/b/o.png", "PNG", 2400, 1600, "/j/fig.jar")
        parts = shlex.split(cmd)
        assert parts[:6] == ["java", "-jar", "/j/fig.jar", "-graphic", "PNG", "-width"]
        assert "2400" in parts and "1600" in parts
        assert parts[-2:] == ["/a/o.nex", "/b/o.png"]

    def test_join_commands_all_or_nothing(self) -> None:
        joined = join_commands(["a", "b", ""])
        assert joined == "a && b"

    def test_bash_repr(self) -> None:
        assert shlex.split(bash_repr("hello world")) == ["hello world"]


class TestRoundTrip:
    def test_shlex_round_trip_reconstructs_argv(self) -> None:
        args_list = [
            "--layout",
            "polar",
            "--background-color",
            "#FAFAFA",
            "--taxonomy-levels",
            "d:domain,p:phylum",
            "--set",
            "scaleAxis.fontSize=14",
            "--highlight",
            "A,B:#FF0000:3",
            "--collapse-taxa",
            "C,label=Clade1,type=cartoon",
        ]
        cmd = build_figtreekit_command("/path with space/in tree.tre", "/out/o.nex", args_list)
        reparsed = split_for_check(cmd)
        expected = [
            "python",
            "-m",
            "figtreekit",
            "/path with space/in tree.tre",
            "-o",
            "/out/o.nex",
            "--force",
            *args_list,
        ]
        assert reparsed == expected

    def test_java_command_round_trip(self) -> None:
        cmd = build_java_render_command("/d/o.nex", "/e/o.png", "PDF", 800, 600, "/j/jar x.jar")
        parts = split_for_check(cmd)
        assert parts[2] == "/j/jar x.jar"
