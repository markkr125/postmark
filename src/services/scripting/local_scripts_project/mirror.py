"""Mirror DB-backed local scripts into the Deno LSP workspace ``local/`` tree."""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

from database.database import get_session
from services.lsp.servers._workspace import ensure_js_workspace
from services.scripting.local_script_modules import (
    LocalScriptModule,
    build_module_index,
    lookup_rel_path_by_script_id,
)

_JS_TS_EXTENSIONS = frozenset({".js", ".ts", ".cjs"})

# Serialize mirror writes when multiple local-script LSP prep workers run concurrently.
_MIRROR_WRITE_LOCK = threading.RLock()


def mirror_write_lock() -> threading.RLock:
    """Return the process-wide lock for ``local/`` mirror tree writes."""
    return _MIRROR_WRITE_LOCK


def local_mirror_root() -> Path:
    """Return ``<js_workspace>/local`` (created)."""
    root = ensure_js_workspace() / "local"
    root.mkdir(parents=True, exist_ok=True)
    return root


def rel_path_for_script_id(script_id: int) -> str | None:
    """Map a script primary key to its virtual path under ``local/``."""
    return lookup_rel_path_by_script_id(script_id)


def mirror_path_for_rel(rel_path: str) -> Path:
    """Absolute path for a virtual ``local/`` file."""
    return local_mirror_root() / rel_path


def mirror_path_for_script_id(script_id: int) -> Path | None:
    """Absolute mirror path for *script_id*, or ``None`` if not path-safe."""
    rel = rel_path_for_script_id(script_id)
    if rel is None:
        return None
    return mirror_path_for_rel(rel)


def _should_mirror(mod: LocalScriptModule) -> bool:
    ext = mod.rel_path[mod.rel_path.rfind(".") :]
    return ext in _JS_TS_EXTENSIONS


def _write_module(mod: LocalScriptModule) -> None:
    """Write one module file (caller must hold :func:`mirror_write_lock` when needed)."""
    dest = mirror_path_for_rel(mod.rel_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = mod.source if mod.source.endswith("\n") else f"{mod.source}\n"
    dest.write_text(body, encoding="utf-8", newline="\n")


def sync_script_with_index(
    script_id: int,
    index: dict[str, LocalScriptModule],
) -> Path | None:
    """Write one script using a pre-built *index*; return path or ``None``."""
    for rel, mod in index.items():
        if mod.script_id != script_id:
            continue
        if not _should_mirror(mod):
            return None
        _write_module(mod)
        return mirror_path_for_rel(rel)
    return None


def sync_script(script_id: int) -> Path | None:
    """Write one script to the mirror; return path or ``None`` if not mirrored."""
    with _MIRROR_WRITE_LOCK:
        with get_session() as session:
            index = build_module_index(session)
        return sync_script_with_index(script_id, index)


def sync_closure(modules: dict[str, LocalScriptModule]) -> set[str]:
    """Mirror every JS/TS module in *modules*; return mirrored rel paths."""
    with _MIRROR_WRITE_LOCK:
        written: set[str] = set()
        for mod in modules.values():
            if not _should_mirror(mod):
                continue
            _write_module(mod)
            written.add(mod.rel_path)
        return written


def remove_mirrored_script(script_id: int) -> None:
    """Delete the mirror file for *script_id* if it exists."""
    path = mirror_path_for_script_id(script_id)
    if path is None or not path.is_file():
        return
    path.unlink()
    parent = path.parent
    with contextlib.suppress(OSError):
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


def prune_orphans(index: dict[str, LocalScriptModule] | None = None) -> list[str]:
    """Delete mirror files with no corresponding DB row; return removed rel paths."""
    if index is None:
        with get_session() as session:
            index = build_module_index(session)
    allowed = {rel for rel, mod in index.items() if _should_mirror(mod)}
    root = local_mirror_root()
    removed: list[str] = []
    if not root.is_dir():
        return removed
    for path in sorted(root.rglob("*"), reverse=True):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in allowed:
            path.unlink()
            removed.append(rel)
    _prune_empty_dirs(root)
    return removed


def _prune_empty_dirs(root: Path) -> None:
    """Remove empty directories under *root* (bottom-up)."""
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and path != root and not any(path.iterdir()):
            path.rmdir()


def sync_all() -> None:
    """Rewrite the full JS/TS mirror from the database and prune orphans."""
    with _MIRROR_WRITE_LOCK:
        with get_session() as session:
            index = build_module_index(session)
        for mod in index.values():
            if _should_mirror(mod):
                _write_module(mod)
        prune_orphans(index)
