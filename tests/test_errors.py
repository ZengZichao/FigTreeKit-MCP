# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Error envelope and exception-mapping unit tests.

Every figtreekit exception must map to its stable code; unknown exceptions
become ``internal_error`` with a stack summary; ``CompatibilityWarning``
surfaces as ``validation_failed``.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

import figtreekit
from figtreekit import exceptions as fk_exc

from figtreekit_mcp._errors import (
    ERROR_CODES,
    ToolError,
    envelope_from_exception,
    error_envelope,
    guard,
    ok_envelope,
)


class TestEnvelope:
    def test_ok_envelope(self) -> None:
        env = ok_envelope(a=1, b="x")
        assert env["ok"] is True
        assert env["a"] == 1

    def test_error_envelope_shape(self) -> None:
        env = error_envelope(code="access_denied", error="拒绝", error_key="k",
                             error_detail="d", details=[{"level": "W", "message": "m"}])
        assert env == {
            "ok": False,
            "code": "access_denied",
            "error_key": "k",
            "error": "拒绝",
            "error_detail": "d",
            "details": [{"level": "W", "message": "m"}],
        }

    def test_error_envelope_run_dir_extra(self) -> None:
        env = error_envelope(code="access_denied", error="e", run_dir="run_1", extra_field=2)
        assert env["run_dir"] == "run_1"
        assert env["extra_field"] == 2

    def test_stable_error_codes(self) -> None:
        assert len(ERROR_CODES) == 19
        assert ERROR_CODES[0] == "invalid_argument"
        assert "internal_error" in ERROR_CODES


class TestToolError:
    def test_unknown_code_normalised(self) -> None:
        t = ToolError("nope", "x")
        assert t.code == "internal_error"
        assert t.error_key == "internal_error"

    def test_cancelled_allowed(self) -> None:
        t = ToolError("cancelled", "取消")
        assert t.code == "cancelled"

    def test_message_is_error(self) -> None:
        t = ToolError("cli_failed", "命令失败")
        assert str(t) == "命令失败"


class TestExceptionMapping:
    def test_toolerror_passthrough(self) -> None:
        src = ToolError("monophyly_error", "m", error_key="kk", error_detail="dd",
                        details=[{"level": "E", "message": "x"}])
        env = envelope_from_exception(src, run_dir="run_9")
        assert env["code"] == "monophyly_error"
        assert env["error_key"] == "kk"
        assert env["error_detail"] == "dd"
        assert env["run_dir"] == "run_9"

    def test_value_error_maps_invalid_argument(self) -> None:
        env = envelope_from_exception(ValueError("bad value"))
        assert env["code"] == "invalid_argument"

    def test_file_not_found_maps_access_denied(self) -> None:
        env = envelope_from_exception(FileNotFoundError("/x"))
        assert env["code"] == "access_denied"

    def test_permission_error_maps_access_denied(self) -> None:
        env = envelope_from_exception(PermissionError("denied"))
        assert env["code"] == "access_denied"

    def test_figtreekit_parse_error(self) -> None:
        env = envelope_from_exception(fk_exc.ParseError("syntax"))
        assert env["code"] == "tree_parse_error"

    def test_figtreekit_phylo_format_error(self) -> None:
        env = envelope_from_exception(fk_exc.PhyloFormatError("fmt"))
        assert env["code"] == "tree_parse_error"

    def test_figtreekit_validation_error(self) -> None:
        env = envelope_from_exception(fk_exc.ValidationError("v"))
        assert env["code"] == "validation_failed"

    def test_figtreekit_export_error(self) -> None:
        env = envelope_from_exception(fk_exc.ExportError("x"))
        assert env["code"] == "export_failed"

    def test_figtreekit_render_error(self) -> None:
        env = envelope_from_exception(fk_exc.RenderError("r"))
        assert env["code"] == "render_failed"

    def test_figtreekit_monophyly_error(self) -> None:
        env = envelope_from_exception(fk_exc.MonophylyError("m"))
        assert env["code"] == "monophyly_error"

    def test_figtreekit_taxonomy_conflict(self) -> None:
        env = envelope_from_exception(fk_exc.TaxonomyConflictError("t"))
        assert env["code"] == "taxonomy_conflict"

    def test_compatibility_warning_surfaces(self) -> None:
        env = envelope_from_exception(fk_exc.CompatibilityWarning("compat"))
        assert env["code"] == "validation_failed"
        assert env["error_key"] == "compatibility_warning"

    def test_unknown_exception_internal_with_stack(self) -> None:
        env = envelope_from_exception(RuntimeError("boom"))
        assert env["code"] == "internal_error"
        assert "stack_summary" in env
        assert "RuntimeError" in env["stack_summary"]
        # never leaks the raw traceback to the detail field
        assert "Traceback" not in env["error"]

    def test_friendly_message_chinese(self) -> None:
        env = envelope_from_exception(FileNotFoundError("missing"))
        assert "拒绝" in env["error"]


class TestGuard:
    def test_guard_passes_through_result(self) -> None:
        @guard
        def fn() -> Dict[str, Any]:
            return {"ok": True}

        assert fn() == {"ok": True}

    def test_guard_catches_into_envelope(self) -> None:
        @guard
        def fn() -> Dict[str, Any]:
            raise ToolError("access_denied", "越权")

        env = fn()
        assert env["ok"] is False
        assert env["code"] == "access_denied"

    def test_guard_catches_unexpected(self) -> None:
        @guard
        def fn() -> Dict[str, Any]:
            raise ValueError("bad")

        env = fn()
        assert env["code"] == "invalid_argument"

    def test_guard_passes_keyboard_interrupt(self) -> None:
        @guard
        def fn() -> Dict[str, Any]:
            raise KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            fn()

    def test_guard_passes_system_exit(self) -> None:
        @guard
        def fn() -> Dict[str, Any]:
            raise SystemExit(3)

        with pytest.raises(SystemExit) as ei:
            fn()
        assert ei.value.code == 3


def test_collect_warnings() -> None:
    import warnings

    from figtreekit_mcp._errors import collect_warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn("w1", UserWarning)
        warnings.warn("w2", UserWarning)
    assert collect_warnings(caught) == [
        {"level": "WARNING", "message": "w1"},
        {"level": "WARNING", "message": "w2"},
    ]

    # plain objects / strings are also normalised
    assert collect_warnings(["raw-text"]) == [{"level": "WARNING", "message": "raw-text"}]


def test_figtreekit_exceptions_module_importable() -> None:
    assert figtreekit.exceptions is fk_exc
