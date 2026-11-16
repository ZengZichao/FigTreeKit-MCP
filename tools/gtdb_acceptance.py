#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""GTDB R232 real-data acceptance script (AC-12).

Runs a five-step end-to-end acceptance against real GTDB R232 data through the
in-process MCP tool handlers (the same code path as the running server):

====  ==========================  ============================================
Step  Input                       Check
====  ==========================  ============================================
1     ``ar53_r232.tree``          ``validate_tree`` ok and 700+ leaves
2     tree + taxonomy TSV         ``analyze_taxonomy(class)`` counts equal the
                                  ``figtreekit --analyze-taxonomy class`` CLI
3     tree + taxonomy TSV         ``style_tree(polar, phylum)`` .nex is
                                  byte-identical to the CLI .nex
4     .nex from step 3            ``render_tree`` PNG 2400x1600 + PDF exist,
                                  have the right size and are not blank
5     tree + taxonomy TSV         ``collapse_rank(class)`` .nex is byte-identical
                                  to the CLI .nex and contains ``!collapse``
====  ==========================  ============================================

The data directory is resolved, in order, from ``--read-root``,
``$FIGTREEKIT_GTDB_DIR``, ``$FIGTREEKIT_MCP_GTDB_DIR``, or a sibling
``FigTreeKit-参考文件/参考数据-GTDB-R232`` directory.  No author-specific
absolute path is hard-coded.

Exit codes:

* ``0`` - every step passed (an explicit ``--no-render`` skip is allowed);
* ``1`` - at least one step failed;
* ``2`` - invalid usage;
* ``3`` - SKIP: GTDB data not found (or one of the two expected files missing).

Usage::

    python tools/gtdb_acceptance.py --read-root /path/to/参考数据-GTDB-R232
    FIGTREEKIT_GTDB_DIR=/path/to/data python tools/gtdb_acceptance.py
    python tools/gtdb_acceptance.py --no-render
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Resolve the checkout (package lives under src/) for script execution.
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (_ROOT, _ROOT / "src"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

try:  # pragma: no cover - exercised by running the script
    from figtreekit_mcp._errors import ToolError
    from figtreekit_mcp.server import create_server, get_active_app
    from figtreekit_mcp.tools import TOOLS
except ModuleNotFoundError as exc:  # pragma: no cover
    print(f"[FAIL] missing dependency {exc.name!r}; run bash scripts/setup_env.sh", file=sys.stderr)
    raise SystemExit(2) from exc

_TAXONOMY_LEVELS = "d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus"
_TREE_NAME = "ar53_r232.tree"
_TAX_NAME = "ar53_r232_taxonomy.tsv"
_GTDB_ENV_KEYS = ("FIGTREEKIT_GTDB_DIR", "FIGTREEKIT_MCP_GTDB_DIR")


class _FakeCtx:
    """Minimal Context stand-in for in-process handler invocation."""

    def __init__(self, app: Any) -> None:
        self.request_context = types.SimpleNamespace(lifespan_context=app)

    def report_progress(self, *a: Any, **k: Any) -> None:
        pass

    def info(self, *a: Any, **k: Any) -> None:
        pass


# --------------------------------------------------------------------------- #
# Data discovery and CLI helpers
# --------------------------------------------------------------------------- #
def _default_candidates() -> List[Path]:
    """Sibling GTDB layouts that do not contain user-specific paths."""
    return [
        _ROOT.parent / "FigTreeKit-参考文件" / "参考数据-GTDB-R232",
        _ROOT.parent.parent / "FigTreeKit-参考文件" / "参考数据-GTDB-R232",
    ]


def _resolve_gtdb_dir(cli_value: Optional[str]) -> Optional[Path]:
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    for key in _GTDB_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return Path(value).expanduser().resolve()
    for candidate in _default_candidates():
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_cli(args: List[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Run ``python -m figtreekit ...`` with UTF-8 decoding (Windows-safe)."""
    cmd = [sys.executable, "-m", "figtreekit", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _run_from_cli_command(
    cli_command: str, output_path: Path, timeout: int = 600
) -> subprocess.CompletedProcess:
    """Re-run a returned ``cli_command`` with a different output path.

    ``style_tree`` returns a shell-quoted command such as
    ``python -m figtreekit 'input.tre' -o 'output.nex' --force ...``.  It is
    parsed with :mod:`shlex` (backslashes normalised to ``/`` so Windows paths
    survive) and executed with the current interpreter.
    """
    tokens = shlex.split(cli_command.replace("\\", "/"), posix=True)
    if len(tokens) < 3 or tokens[:3] != ["python", "-m", "figtreekit"]:
        raise ValueError(f"unexpected cli_command prefix: {tokens[:3]!r}")
    args = tokens[3:]

    rewritten: List[str] = []
    index = 0
    saw_output = False
    while index < len(args):
        token = args[index]
        if token in ("-o", "--output"):
            if index + 1 >= len(args):
                raise ValueError("cli_command ends with -o without a value")
            rewritten += [token, str(output_path)]
            saw_output = True
            index += 2
            continue
        rewritten.append(token)
        index += 1
    if not saw_output:
        rewritten += ["-o", str(output_path)]
    if "--force" not in rewritten:
        rewritten.append("--force")

    cmd = [sys.executable, "-m", "figtreekit", *rewritten]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _parse_cli_analysis(text: str) -> Dict[str, Any]:
    """Parse the human-readable ``--analyze-taxonomy`` report."""
    labels = {
        "total_labels": r"Total labels\s*:\s*(\d+)",
        "mapped_labels": r"Mapped labels\s*:\s*(\d+)",
        "total_groups": r"Total groups\s*:\s*(\d+)",
        "monophyletic": r"Monophyletic\s*:\s*(\d+)",
        "non_monophyletic": r"Non-monophyletic\s*:\s*(\d+)",
        "monophyly_rate": r"Monophyly rate\s*:\s*([0-9.]+)\s*%",
    }
    result: Dict[str, Any] = {}
    for key, pattern in labels.items():
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"CLI output is missing {key!r}")
        value = match.group(1)
        result[key] = float(value) if key == "monophyly_rate" else int(value)
    return result


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def _step1_validate(app: Any, tree: Path) -> Dict[str, Any]:
    res = TOOLS["validate_tree"](_FakeCtx(app), tree_file=str(tree))
    leaf = int(res.get("leaf_count") or 0)
    if not res.get("ok"):
        return {"ok": False, "message": f"validate_tree failed: {res.get('error_key')}"}
    if leaf < 700:
        return {"ok": False, "message": f"leaf_count={leaf}, expected 700+"}
    return {
        "ok": True,
        "message": (
            f"validate_tree ok: leaves={leaf}, trees={res.get('tree_count')}, "
            f"format={res.get('format')}"
        ),
    }


def _step2_analyze(app: Any, tree: Path, tax_tsv: Path) -> Dict[str, Any]:
    res = TOOLS["analyze_taxonomy"](
        _FakeCtx(app),
        tree_file=str(tree),
        taxonomy_mapping_file=str(tax_tsv),
        rank="class",
        taxonomy_levels=_TAXONOMY_LEVELS,
    )
    if not res.get("ok"):
        return {"ok": False, "message": f"analyze_taxonomy failed: {res.get('error_key')}"}
    summary = res.get("summary", {})
    mapped = int(summary.get("mapped_labels") or 0)
    if mapped <= 0:
        return {"ok": False, "message": "mapped_labels is 0; taxonomy mapping was not applied"}

    proc = _run_cli(
        [
            str(tree),
            "--analyze-taxonomy",
            "class",
            "--taxonomy-mapping-file",
            str(tax_tsv),
            "--taxonomy-levels",
            _TAXONOMY_LEVELS,
        ]
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "message": f"CLI --analyze-taxonomy failed (rc={proc.returncode}): "
            f"{proc.stderr[-400:]}",
        }
    try:
        cli = _parse_cli_analysis(proc.stdout + "\n" + proc.stderr)
    except ValueError as exc:
        return {"ok": False, "message": f"cannot parse CLI analysis: {exc}"}

    mcp = {
        "total_labels": int(summary.get("total_labels") or 0),
        "mapped_labels": mapped,
        "total_groups": int(summary.get("total_groups") or 0),
        "monophyletic": int(summary.get("monophyletic") or 0),
        "non_monophyletic": int(summary.get("non_monophyletic") or 0),
        "monophyly_rate": float(summary.get("monophyly_rate") or 0.0),
    }
    mismatches = [
        f"{key}: mcp={mcp[key]} cli={cli[key]}"
        for key in mcp
        if (round(mcp[key], 1) if key == "monophyly_rate" else mcp[key])
        != (round(cli[key], 1) if key == "monophyly_rate" else cli[key])
    ]
    if mismatches:
        return {"ok": False, "message": "MCP/CLI analysis mismatch: " + "; ".join(mismatches)}
    return {
        "ok": True,
        "message": (
            f"analyze_taxonomy(class) == CLI: labels={mcp['total_labels']}, "
            f"mapped={mcp['mapped_labels']}, groups={mcp['total_groups']}, "
            f"mono={mcp['monophyletic']}, non_mono={mcp['non_monophyletic']}, "
            f"rate={mcp['monophyly_rate']}%"
        ),
    }


def _style_kwargs(tree: Path, tax_tsv: Path) -> Dict[str, Any]:
    return {
        "tree_file": str(tree),
        "taxonomy_levels": _TAXONOMY_LEVELS,
        "taxonomy_mapping_file": str(tax_tsv),
        "layout": "polar",
        "auto_color_rank": "phylum",
        "tip_labels": "hide",
        "polar_angular_range_degrees": 180,
        "polar_root_angle_degrees": 270,
        "scale_axis": "show",
        "scale_axis_reverse": False,
        "scale_axis_font_size": 14,
        "scale_axis_significant_digits": 2,
    }


def _step3_style(app: Any, tree: Path, tax_tsv: Path, workspace: Path) -> Dict[str, Any]:
    res = TOOLS["style_tree"](_FakeCtx(app), **_style_kwargs(tree, tax_tsv))
    if not res.get("ok"):
        return {"ok": False, "message": f"style_tree failed: {res.get('error_key')}"}
    nexus = res.get("nexus_file", {}).get("absolute")
    if not nexus or not Path(nexus).is_file():
        return {"ok": False, "message": "style_tree did not write a .nex file"}
    cli_command = res.get("cli_command", "")
    if not cli_command:
        return {
            "ok": False,
            "message": "style_tree returned no cli_command (reproducibility red line)",
        }
    for required in ("--taxonomy-levels", "--taxonomy-mapping-file"):
        if required not in cli_command:
            return {"ok": False, "message": f"cli_command is missing {required} (cannot reproduce)"}

    cli_nexus = workspace / "cli_style.nex"
    try:
        proc = _run_from_cli_command(cli_command, cli_nexus)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "message": f"cannot run cli_command: {exc}"}
    if proc.returncode != 0:
        return {
            "ok": False,
            "message": f"CLI style failed (rc={proc.returncode}): {proc.stderr[-400:]}",
        }

    mcp_bytes = Path(nexus).read_bytes()
    cli_bytes = cli_nexus.read_bytes()
    if mcp_bytes != cli_bytes:
        return {
            "ok": False,
            "message": (
                f"style .nex differs from CLI: mcp={_sha256(Path(nexus))[:12]} "
                f"({len(mcp_bytes)} B) vs cli={_sha256(cli_nexus)[:12]} "
                f"({len(cli_bytes)} B)"
            ),
        }
    return {
        "ok": True,
        "message": f"style_tree .nex == CLI .nex (sha256 {_sha256(Path(nexus))[:12]})",
        "nexus": str(nexus),
    }


def _step4_render(app: Any, nexus: str, workspace: Path) -> Dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        return {"ok": False, "message": f"Pillow is required for the non-blank check: {exc}"}

    png = TOOLS["render_tree"](
        _FakeCtx(app),
        nexus_file=nexus,
        format="PNG",
        width=2400,
        height=1600,
    )
    if not png.get("ok"):
        return {
            "ok": False,
            "message": (
                f"render PNG failed: {png.get('error_key')} "
                "(install Java 8+ / figtree_patched.jar, or rerun with --no-render)"
            ),
        }
    image = png.get("image", {})
    png_path = Path(image.get("absolute") or "")
    if not png_path.is_file():
        return {"ok": False, "message": "PNG artifact was not written"}
    if image.get("width") != 2400 or image.get("height") != 1600:
        return {
            "ok": False,
            "message": f"PNG size is {image.get('width')}x{image.get('height')}, expected 2400x1600",
        }

    with Image.open(png_path) as handle:
        gray = handle.convert("L")
        histogram = gray.histogram()
        total = gray.width * gray.height
    # Non-blank check: a phylogenetic figure must contain more than a handful
    # of non-white pixels, and must not be a single flat colour (blank white or
    # solid black).  A dense 700-tip tree can legitimately cover every pixel,
    # so the intensity spread is a better blank detector than a ratio bound.
    nonwhite = sum(histogram[:250])
    ratio = nonwhite / total if total else 0.0
    if total == 0:
        return {"ok": False, "message": "PNG has zero pixels"}
    mean = sum(value * count for value, count in enumerate(histogram)) / total
    variance = sum((value - mean) ** 2 * count for value, count in enumerate(histogram)) / total
    deviation = variance**0.5
    if ratio < 0.002:
        return {"ok": False, "message": f"PNG looks blank: only {ratio:.4%} non-white pixels"}
    if deviation < 1.0:
        return {"ok": False, "message": f"PNG is a flat single colour (std={deviation:.3f})"}

    pdf = TOOLS["render_tree"](
        _FakeCtx(app),
        nexus_file=nexus,
        format="PDF",
        width=2400,
        height=1600,
    )
    if not pdf.get("ok"):
        return {"ok": False, "message": f"render PDF failed: {pdf.get('error_key')}"}
    pdf_path = Path(pdf.get("image", {}).get("absolute") or "")
    if not pdf_path.is_file():
        return {"ok": False, "message": "PDF artifact was not written"}
    head = pdf_path.read_bytes()[:5]
    if head != b"%PDF-":
        return {"ok": False, "message": f"PDF artifact has no %PDF header: {head!r}"}

    return {
        "ok": True,
        "message": (
            f"render_tree PNG 2400x1600 + PDF ok "
            f"(non-white={ratio:.2%}, pdf={pdf_path.stat().st_size} B)"
        ),
    }


def _step5_collapse(app: Any, tree: Path, tax_tsv: Path, workspace: Path) -> Dict[str, Any]:
    res = TOOLS["collapse_rank"](
        _FakeCtx(app),
        tree_file=str(tree),
        taxonomy_levels=_TAXONOMY_LEVELS,
        taxonomy_mapping_file=str(tax_tsv),
        rank="class",
        collapse_style="collapse",
        auto_color_rank="phylum",
    )
    if not res.get("ok"):
        return {"ok": False, "message": f"collapse_rank failed: {res.get('error_key')}"}
    collapsed = int(res.get("collapsed_groups") or 0)
    if collapsed <= 0:
        return {"ok": False, "message": "collapse_rank collapsed 0 groups"}
    nexus = res.get("nexus_file", {}).get("absolute")
    if not nexus or not Path(nexus).is_file():
        return {"ok": False, "message": "collapse_rank did not write a .nex file"}
    mcp_text = Path(nexus).read_text(encoding="utf-8")
    if "!collapse" not in mcp_text:
        return {"ok": False, "message": "collapse_rank .nex has no !collapse annotation"}

    # The tool's returned cli_command intentionally does not contain the
    # taxonomy flags (source limitation), so build the equivalent CLI argv
    # explicitly for the parity check.
    cli_nexus = workspace / "cli_collapse.nex"
    proc = _run_cli(
        [
            str(tree),
            "--collapse-rank",
            "class",
            "--collapse-style",
            "collapse",
            "--auto-color",
            "phylum",
            "--taxonomy-levels",
            _TAXONOMY_LEVELS,
            "--taxonomy-mapping-file",
            str(tax_tsv),
            "-o",
            str(cli_nexus),
            "--force",
        ]
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "message": f"CLI --collapse-rank failed (rc={proc.returncode}): {proc.stderr[-400:]}",
        }
    if Path(nexus).read_bytes() != cli_nexus.read_bytes():
        return {
            "ok": False,
            "message": (
                f"collapse .nex differs from CLI: "
                f"mcp={_sha256(Path(nexus))[:12]} vs "
                f"cli={_sha256(cli_nexus)[:12]}"
            ),
        }
    return {
        "ok": True,
        "message": (
            f"collapse_rank(class) collapsed={collapsed}, "
            f".nex == CLI (sha256 {_sha256(Path(nexus))[:12]})"
        ),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gtdb_acceptance",
        description="GTDB R232 five-step end-to-end acceptance (AC-12).",
    )
    parser.add_argument(
        "--read-root",
        default=None,
        help="GTDB input directory containing ar53_r232.tree and "
        "ar53_r232_taxonomy.tsv (env: FIGTREEKIT_GTDB_DIR)",
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help="Writable workspace (default: a temporary directory)",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip step 4 (use only when Java/JAR are unavailable)",
    )
    args = parser.parse_args(argv)

    gtdb = _resolve_gtdb_dir(args.read_root)
    tree = gtdb / _TREE_NAME if gtdb else None
    tax_tsv = gtdb / _TAX_NAME if gtdb else None
    missing = [str(p) for p in (tree, tax_tsv) if p is not None and not p.is_file()]
    if gtdb is None or tree is None or tax_tsv is None or missing:
        print("[SKIP] GTDB R232 data not found - acceptance cannot run.")
        if gtdb is not None:
            print(f"       Directory checked: {gtdb}")
            for path in missing:
                print(f"       Missing file    : {path}")
        print("       Provide the directory with one of:")
        print("         python tools/gtdb_acceptance.py --read-root /path/to/参考数据-GTDB-R232")
        print(
            "         FIGTREEKIT_GTDB_DIR=/path/to/参考数据-GTDB-R232 python tools/gtdb_acceptance.py"
        )
        print(f"       Expected files: {_TREE_NAME}, {_TAX_NAME}")
        return 3

    workspace = (
        Path(args.workspace_root).expanduser().resolve()
        if args.workspace_root
        else Path(tempfile.mkdtemp(prefix="figtreekit-gtdb-acceptance-"))
    )
    workspace.mkdir(parents=True, exist_ok=True)

    create_server(
        {
            "workspace_root": str(workspace),
            "read_roots": [str(gtdb)],
            "jar": None,
        }
    )
    app = get_active_app()
    if app is None:  # pragma: no cover - defensive
        print("[FAIL] create_server() did not install an AppContext", file=sys.stderr)
        return 1

    print("gtdb_acceptance (GTDB R232) - AC-12")
    print(f"data      : {gtdb}")
    print(f"workspace : {workspace}")
    print("-" * 72)

    steps: List[Dict[str, Any]] = []

    def run(label: str, fn: Any, *fn_args: Any) -> Optional[Dict[str, Any]]:
        try:
            result = fn(*fn_args)
        except ToolError as exc:
            result = {
                "ok": False,
                "message": f"{label} raised {exc.code}/{exc.error_key}: {exc.error}",
            }
        except Exception as exc:  # noqa: BLE001 - acceptance reports failures
            result = {"ok": False, "message": f"{label} raised {type(exc).__name__}: {exc}"}
        steps.append(result)
        return result

    run("validate", _step1_validate, app, tree)
    run("analyze", _step2_analyze, app, tree, tax_tsv)
    style_result = run("style", _step3_style, app, tree, tax_tsv, workspace)
    nexus = (style_result or {}).get("nexus")

    if args.no_render:
        steps.append(
            {"ok": True, "skipped": True, "message": "render skipped explicitly (--no-render)"}
        )
    elif nexus:
        run("render", _step4_render, app, nexus, workspace)
    else:
        steps.append({"ok": False, "message": "render skipped because step 3 (style) failed"})

    run("collapse", _step5_collapse, app, tree, tax_tsv, workspace)

    print("-" * 72)
    all_pass = True
    for index, step in enumerate(steps, 1):
        if not step.get("ok"):
            tag = "[FAIL]"
            all_pass = False
        elif step.get("skipped"):
            tag = "[SKIP]"
        else:
            tag = "[PASS]"
        print(f"{tag} step {index}: {step.get('message', '')}")
    print("-" * 72)
    print(f"RESULT: {'ALL PASS' if all_pass else 'FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
