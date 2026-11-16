# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Shared pytest fixtures for FigTreeKit-MCP.

Tests invoke tool handlers in-process with a fake ``Context`` whose
``request_context.lifespan_context`` carries the real AppContext built from a
per-test temporary workspace (stateless model).

Real-data fixtures (``gtdb_dir`` / ``showcase_tree``) are auto-discovered
relative to this repository, so integration tests run with real GTDB R232
trees when the sibling reference directory is present, and are skipped
otherwise.
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

# --------------------------------------------------------------------------- #
# Register every tool module (side-effect) so ``TOOLS`` is complete.
# --------------------------------------------------------------------------- #
for _mod in ("environment", "validate", "analyze", "style", "clade", "render", "passthrough"):
    importlib.import_module(f"figtreekit_mcp.tools.{_mod}")
from figtreekit_mcp.tools import TOOLS  # noqa: E402

from figtreekit_mcp.server import _APP_HOLDER, build_app_context  # noqa: E402

# --------------------------------------------------------------------------- #
# tree / taxonomy fixtures
# --------------------------------------------------------------------------- #
SMALL_TREE = "(((A:1,B:1):1,C:2):1,(D:3,E:3):1);"
UNROOTED_TREE = "((A:1,B:1):1,(C:2,D:2):1);"
NEGATIVE_BRANCH_TREE = "((A:-1,B:1):1,C:2);"
MULTI_TREE_NEXUS = """#NEXUS
begin trees;
  tree t1 = (((A:1,B:1):1,C:2):1,(D:3,E:3):1);
  tree t2 = (((A:1,B:1):1,D:2):1,(C:3,E:3):1);
end;
"""

# GTDB-style embedded taxonomy labels (format A: _p__X_ / _c__Y_ ...)
TAX_TREE = (
    "((A:p__Cyanobacteriota:c__Cyano:c1:1,B:p__Cyanobacteriota:c__Cyano:c2:1):1,"
    "(C:p__Euryarchaeota:c__Eury:c3:1,D:p__Euryarchaeota:c__Eury:c4:1):1,"
    "E:p__Actinobacteriota:c__Acti:c5:1);"
)
BIG_PHYLUM_TREE = (
    "(A_p__Phy1_c__Cls1:1,(B_p__Phy1_c__Cls1:1,C_p__Phy1_c__Cls2:1):1,"
    "(D_p__Phy2_c__Cls3:1,E_p__Phy2_c__Cls3:1):1,F_p__Phy3_c__Cls4:1);"
)
TAX_LEVELS = "d:domain,p:phylum,c:class,o:order,f:family,g:genus"
TABLE_MAPPING = "taxon\tphylum\tclass\nA\tPhy1\tCls1\nB\tPhy1\tCls1\nC\tPhy1\tCls2\nD\tPhy2\tCls3\nE\tPhy2\tCls3\nF\tPhy3\tCls4\n"

FASTA_DNA = ">seq1\nACGTACGT\n>seq2\nACGTACGT\n"
FASTQ_DNA = "@read1\nACGTACGT\n+\nIIIIIIII\n@read2\nACGTACGT\n+\nIIIIIIII\n"

# Tree whose tip labels match FASTA_DNA ids.
CROSS_TREE = "(seq1:1,seq2:1);"
MISMATCH_FASTA = ">other1\nACGTACGT\n>other2\nACGTACGT\n"

TAXONOMY_MAPPING_TSV = "taxon\tphylum\nA\tCyanobacteriota\nB\tCyanobacteriota\nC\tEuryarchaeota\nD\tEuryarchaeota\nE\tActinobacteriota\n"


# --------------------------------------------------------------------------- #
# Real-data discovery (FigTreeKit repo sibling directories)
# --------------------------------------------------------------------------- #
def _find_reference(name: str) -> Optional[Path]:
    """Locate a sibling reference directory by walking up from this file."""
    current = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = current / name
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def _find_file(rel: str) -> Optional[Path]:
    for prefix in ("..",):
        candidate = Path(__file__).resolve().parent.parent / prefix / rel
        if candidate.is_file():
            return candidate.resolve()
    base = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = base / rel
        if candidate.is_file():
            return candidate.resolve()
        if base.parent == base:
            break
        base = base.parent
    return None


GTDB_DIR = _find_reference("FigTreeKit-参考文件/参考数据-GTDB-R232")
SHOWCASE_TREE = _find_file("FigTreeKit-功能展示/输入文件/FigTree_withLACA_CLK_95CI.tree.recover")
SHOWCASE_TSV = _find_file("FigTreeKit-功能展示/输入文件/FigTree_withLACA_CLK_95CI.tsv")


def _gtdb(name: str) -> Optional[Path]:
    if GTDB_DIR is None:
        return None
    p = GTDB_DIR / name
    return p if p.is_file() else None


@pytest.fixture()
def gtdb_dir() -> Path:
    """Real GTDB R232 data directory (skipped when absent)."""
    if GTDB_DIR is None:
        pytest.skip("参考数据-GTDB-R232 目录不存在（真实数据集成测试跳过）")
    return GTDB_DIR


@pytest.fixture()
def ar53_tree() -> Path:
    p = _gtdb("ar53_r232.tree")
    if p is None:
        pytest.skip("ar53_r232.tree 缺失")
    return p


@pytest.fixture()
def ar53_taxonomy() -> Path:
    p = _gtdb("ar53_r232_taxonomy.tsv")
    if p is None:
        pytest.skip("ar53_r232_taxonomy.tsv 缺失")
    return p


@pytest.fixture()
def ar53_class_tree() -> Path:
    p = _gtdb("ar53_r232_class.tree")
    if p is None:
        pytest.skip("ar53_r232_class.tree 缺失")
    return p


@pytest.fixture()
def ar53_phylum_tree() -> Path:
    p = _gtdb("ar53_r232_phylum.tree")
    if p is None:
        pytest.skip("ar53_r232_phylum.tree 缺失")
    return p


@pytest.fixture(scope="session")
def showcase_tree() -> Path:
    """700-tip showcase tree (FigTree_withLACA_CLK_95CI)."""
    if SHOWCASE_TREE is None:
        pytest.skip("功能展示/输入文件/FigTree_withLACA_CLK_95CI.tree.recover 缺失")
    return SHOWCASE_TREE


@pytest.fixture(scope="session")
def showcase_tsv() -> Path:
    if SHOWCASE_TSV is None:
        pytest.skip("功能展示/输入文件/FigTree_withLACA_CLK_95CI.tsv 缺失")
    return SHOWCASE_TSV


SHOWCASE_LEVELS = "d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus"


@pytest.fixture()
def data_read_roots() -> List[str]:
    """Whitelisted read roots for real-data tests (best effort)."""
    roots: List[str] = []
    if GTDB_DIR is not None:
        roots.append(str(GTDB_DIR))
    if SHOWCASE_TREE is not None:
        roots.append(str(SHOWCASE_TREE.parent.parent))
    return roots


# --------------------------------------------------------------------------- #
# App / context fixtures
# --------------------------------------------------------------------------- #
def _build_app(
    tmp_path: Path, extra_read_roots: Optional[List[str]] = None, **overrides: Any
) -> Any:
    cfg: Dict[str, Any] = {
        "workspace_root": str(tmp_path / "ws"),
        "read_roots": [str(tmp_path / "reads")],
        "jar": None,
    }
    if extra_read_roots:
        cfg["read_roots"] = list(cfg["read_roots"]) + list(extra_read_roots)
    cfg.update(overrides)
    ctx = build_app_context(cfg)
    (tmp_path / "reads").mkdir(parents=True, exist_ok=True)
    _APP_HOLDER["app"] = ctx
    return ctx


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    """A real AppContext over a fresh temporary workspace."""
    return _build_app(tmp_path)


@pytest.fixture()
def app_with_data(tmp_path: Path, data_read_roots: List[str]) -> Any:
    """AppContext whose read roots also include the reference data dirs."""
    return _build_app(tmp_path, extra_read_roots=data_read_roots)


def _fake_ctx(app: Any) -> Any:
    class _FakeCtx:
        request_context = types.SimpleNamespace(lifespan_context=app)

        def report_progress(self, *a: Any, **k: Any) -> None:
            pass

        def info(self, *a: Any, **k: Any) -> None:
            pass

    return _FakeCtx()


@pytest.fixture()
def ctx(app: Any) -> Any:
    """A fake MCP Context carrying the AppContext lifespan value."""
    return _fake_ctx(app)


@pytest.fixture()
def ctx_with_data(app_with_data: Any) -> Any:
    return _fake_ctx(app_with_data)


@pytest.fixture()
def reads_dir(tmp_path: Path) -> Path:
    """Path to the whitelisted read-only root."""
    d = tmp_path / "reads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def call_app(name: str, ctx: Any, **kwargs: Any) -> Dict[str, Any]:
    """Invoke a registered handler directly (in-process integration)."""
    if name not in TOOLS:
        raise KeyError(f"tool not registered: {name}")
    return TOOLS[name](ctx, **kwargs)


@pytest.fixture()
def call(ctx: Any) -> Callable[..., Dict[str, Any]]:
    """Handy per-test callable bound to the fake context."""

    def _call(name: str, **kwargs: Any) -> Dict[str, Any]:
        return call_app(name, ctx, **kwargs)

    return _call


@pytest.fixture()
def call_app_data(ctx_with_data: Any) -> Callable[..., Dict[str, Any]]:
    """Callable bound to a context whose read roots include the reference data."""

    def _call(name: str, **kwargs: Any) -> Dict[str, Any]:
        return call_app(name, ctx_with_data, **kwargs)

    return _call
