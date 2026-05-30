"""Resolve static ESM imports between mirrored local scripts."""

from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath

from database.database import get_session
from services.scripting.local_script_modules import (
    MAX_LOCAL_MODULES,
    LocalScriptModule,
    _import_allowed,
    _resolve_required_from_index,
    build_module_index,
    iter_pm_require_local_paths_js,
)
from services.scripting.local_script_modules import (
    _scan_local_paths_in_source as _scan_pm_require_paths,
)

_JS_TS_EXTENSIONS = (".js", ".ts", ".cjs")

# Static relative import/export-from (JS and TS — no Esprima; TS-only syntax matches).
_IMPORT_FROM_RE = re.compile(
    r"""(?:^|[;\n}])\s*"""
    r"""(?:import|export)\s+(?:type\s+)?(?:[\w*{}\s,]+?\s+from\s+)?"""
    r"""['"](?P<spec>(?:\./|\.\./)[^'"]+)['"]""",
    re.MULTILINE,
)
_EXPORT_FROM_RE = re.compile(
    r"""(?:^|[;\n}])\s*export\s+(?:type\s+)?(?:\*|\{[^}]*\})\s+from\s+"""
    r"""['"](?P<spec>(?:\./|\.\./)[^'"]+)['"]""",
    re.MULTILINE,
)


def iter_static_relative_import_specs(source: str) -> list[str]:
    """Return unique relative import specifiers from *source*."""
    seen: set[str] = set()
    out: list[str] = []
    for pattern in (_IMPORT_FROM_RE, _EXPORT_FROM_RE):
        for m in pattern.finditer(source):
            spec = m.group("spec").strip()
            if spec and spec not in seen:
                seen.add(spec)
                out.append(spec)
    return out


def import_specifier_at_offset(source: str, offset: int) -> tuple[str, int, int] | None:
    """Return ``(spec, start, end)`` when *offset* is inside a relative import string."""
    for pattern in (_IMPORT_FROM_RE, _EXPORT_FROM_RE):
        for m in pattern.finditer(source):
            spec = m.group("spec")
            start = m.start("spec")
            end = m.end("spec")
            if start <= offset <= end:
                return (spec, start, end)
    return None


def _normalize_rel_path(rel: str) -> str:
    return rel.strip().replace("\\", "/")


def _resolve_specifier(from_rel: str, spec: str) -> str:
    """Resolve *spec* relative to the file at *from_rel* (POSIX paths under local/)."""
    base_dir = PurePosixPath(from_rel).parent
    joined = (base_dir / spec).as_posix()
    normalized = posixpath.normpath(joined)
    if normalized.startswith("../") or normalized == "..":
        raise ValueError(f"import path {spec!r} escapes the local scripts root")
    return normalized


def _resolve_specifier_with_extension(
    spec_resolved: str,
    index: dict[str, LocalScriptModule],
) -> str | None:
    """Return index key for *spec_resolved*, trying common extensions."""
    if spec_resolved in index:
        return spec_resolved
    for ext in _JS_TS_EXTENSIONS:
        candidate = spec_resolved if spec_resolved.endswith(ext) else f"{spec_resolved}{ext}"
        if candidate in index:
            return candidate
    # spec may already include extension but wrong case — exact only
    return None


def _visit_imports_from_module(
    from_rel: str,
    mod: LocalScriptModule,
    language: str,
    index: dict[str, LocalScriptModule],
    reachable: dict[str, LocalScriptModule],
    on_stack: set[str],
) -> None:
    """DFS over static imports and nested pm.require in *mod*."""
    for spec in iter_static_relative_import_specs(mod.source):
        target_key = _resolve_specifier_with_extension(
            _resolve_specifier(from_rel, spec),
            index,
        )
        if target_key is None:
            raise ValueError(
                f"Cannot resolve import {spec!r} from {from_rel!r} "
                "(check the Local scripts tree; paths are case-sensitive)"
            )
        _visit_module(target_key, language, index, reachable, on_stack)

    ext = mod.rel_path[mod.rel_path.rfind(".") :]
    if ext == ".cjs":
        nested_pm = _scan_pm_require_paths(mod.source)
        if nested_pm:
            raise ValueError(
                'pm.require("local:…") is not available inside .cjs local scripts; '
                "use module.exports and import the module from an ESM script instead."
            )
        return

    for nested_path in _scan_pm_require_paths(mod.source):
        _visit_module(nested_path, language, index, reachable, on_stack)


def _visit_module(
    rel_path: str,
    language: str,
    index: dict[str, LocalScriptModule],
    reachable: dict[str, LocalScriptModule],
    on_stack: set[str],
) -> None:
    rel_path = _normalize_rel_path(rel_path)
    mod = index.get(rel_path)
    if mod is None:
        raise ValueError(f"No local script at {rel_path!r}")
    if rel_path in reachable:
        return
    if rel_path in on_stack:
        # ESM cycles are legal at runtime; include the module once without re-walking.
        reachable[rel_path] = mod
        return
    ext = mod.rel_path[mod.rel_path.rfind(".") :]
    if not _import_allowed(language, ext):
        raise ValueError(
            f"Cannot import {mod.rel_path!r} from a {language} script "
            f"(extension {ext!r} not allowed)"
        )
    on_stack.add(rel_path)
    _visit_imports_from_module(rel_path, mod, language, index, reachable, on_stack)
    on_stack.remove(rel_path)
    reachable[rel_path] = mod
    if len(reachable) > MAX_LOCAL_MODULES:
        raise ValueError(f"local module limit ({MAX_LOCAL_MODULES}) exceeded")


def resolve_import_closure(
    entry_rel: str,
    language: str,
    *,
    entry_source: str | None = None,
    module_index: dict[str, LocalScriptModule] | None = None,
) -> dict[str, LocalScriptModule]:
    """Transitive closure from *entry_rel* via static imports + pm.require."""
    entry_rel = _normalize_rel_path(entry_rel)
    if module_index is None:
        with get_session() as session:
            index = build_module_index(session)
    else:
        index = module_index
    if entry_rel not in index:
        raise ValueError(f"No local script at {entry_rel!r}")
    reachable: dict[str, LocalScriptModule] = {}
    on_stack: set[str] = set()
    entry_mod = index[entry_rel]
    source = entry_source if entry_source is not None else entry_mod.source
    on_stack.add(entry_rel)
    for spec in iter_static_relative_import_specs(source):
        target_key = _resolve_specifier_with_extension(
            _resolve_specifier(entry_rel, spec),
            index,
        )
        if target_key is None:
            raise ValueError(
                f"Cannot resolve import {spec!r} from {entry_rel!r} "
                "(check the Local scripts tree; paths are case-sensitive)"
            )
        _visit_module(target_key, language, index, reachable, on_stack)
    for path in iter_pm_require_local_paths_js(source):
        _visit_module(path, language, index, reachable, on_stack)
    on_stack.remove(entry_rel)
    reachable[entry_rel] = entry_mod
    return reachable


def resolve_union_closure(
    entry_rel: str,
    language: str,
    entry_source: str,
    *,
    module_index: dict[str, LocalScriptModule] | None = None,
) -> dict[str, LocalScriptModule]:
    """Merge import-graph and pm.require-only closure for *entry_source*."""
    if module_index is None:
        with get_session() as session:
            module_index = build_module_index(session)
    by_import = resolve_import_closure(
        entry_rel,
        language,
        entry_source=entry_source,
        module_index=module_index,
    )
    by_require = _resolve_required_from_index(entry_source, language, module_index)
    merged = dict(by_require)
    merged.update(by_import)
    if len(merged) > MAX_LOCAL_MODULES:
        raise ValueError(f"local module limit ({MAX_LOCAL_MODULES}) exceeded")
    return merged


def union_source_for_closure(modules: dict[str, LocalScriptModule]) -> str:
    """Concatenate sources for npm/vendor union scans."""
    parts = [m.source for m in sorted(modules.values(), key=lambda m: m.rel_path)]
    return "\n".join(parts)


# Cursor inside an UNCLOSED import/export-from string at end of text_before_cursor.
_IMPORT_FROM_TAIL_RE = re.compile(
    r"""(?:^|[\s;{}])(?:import|export)\b[^'"\n;]*?\bfrom\s*(?P<q>['"])(?P<tail>[^'"\n]*)$"""
)
_IMPORT_BARE_TAIL_RE = re.compile(r"""(?:^|[\s;{}])import\s*(?P<q>['"])(?P<tail>[^'"\n]*)$""")


def esm_import_string_tail(text_before_cursor: str) -> str | None:
    """Return the unclosed import-string tail at the cursor, or ``None``."""
    for pattern in (_IMPORT_FROM_TAIL_RE, _IMPORT_BARE_TAIL_RE):
        m = pattern.search(text_before_cursor)
        if m is not None:
            return m.group("tail")
    return None


def relative_import_suggestions(
    from_rel: str | None,
    typed_prefix: str,
    language: str,
) -> list[str]:
    """Return sibling specifiers (``./x.js`` / ``../d/y.ts``) relative to *from_rel*."""
    if not from_rel:
        return []
    from services.local_script_service import LocalScriptService

    from_dir = posixpath.dirname(from_rel)
    lower = typed_prefix.lower()
    seen: set[str] = set()
    out: list[str] = []
    for cand in LocalScriptService.list_virtual_paths(language=language):
        if cand == from_rel or not cand.endswith(_JS_TS_EXTENSIONS):
            continue
        spec = posixpath.relpath(cand, from_dir or ".")
        if not spec.startswith("."):
            spec = f"./{spec}"
        if lower and not spec.lower().startswith(lower):
            continue
        if spec.lower() in seen:
            continue
        seen.add(spec.lower())
        out.append(spec)

    def _sort_key(s: str) -> tuple[int, str]:
        if s.startswith("../"):
            group = 2
        elif s.startswith("./") and "/" not in s[2:]:
            group = 0  # same directory first
        else:
            group = 1  # ./subdir/…
        return (group, s.lower())

    out.sort(key=_sort_key)
    return out
