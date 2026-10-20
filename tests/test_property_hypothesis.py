# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Hypothesis property tests.

The ``ParamSpec`` validator (and the run-name/colour helpers it shares with
the passthrough tool) must never raise a bare exception on adversarial input —
only ``ToolError`` (the stable error family) or a successful validation.
"""

from __future__ import annotations

from typing import Any, Dict, List

from hypothesis import given, strategies as st

from figtreekit_mcp._errors import ToolError
from figtreekit_mcp.params import ParamSpec


# --------------------------------------------------------------------------- #
# 1. ParamSpec.validate() only raises ToolError, never a bare exception
# --------------------------------------------------------------------------- #
@given(st.dictionaries(keys=st.sampled_from([
    "layout", "rooting_type", "transform", "order", "tip_labels",
    "node_labels", "branch_labels", "scale_bar", "scale_axis", "legend",
    "legend_position", "collapse_style", "multi_tree",
    "background_color", "foreground_color", "selection_color", "label_color",
    "tip_label_font_style", "tip_label_font_size", "branch_width", "zoom",
    "expansion", "root_age", "scale_factor", "polar_angular_range_degrees",
    "polar_root_angle_degrees", "radial_spread", "curvature", "root_length",
    "scale_axis_font_size", "scale_axis_significant_digits", "run_name",
]), values=st.one_of(
    st.none(),
    st.text(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.booleans(),
    st.lists(st.text()),
)))
def test_param_spec_validate_only_raises_tool_error(kwargs: Dict[str, Any]) -> None:
    try:
        ParamSpec(**kwargs).validate()
    except ToolError:
        pass  # expected, stable error family
    except Exception as exc:  # pragma: no cover - must not happen
        raise AssertionError(
            f"ParamSpec.validate() raised bare {type(exc).__name__}: {exc!r}"
        ) from exc


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)),
               max_size=64))
def test_run_name_validation_only_tool_error(run_name: str) -> None:
    try:
        ParamSpec(run_name=run_name).validate()
    except ToolError:
        pass
    except Exception as exc:  # pragma: no cover
        raise AssertionError(
            f"run_name raised bare {type(exc).__name__}: {exc!r}"
        ) from exc


# --------------------------------------------------------------------------- #
# 2. Colour fields: any non-hex colour is cleanly rejected as ToolError
# --------------------------------------------------------------------------- #
@given(st.text())
def test_colour_never_crashes(value: str) -> None:
    try:
        ParamSpec(background_color=value).validate()
    except ToolError:
        pass
    except Exception as exc:  # pragma: no cover
        raise AssertionError(
            f"background_color raised bare {type(exc).__name__}: {exc!r}"
        ) from exc


# --------------------------------------------------------------------------- #
# 3. operations: adversarial op lists must never crash the validator
# --------------------------------------------------------------------------- #
@given(st.lists(st.dictionaries(
    keys=st.text(max_size=16),
    values=st.one_of(st.text(), st.integers(), st.booleans(), st.lists(st.text())),
    max_size=4,
), max_size=4))
def test_operations_never_crash(operations: List[Dict[str, Any]]) -> None:
    try:
        ParamSpec(operations=operations).validate()
    except ToolError:
        pass
    except Exception as exc:  # pragma: no cover
        raise AssertionError(
            f"operations raised bare {type(exc).__name__}: {exc!r}"
        ) from exc


# --------------------------------------------------------------------------- #
# 4. additional_config: arbitrary config dicts must not crash to_cli_args
# --------------------------------------------------------------------------- #
@given(st.dictionaries(st.text(max_size=16),
                       st.one_of(st.text(), st.integers(), st.floats(allow_nan=True),
                                 st.booleans())))
def test_additional_config_to_cli_args_never_crashes(cfg: Dict[str, Any]) -> None:
    try:
        spec = ParamSpec(additional_config=cfg)
        spec.validate()
        spec.to_cli_args()
        spec.to_config_dict()
    except ToolError:
        pass
    except Exception as exc:  # pragma: no cover
        raise AssertionError(
            f"additional_config raised bare {type(exc).__name__}: {exc!r}"
        ) from exc


# --------------------------------------------------------------------------- #
# 5. Valid parameter set round-trips through to_cli_args / to_config_dict
# --------------------------------------------------------------------------- #
@given(
    st.sampled_from(["rectilinear", "polar", "radial"]),
    st.integers(min_value=0, max_value=500),
    st.floats(min_value=0.001, max_value=1000.0, allow_nan=False),
)
def test_valid_params_round_trip(layout: str, expansion: int, zoom: float) -> None:
    spec = ParamSpec(layout=layout, expansion=expansion, zoom=zoom).validate()
    assert isinstance(spec.to_cli_args(), list)
    assert isinstance(spec.to_config_dict(), dict)
