# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Equivalence probe pytest entry (AC-6/7).

Runs ``tools/equivalence_probe.py`` against the 6 golden parameter sets on the
showcase tree (FigTree_withLACA_CLK_95CI).  Marked ``slow`` — CI & acceptance
always run it; skipped when the showcase input tree is absent.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from conftest import SHOWCASE_TREE, SHOWCASE_TSV

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"


def _load_probe() -> Any:
    sys.path.insert(0, str(_TOOLS_DIR))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    spec = importlib.util.spec_from_file_location(
        "equivalence_probe", _TOOLS_DIR / "equivalence_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.mark.slow
@pytest.mark.timeout(900)  # 6 golden sets x (API + CLI + MCP) ≈ 5 min
def test_golden_equivalence(showcase_tree: Path, showcase_tsv: Path, tmp_path: Path) -> None:
    probe = _load_probe()
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    report = probe.run_probe(str(showcase_tree), str(showcase_tsv), str(ws),
                             check_render=False)
    assert report["ok"], "equivalence probe failed:\n" + _fmt(report)


@pytest.mark.slow
@pytest.mark.timeout(900)
def test_golden_equivalence_with_render(showcase_tree: Path, showcase_tsv: Path,
                                        tmp_path: Path) -> None:
    probe = _load_probe()
    ws = tmp_path / "ws_render"
    ws.mkdir(parents=True, exist_ok=True)
    report = probe.run_probe(str(showcase_tree), str(showcase_tsv), str(ws),
                             check_render=True)
    assert report["ok"], "equivalence+render probe failed:\n" + _fmt(report)


def _fmt(report: Dict[str, Any]) -> str:
    return "\n".join(
        f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['message']}"
        for c in report["checks"]
    )
