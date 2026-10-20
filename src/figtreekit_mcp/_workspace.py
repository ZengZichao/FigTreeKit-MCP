# SPDX-License-Identifier: GPL-2.0-or-later
# This file is part of FigTreeKit-MCP; see LICENSE and NOTICE for licensing terms.
"""Workspace management: path whitelist, run directories, artifact registry.

Security model:
- One **writable** root (``--workspace-root``): everything produced lives here.
- Zero..N **read-only** roots (``--allow-read-root``): input files may come
  from these trees.
- ``assert_within_roots`` canonicalises with ``Path.resolve()`` (following
  symlinks) and requires the final target to stay inside a registered root;
  a symlink that escapes is therefore rejected (SEC-2).

Artifacts are written to per-call ``run_<uuid8>`` directories, so
concurrent calls never collide and products are auditable.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ._errors import ToolError
from ._logging import get_logger

_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")  # full artifact filename
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Inline previews are token-expensive (base64 inflates by ~33%). 512 KiB is
# enough for a readable thumbnail while keeping a single tool result small.
_DATA_URI_MAX_BYTES = 512 * 1024
_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}


def resolve_root(root: str | os.PathLike) -> Path:
    """Canonicalise an absolute writable root, creating it if needed."""
    path = Path(root).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _reject_parent_tokens(path: Path) -> None:
    if any(part == ".." for part in path.parts):
        raise ToolError(
            "access_denied",
            "路径包含 '..' 父目录跳转，已拒绝",
            error_key="path_traversal",
            error_detail=f"路径含 '..' 段：{path}",
        )
    # Windows treats ``C:relative`` as relative to the current directory on
    # drive C; resolving it may silently leave the configured root.
    if os.name == "nt" and path.drive and not path.is_absolute():
        raise ToolError(
            "access_denied",
            "不允许 Windows 盘符相对路径",
            error_key="drive_relative_path",
            error_detail=str(path),
        )


def _check_artifact_name(base_name: str) -> None:
    """Reject names that are not a single, ordinary path component."""
    if (
        not _RUN_NAME_RE.match(base_name)
        or base_name in (".", "..")
        or base_name.rstrip(". ") != base_name
        or (os.name == "nt" and base_name.split(".", 1)[0].upper() in _WINDOWS_RESERVED)
    ):
        raise ToolError(
            "invalid_argument",
            "产物文件名不合法（仅允许字母、数字、下划线、点、连字符，长度 1-64）",
            error_key="bad_run_name",
            error_detail=base_name,
        )


def assert_within_roots(
    path: str | os.PathLike,
    roots: List[Path],
    *,
    writable: bool = False,
    base_dir: Optional[Path] = None,
) -> Path:
    """Assert *path* resolves inside one of the whitelisted roots.

    Args:
        path: Input path (absolute, or relative to *base_dir*).
        roots: Registered root paths (already resolved).
        writable: If ``True`` the parent directory must exist for writes.
        base_dir: Base for resolving relative paths (default: workspace root).

    Returns:
        The resolved absolute path.

    Raises:
        ToolError(access_denied): Any whitelist / symlink escape violation.
    """
    if not roots:
        raise ToolError(
            "access_denied",
            "未配置任何允许访问的根目录",
            error_key="no_roots",
        )
    p = Path(path).expanduser()
    if os.name == "nt" and p.drive and not p.is_absolute():
        raise ToolError(
            "access_denied",
            "不允许 Windows 盘符相对路径",
            error_key="drive_relative_path",
            error_detail=str(p),
        )
    if not p.is_absolute():
        if base_dir is None:
            raise ToolError(
                "access_denied",
                "相对路径需要基于 workspace 根目录解析",
                error_key="relative_without_base",
                error_detail=f"{p}",
            )
        p = base_dir / p

    _reject_parent_tokens(p)

    try:
        resolved = p.resolve()  # follows symlinks
    except OSError as exc:
        raise ToolError(
            "access_denied",
            f"无法解析路径：{exc}",
            error_key="resolve_failed",
            error_detail=str(p),
        ) from exc

    for root in roots:
        if resolved.is_relative_to(root):
            if writable:
                # Only the writable root may be written; ensure parent exists.
                parent = resolved.parent
                if not parent.exists():
                    raise ToolError(
                        "access_denied",
                        "写入目录不存在（无法创建）",
                        error_key="parent_missing",
                        error_detail=str(parent),
                    )
                if not parent.is_dir():
                    raise ToolError(
                        "access_denied",
                        "写入目标父路径不是目录",
                        error_key="parent_not_dir",
                        error_detail=str(parent),
                    )
            return resolved

    root_list = "\n".join(f"  - {r}" for r in roots)
    raise ToolError(
        "access_denied",
        "路径不在允许访问的白名单根目录内",
        error_key="outside_roots",
        error_detail=f"请求路径：{resolved}\n允许的根目录：\n{root_list}",
    )


def check_readable(root: Path) -> bool:
    """Return whether *root* exists and is readable (for startup diagnostics)."""
    return root.is_dir() and os.access(root, os.R_OK)


@dataclass
class RunStorage:
    """A single ``run_<uuid8>`` directory with artifact registration."""

    run_dir: Path
    root: Path
    created_at: float = field(default_factory=time.time)

    @property
    def name(self) -> str:
        return self.run_dir.name

    def file_path(self, base_name: str = "output") -> Path:
        """Return a safe path inside the run dir from an artifact base name."""
        _check_artifact_name(base_name)
        return self.run_dir / base_name

    def register(
        self,
        relpath: str | os.PathLike,
        *,
        with_data_uri: bool = True,
    ) -> Dict[str, object]:
        """Register a produced artifact; returns ``{relative, absolute, ...}``.

        A base64 ``data_uri`` is generated only for image-like files ≤ 512 KiB
        (token economy; larger previews are left on disk).
        """
        path = Path(relpath)
        if not path.is_absolute():
            path = self.run_dir / path
        path = assert_within_roots(path, [self.root], writable=False, base_dir=self.root)

        entry: Dict[str, object] = {
            "relative": str(path.relative_to(self.root)),
            "absolute": str(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

        mime = _IMAGE_MIME.get(path.suffix.lower())
        if (
            with_data_uri
            and mime
            and path.exists()
            and path.stat().st_size <= _DATA_URI_MAX_BYTES
        ):
            data = path.read_bytes()
            entry["data_uri"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            entry["mime"] = mime
        else:
            entry["data_uri"] = None
            entry["mime"] = mime

        # Image dimensions for raster formats (best-effort)
        if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            try:
                from PIL import Image

                with Image.open(path) as im:
                    entry["width"], entry["height"] = im.size
            except Exception:  # pragma: no cover - best-effort
                pass
        return entry


class Workspace:
    """Workspace root + whitelist roots + run-directory lifecycle."""

    def __init__(
        self,
        root: str | os.PathLike,
        read_roots: Optional[List[str | os.PathLike]] = None,
        *,
        keep_runs: int = 50,
        content_max_bytes: int = 10 * 1024 * 1024,
        file_max_bytes: int = 200 * 1024 * 1024,
    ) -> None:
        self.root = resolve_root(root)
        read_paths = [Path(p).expanduser().resolve() for p in (read_roots or [])]
        self.read_roots: List[Path] = [self.root] + read_paths
        self.keep_runs = keep_runs
        self.content_max_bytes = content_max_bytes
        self.file_max_bytes = file_max_bytes
        self._log = get_logger()

    # -- whitelist -------------------------------------------------------
    @property
    def allowed_read_roots(self) -> List[str]:
        return [str(r) for r in self.read_roots]

    def assert_readable(self, path: str | os.PathLike) -> Path:
        """Assert *path* may be *read* (inside any root, incl. read roots)."""
        return assert_within_roots(path, self.read_roots, writable=False, base_dir=self.root)

    def assert_writable(self, path: str | os.PathLike) -> Path:
        """Assert *path* may be *written* (inside the writable workspace root)."""
        return assert_within_roots(path, [self.root], writable=True, base_dir=self.root)

    def check_file_size(self, path: Path) -> None:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ToolError(
                "access_denied",
                f"无法读取文件信息：{exc}",
                error_key="stat_failed",
            ) from exc
        if size > self.file_max_bytes:
            raise ToolError(
                "input_too_large",
                f"文件超过大小限额（{self.file_max_bytes} bytes）",
                error_key="file_too_large",
                error_detail=f"{path} = {size} bytes",
            )

    def check_content_size(self, content: str) -> None:
        size = len(content.encode("utf-8"))
        if size > self.content_max_bytes:
            raise ToolError(
                "input_too_large",
                f"tree_content 超过大小限额（{self.content_max_bytes} bytes）",
                error_key="content_too_large",
                error_detail=f"{size} bytes",
            )

    # -- run lifecycle ----------------------------------------------------
    def new_run(self, prefix: str = "run_") -> RunStorage:
        run_dir = self.root / f"{prefix}{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return RunStorage(run_dir=run_dir, root=self.root)

    def cleanup(self, keep_runs: Optional[int] = None) -> int:
        """Delete the oldest run directories beyond *keep_runs*.

        Returns the number of removed directories.
        """
        keep = self.keep_runs if keep_runs is None else keep_runs
        def _mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:  # deleted concurrently
                return 0.0

        runs = sorted(
            (p for p in self.root.glob("run_*") if p.is_dir()),
            key=_mtime,
        )
        removed = 0
        for old in runs[:-keep] if keep > 0 else runs:
            try:
                # Never follow a symlink during cleanup: it may point outside
                # the workspace and rmtree would otherwise delete its target.
                if old.is_symlink():
                    old.unlink()
                else:
                    shutil.rmtree(old)
                removed += 1
            except OSError as exc:
                self._log.warning("清理 run 目录失败 %s: %s", old, exc)
        return removed

    def cleanup_older_than(self, age_seconds: float) -> int:
        """Remove run directories older than *age_seconds* (startup sweep)."""
        cutoff = time.time() - age_seconds
        removed = 0
        for p in self.root.glob("run_*"):
            if p.is_dir() and p.stat().st_mtime < cutoff:
                try:
                    if p.is_symlink():
                        p.unlink()
                    else:
                        shutil.rmtree(p)
                    removed += 1
                except OSError:  # pragma: no cover
                    pass
        return removed
