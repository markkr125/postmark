"""Resolve ``pm.require("local:…")`` against DB-backed local scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import get_session
from database.models.local_scripts.model.local_script_folder_model import LocalScriptFolderModel
from database.models.local_scripts.model.local_script_model import LocalScriptModel
from database.models.local_scripts.path_policy import (
    is_path_safe_folder_name,
    is_path_safe_script_basename,
)
from database.models.local_scripts.virtual_paths import (
    MODULE_FORMAT_ESM,
    _script_basename_from_stored,
    script_virtual_extension,
)

MAX_LOCAL_MODULES = 500

_PM_REQUIRE_LOCAL_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]local:(?P<path>[^'"]+)['"]\s*\)""",
)


@dataclass(frozen=True)
class LocalScriptModule:
    """One local script module keyed by virtual path."""

    rel_path: str
    language: str
    source: str
    script_id: int


def iter_pm_require_local_paths_js(source: str) -> list[str]:
    """Return unique ``local:`` path strings from *source* (JS/TS)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _PM_REQUIRE_LOCAL_RE.finditer(source):
        path = m.group("path").strip()
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def iter_pm_require_local_paths_py(source: str) -> list[str]:
    """Return unique ``local:`` path strings from *source* (Python)."""
    return iter_pm_require_local_paths_js(source)


def _import_allowed(user_language: str, module_ext: str) -> bool:
    code = (user_language or "javascript").strip().lower()
    if code in ("python", "py"):
        return module_ext == ".py"
    if code in ("typescript", "ts"):
        return module_ext in (".js", ".ts", ".cjs")
    return module_ext in (".js", ".ts", ".cjs")


def _scan_local_paths_in_source(source: str) -> list[str]:
    return iter_pm_require_local_paths_js(source)


def build_module_index(session: Session) -> dict[str, LocalScriptModule]:
    """Build ``rel_path`` → module for path-safe scripts (raises on duplicates)."""
    folder_names_by_id: dict[int, list[str]] = {}
    folder_stmt = select(
        LocalScriptFolderModel.id,
        LocalScriptFolderModel.name,
        LocalScriptFolderModel.parent_id,
    )
    folders: dict[int, tuple[str, int | None]] = {}
    for fid, fname, pid in session.execute(folder_stmt):
        folders[fid] = (fname, pid)

    def names_for(fid: int) -> list[str]:
        if fid in folder_names_by_id:
            return folder_names_by_id[fid]
        fname, pid = folders[fid]
        chain = [*names_for(pid), fname] if pid is not None and pid in folders else [fname]
        folder_names_by_id[fid] = chain
        return chain

    script_stmt = select(
        LocalScriptModel.id,
        LocalScriptModel.folder_id,
        LocalScriptModel.name,
        LocalScriptModel.language,
        LocalScriptModel.module_format,
        LocalScriptModel.content,
    )
    index: dict[str, LocalScriptModule] = {}
    for sid, folder_id, sname, slang, mod_fmt, content in session.execute(script_stmt):
        if folder_id not in folders:
            continue
        chain = names_for(folder_id)
        basename = _script_basename_from_stored(sname)
        lang = slang or "javascript"
        if not is_path_safe_script_basename(basename, lang):
            continue
        if not all(is_path_safe_folder_name(n) for n in chain):
            continue
        fmt = mod_fmt or MODULE_FORMAT_ESM
        ext = script_virtual_extension(lang, fmt)
        filename = f"{basename}{ext}"
        rel = "/".join(chain) + "/" + filename if chain else filename
        if rel in index:
            raise ValueError(f"Duplicate local script path {rel!r} in database")
        index[rel] = LocalScriptModule(
            rel_path=rel,
            language=lang,
            source=content or "",
            script_id=sid,
        )
    return index


def resolve_required(user_source: str, language: str) -> dict[str, LocalScriptModule]:
    """Transitive closure of local modules reachable from *user_source*."""
    with get_session() as session:
        index = build_module_index(session)
    return _resolve_required_from_index(user_source, language, index)


def _resolve_required_from_index(
    user_source: str,
    language: str,
    index: dict[str, LocalScriptModule],
) -> dict[str, LocalScriptModule]:
    """DFS transitive resolve using a pre-built *index*."""
    # Deferred import: ``import_graph`` imports this module at top level.
    from services.scripting.local_scripts_project.import_graph import (
        _resolve_specifier,
        _resolve_specifier_with_extension,
        iter_static_relative_import_specs,
    )

    reachable: dict[str, LocalScriptModule] = {}
    on_stack: set[str] = set()

    def visit(rel_path: str) -> None:
        if rel_path in reachable:
            return
        if rel_path in on_stack:
            raise ValueError(f"pm.require: local script import cycle detected at {rel_path!r}")
        mod = index.get(rel_path)
        if mod is None:
            raise ValueError(
                f"pm.require: no local script at {rel_path!r} "
                "(check the Local scripts tree; paths are case-sensitive and path-safe)"
            )
        ext = mod.rel_path[mod.rel_path.rfind(".") :]
        if not _import_allowed(language, ext):
            raise ValueError(
                f"pm.require: cannot import {mod.rel_path!r} "
                f"from a {script_virtual_extension(language)} script"
            )
        on_stack.add(rel_path)
        if ext == ".cjs":
            nested_paths = _scan_local_paths_in_source(mod.source)
            if nested_paths:
                raise ValueError(
                    'pm.require("local:…") is not available inside .cjs local scripts; '
                    "use module.exports and import the module from an ESM pre-request "
                    "or test script instead."
                )
        else:
            for nested_path in _scan_local_paths_in_source(mod.source):
                visit(nested_path)
            # Follow static ESM imports too, so a required module's sibling deps
            # are mirrored (matches the editor-run closure in import_graph).
            for spec in iter_static_relative_import_specs(mod.source):
                target_key = _resolve_specifier_with_extension(
                    _resolve_specifier(rel_path, spec),
                    index,
                )
                if target_key is None:
                    raise ValueError(
                        f"pm.require: cannot resolve import {spec!r} from {rel_path!r} "
                        "(check the Local scripts tree; paths are case-sensitive)"
                    )
                visit(target_key)
        on_stack.remove(rel_path)
        reachable[rel_path] = mod
        if len(reachable) > MAX_LOCAL_MODULES:
            raise ValueError(f"pm.require: local module limit ({MAX_LOCAL_MODULES}) exceeded")

    for path in _scan_local_paths_in_source(user_source):
        visit(path)
    return reachable


def lookup_script_id_by_rel_path(rel_path: str) -> int | None:
    """Map a virtual path to a DB script id, or ``None`` if missing."""
    with get_session() as session:
        index = build_module_index(session)
    mod = index.get(rel_path.strip())
    return mod.script_id if mod is not None else None


def lookup_rel_path_by_script_id(script_id: int) -> str | None:
    """Map a database script id to its virtual path, or ``None`` if missing."""
    with get_session() as session:
        index = build_module_index(session)
    for rel_path, mod in index.items():
        if mod.script_id == script_id:
            return rel_path
    return None


def local_require_path_at_offset(source: str, offset: int) -> tuple[str, int, int] | None:
    """Return ``(rel_path, start, end)`` when *offset* is inside ``pm.require('local:…')``."""
    for m in _PM_REQUIRE_LOCAL_RE.finditer(source):
        path = m.group("path")
        start = m.start("path")
        end = m.end("path")
        if start <= offset <= end:
            return (path, start, end)
    return None
