#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Equivalence probe: MCP style_tree == CLI byte-for-byte, and both == API
baseline semantically; render pixel-statistics < 0.5%.

For each of the 6 golden parameter sets:

1. **API 基准** — ``ref_test_gen.build_styler`` (raw figtreekit Python API);
2. **CLI 基准** — ``python -m figtreekit`` with the equivalent CLI args;
3. **MCP 基准** — the ``style_tree`` handler with the same parameter set;
4. assert  MCP .nex == CLI .nex (byte-for-byte), and both are semantically
   equal to the API baseline after normalising known non-deterministic fields
   (tree names / tree indices).
5. render MCP PNG vs ``java -jar ... -graphic`` direct PNG, pixel-stat diff <0.5%.

Exit code 0 when every check passes, non-zero with a diff summary otherwise.

Usage:
    python tools/equivalence_probe.py <input.tree> <taxonomy.tsv> <workspace_root>
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---- resolve package when run as a script (repo root + src on sys.path) -----
_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (_ROOT, _ROOT / "src"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from figtreekit_mcp.params import ParamSpec  # noqa: E402
from figtreekit_mcp.server import build_app_context  # noqa: E402

from ref_test_gen import GOLDEN_SETS, GoldenSet, build_styler  # noqa: E402

PY = sys.executable
TAXONOMY_LEVELS = "d:domain,sp:superphylum,p:phylum,c:class,o:order,f:family,g:genus"


# --------------------------------------------------------------------------- #
# Golden set → MCP ParamSpec / CLI argv (CLI mapping)
# --------------------------------------------------------------------------- #
def _mcp_spec(gs: GoldenSet, input_tree: str, taxonomy_tsv: str) -> ParamSpec:
    spec = ParamSpec(
        tree_file=input_tree,
        taxonomy_levels=TAXONOMY_LEVELS,
        taxonomy_mapping_file=taxonomy_tsv,
        layout=gs.layout,
        auto_color_rank=gs.auto_color_rank,
        collapse_rank=gs.collapse_rank,
        collapse_style=gs.collapse_style or "collapse",
        tip_labels="hide" if gs.tip_labels_hide else None,
        scale_axis="show" if gs.scale_axis_reverse is not None else None,
        scale_axis_reverse=gs.scale_axis_reverse,
        scale_axis_font_size=gs.scale_axis_font_size,
        scale_axis_significant_digits=gs.scale_axis_significant_digits,
        polar_angular_range_degrees=(
            (360 - gs.angular_range / 1000) if gs.angular_range is not None else None
        ),
        polar_root_angle_degrees=(
            (gs.root_angle / 1000 + 180) if gs.root_angle is not None else None
        ),
        # The showcase Nexus contains several trees; process the first one so
        # the MCP and CLI outputs are directly comparable (CLI parity).
        multi_tree="first",
    )
    return spec.validate()


def _cli_argv(gs: GoldenSet, input_tree: str, taxonomy_tsv: str) -> List[str]:
    spec = _mcp_spec(gs, input_tree, taxonomy_tsv)
    # to_cli_args already emits --taxonomy-levels / --taxonomy-mapping-file.
    return [input_tree] + spec.to_cli_args()


# --------------------------------------------------------------------------- #
# Normalisation for the API-baseline comparison (tree names may differ)
# --------------------------------------------------------------------------- #
def _normalise_nexus(text: str) -> str:
    """Strip tree names / indices that legitimately differ across generators."""
    # Normalise trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    # Tree names:  tree t1 = ...  →  tree = ...
    text = re.sub(r"\btree\s+[\w]+(?=\s*=)", "tree", text)
    # Collapse repeated blank lines
    text = re.sub(r"\n{2,}", "\n", text)
    return text


# --------------------------------------------------------------------------- #
# MCP style_tree handler
# --------------------------------------------------------------------------- #
def _style_via_mcp(
    input_tree: str, taxonomy_tsv: str, gs: GoldenSet, workspace_root: str
) -> Dict[str, Any]:
    import types

    ctx = build_app_context(
        {
            "workspace_root": workspace_root,
            "read_roots": [str(Path(input_tree).parent), str(Path(taxonomy_tsv).parent)],
            "jar": None,
        }
    )

    # fake MCP context carrying the AppContext
    class _FakeCtx:
        request_context = types.SimpleNamespace(lifespan_context=ctx)

        def report_progress(self, *a: Any, **k: Any) -> None:
            pass

        def info(self, *a: Any, **k: Any) -> None:
            pass

    from figtreekit_mcp.tools import TOOLS

    _mcp_spec(gs, input_tree, taxonomy_tsv)
    kwargs = {
        "tree_file": input_tree,
        "taxonomy_levels": TAXONOMY_LEVELS,
        "taxonomy_mapping_file": taxonomy_tsv,
        "layout": gs.layout,
        "auto_color_rank": gs.auto_color_rank,
        "collapse_rank": gs.collapse_rank,
        "collapse_style": gs.collapse_style or "collapse",
        "tip_labels": "hide" if gs.tip_labels_hide else None,
        "scale_axis": "show" if gs.scale_axis_reverse is not None else None,
        "scale_axis_reverse": gs.scale_axis_reverse,
        "scale_axis_font_size": gs.scale_axis_font_size,
        "scale_axis_significant_digits": gs.scale_axis_significant_digits,
        "multi_tree": "first",
    }
    if gs.angular_range is not None:
        kwargs["polar_angular_range_degrees"] = 360 - gs.angular_range / 1000
    if gs.root_angle is not None:
        kwargs["polar_root_angle_degrees"] = gs.root_angle / 1000 + 180

    res = TOOLS["style_tree"](_FakeCtx(), **kwargs)
    if not res.get("ok"):
        raise RuntimeError(f"style_tree failed for {gs.key}: {res}")
    return res


# --------------------------------------------------------------------------- #
# CLI generation
# --------------------------------------------------------------------------- #
def _cli_nexus(input_tree: str, taxonomy_tsv: str, gs: GoldenSet, out: Path) -> Path:
    argv = _cli_argv(gs, input_tree, taxonomy_tsv)
    # argv == [input_tree] + spec.to_cli_args(); append -o/--force at the end,
    # never slice off the trailing taxonomy-mapping-file value.
    cmd = [PY, "-m", "figtreekit", *argv, "-o", str(out), "--force"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed for {gs.key}: {proc.stderr[-2000:]}")
    return out


# --------------------------------------------------------------------------- #
# Render + pixel statistics
# --------------------------------------------------------------------------- #
def _pixel_stats(path: Path) -> Dict[str, Any]:
    """Return total / background / red-labelled pixel stats (Studio-inspired)."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        total = im.width * im.height
        pixels = list(im.getdata())
    # white-ish background
    bg = sum(1 for r, g, b in pixels if r >= 250 and g >= 250 and b >= 250)
    # red-labelled / coloured pixels (dominant red channel)
    red = sum(1 for r, g, b in pixels if r > 150 and r - g > 60 and r - b > 60)
    return {
        "total": total,
        "background": bg,
        "background_ratio": bg / total if total else 0.0,
        "red": red,
        "red_ratio": red / total if total else 0.0,
    }


# --------------------------------------------------------------------------- #
# Main probe
# --------------------------------------------------------------------------- #
def run_probe(
    input_tree: str,
    taxonomy_tsv: str,
    workspace_root: str,
    *,
    only: Optional[List[str]] = None,
    check_render: bool = True,
) -> Dict[str, Any]:
    """Run the full equivalence probe; returns a structured report."""
    report: Dict[str, Any] = {"ok": True, "checks": []}

    def _record(passed: bool, msg: str) -> None:
        report["checks"].append({"ok": passed, "message": msg})
        if not passed:
            report["ok"] = False

    work = tempfile.mkdtemp(prefix="figtreekit-mcp-equiv-")
    Path(workspace_root).mkdir(parents=True, exist_ok=True)

    for gs in GOLDEN_SETS:
        if only and gs.key not in only:
            continue
        try:
            # API baseline
            api_nex = Path(work) / f"{gs.key}_api.nex"
            build_styler(input_tree, taxonomy_tsv, gs).export(
                str(api_nex), include_taxa_block=True, single_tree=True
            )
            api_text = _normalise_nexus(api_nex.read_text(encoding="utf-8"))

            # CLI baseline
            cli_nex = _cli_nexus(input_tree, taxonomy_tsv, gs, Path(work) / f"{gs.key}_cli.nex")
            cli_text = cli_nex.read_text(encoding="utf-8")

            # MCP baseline
            mcp = _style_via_mcp(input_tree, taxonomy_tsv, gs, workspace_root)
            mcp_nex_path = Path(mcp["nexus_file"]["absolute"])
            mcp_text = mcp_nex_path.read_text(encoding="utf-8")

            # 1) MCP == CLI byte-for-byte
            byte_ok = mcp_text == cli_text
            _record(byte_ok, f"{gs.key}: MCP .nex == CLI .nex (byte-for-byte)")

            # 2) MCP & CLI vs API baseline (normalised semantic equality)
            api_match_mcp = _normalise_nexus(mcp_text) == api_text
            api_match_cli = _normalise_nexus(cli_text) == api_text
            _record(
                api_match_mcp and api_match_cli, f"{gs.key}: MCP & CLI ≡ API baseline (normalised)"
            )

            # 3) render (if java + jar available)
            if check_render:
                render_report = _check_render(mcp_nex_path, workspace_root, gs)
                for r in render_report:
                    _record(r["ok"], f"{gs.key}: {r['message']}")
        except Exception as exc:  # noqa: BLE001 - collect per-set failures
            _record(False, f"{gs.key}: probe error — {type(exc).__name__}: {exc}")

    return report


def _check_render(mcp_nex: Path, workspace_root: str, gs: GoldenSet) -> List[Dict[str, Any]]:
    """Compare MCP-rendered PNG vs a direct ``java -jar`` PNG (pixel stats)."""
    from figtreekit_mcp.tools.environment import probe_jar, probe_java

    java = probe_java()
    jar = probe_jar(
        build_app_context({"workspace_root": workspace_root, "read_roots": [], "jar": None})
    )
    if not (java["ok"] and jar["ok"]):
        return [{"ok": True, "message": "render skipped (Java/JAR missing)"}]

    out_dir = Path(workspace_root) / f"{gs.key}_render"
    out_dir.mkdir(parents=True, exist_ok=True)

    # MCP render path (via figtreekit.render_with_figtree)
    import figtreekit

    mcp_png = out_dir / "mcp.png"
    try:
        figtreekit.render_with_figtree(
            str(mcp_nex),
            str(mcp_png),
            format="PNG",
            width=400,
            height=300,
            jar_path=jar["path"],
            timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "message": f"render_tree failed: {exc}"}]

    # Direct JAR render
    direct_png = out_dir / "direct.png"
    jar_cmd = [
        "java",
        "-jar",
        jar["path"],
        "-graphic",
        "PNG",
        "-width",
        "400",
        "-height",
        "300",
        str(mcp_nex),
        str(direct_png),
    ]
    proc = subprocess.run(jar_cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        return [{"ok": False, "message": f"direct JAR render failed: {proc.stderr[-800:]}"}]

    try:
        m = _pixel_stats(mcp_png)
        d = _pixel_stats(direct_png)
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "message": f"pixel stats failed: {exc}"}]

    diff = abs(m["red_ratio"] - d["red_ratio"]) + abs(m["background_ratio"] - d["background_ratio"])
    ok = diff < 0.005
    return [
        {
            "ok": ok,
            "message": f"render pixel diff = {diff:.4f} (<0.5%) "
            f"[MCP red={m['red_ratio']:.4f} bg={m['background_ratio']:.4f} | "
            f"JAR red={d['red_ratio']:.4f} bg={d['background_ratio']:.4f}]",
        }
    ]


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3:
        print(__doc__)
        return 2
    input_tree, taxonomy_tsv, workspace_root = args[0], args[1], args[2]
    for label, value in (("input tree", input_tree), ("taxonomy table", taxonomy_tsv)):
        if not Path(value).is_file():
            print(f"[FAIL] {label} not found: {value}", file=sys.stderr)
            return 2
    report = run_probe(input_tree, taxonomy_tsv, workspace_root)
    print(f"equivalence probe: {'ALL PASS' if report['ok'] else 'FAILED'}")
    for c in report["checks"]:
        tag = "PASS" if c["ok"] else "FAIL"
        print(f"  [{tag}] {c['message']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
