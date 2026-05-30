"""Background preparation for local-script Deno LSP attach (mirror + index + closure)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from database.database import get_session
from services.lsp.pm_require_types import sync_pm_require_closure_buffers, sync_pm_require_types
from services.scripting.local_script_modules import LocalScriptModule, build_module_index
from services.scripting.local_scripts_project.import_graph import resolve_union_closure
from services.scripting.local_scripts_project.mirror import (
    mirror_path_for_rel,
    mirror_write_lock,
    sync_closure,
    sync_script_with_index,
)

logger = logging.getLogger(__name__)

# Set False to restore synchronous attach on the GUI thread (rollback).
ASYNC_LOCAL_LSP_PREP = True


@dataclass(frozen=True)
class LocalScriptLspPrepResult:
    """Outcome of :func:`prepare_local_script_lsp_attach` (safe across threads)."""

    ok: bool
    target_uri: str | None
    index_changed: bool
    error_message: str | None
    closure_diagnostic_uris: frozenset[str] = frozenset()


def _rel_path_for_script_id(script_id: int, index: dict[str, LocalScriptModule]) -> str | None:
    for rel, mod in index.items():
        if mod.script_id == script_id:
            return rel
    return None


def prepare_local_script_lsp_attach(
    *,
    script_id: int,
    language: str,
    buffer_text: str,
    workspace: Path,
) -> LocalScriptLspPrepResult:
    """Mirror entry module, import closure, and pm-require index off the GUI thread.

    Does not call :class:`~services.lsp.client.LspClient`. Raises are caught and
    returned as ``ok=False``.
    """
    lang = language.lower().strip()
    if lang not in ("javascript", "typescript"):
        return LocalScriptLspPrepResult(
            ok=False,
            target_uri=None,
            index_changed=False,
            error_message=f"async prep supports JS/TS only, not {language!r}",
        )
    try:
        with mirror_write_lock():
            with get_session() as session:
                index = build_module_index(session)
            mirror_path = sync_script_with_index(script_id, index)
            if mirror_path is None:
                return LocalScriptLspPrepResult(
                    ok=False,
                    target_uri=None,
                    index_changed=False,
                    error_message=f"local script id={script_id} is not mirrored (not JS/TS or path unsafe)",
                )
            target_uri = mirror_path.as_uri()
            entry_rel = _rel_path_for_script_id(script_id, index)
            if entry_rel is None:
                return LocalScriptLspPrepResult(
                    ok=False,
                    target_uri=None,
                    index_changed=False,
                    error_message=f"no virtual path for local script id={script_id}",
                )
            try:
                mods = resolve_union_closure(
                    entry_rel,
                    lang,
                    buffer_text,
                    module_index=index,
                )
            except ValueError as exc:
                return LocalScriptLspPrepResult(
                    ok=False,
                    target_uri=target_uri,
                    index_changed=False,
                    error_message=str(exc),
                )
            sync_closure(mods)
            closure_uris: set[str] = set()
            buffers: list[tuple[str, str]] = []
            for mod in mods.values():
                path = mirror_path_for_rel(mod.rel_path)
                uri = path.as_uri()
                buffers.append((uri, mod.source))
                if uri != target_uri:
                    closure_uris.add(uri)
            index_changed = sync_pm_require_types(
                buffer_text,
                workspace,
                buffer_uri=target_uri,
                module_index=index,
            )
            sync_pm_require_closure_buffers(workspace, buffers)
        return LocalScriptLspPrepResult(
            ok=True,
            target_uri=target_uri,
            index_changed=index_changed,
            error_message=None,
            closure_diagnostic_uris=frozenset(closure_uris),
        )
    except Exception as exc:
        logger.exception("local script LSP prep failed for id=%s", script_id)
        return LocalScriptLspPrepResult(
            ok=False,
            target_uri=None,
            index_changed=False,
            error_message=str(exc),
        )


__all__ = [
    "ASYNC_LOCAL_LSP_PREP",
    "LocalScriptLspPrepResult",
    "prepare_local_script_lsp_attach",
]
