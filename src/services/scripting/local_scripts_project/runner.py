"""Run and debug local script tabs as Deno entry modules over the import closure."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from services.lsp.servers._workspace import ensure_js_workspace
from services.scripting.deno_runtime import (
    _DENO_DRAIN_FILE,
    _NODE_FS_IMPORT,
    _append_user_script_line0,
    _apply_done_line,
    _empty_output,
    _error_output,
    _ipc_subprocess,
    _pm_require_imports_block,
)
from services.scripting.js_runtime import append_js_pm_preamble, prepare_pm_require_bundle
from services.scripting.local_scripts_project.import_graph import (
    resolve_union_closure,
    union_source_for_closure,
)
from services.scripting.local_scripts_project.mirror import (
    mirror_path_for_rel,
    rel_path_for_script_id,
    sync_closure,
)
from services.scripting.runtime_settings import RuntimeSettings

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput
    from services.scripting.debug.protocol import DebugProtocol

_DEBUG_BASELINE = (
    "var __pm_baseline_json = JSON.stringify(Object.getOwnPropertyNames(globalThis).sort());\n"
    "if (typeof globalThis !== 'undefined') { globalThis.__pm_baseline_json = __pm_baseline_json; }\n"
)


def local_script_id_from_context(context: ScriptInput) -> int | None:
    """Return ``localScriptId`` from ``context['info']`` when set."""
    info = context.get("info")
    if not isinstance(info, dict):
        return None
    raw = info.get("localScriptId")
    return int(raw) if isinstance(raw, int) else None


def _build_preamble_parts(
    union_source: str,
    context: ScriptInput,
    *,
    language: str,
) -> tuple[list[str], bool, dict[str, Any]]:
    """Shared npm/vendor/context/bootstrap preamble for local entry runs."""
    from services.scripting.js_runtime import _detect_pm_require_specs as _detect_specs

    parts: list[str] = [_NODE_FS_IMPORT]
    try:
        _union, needs_net, local_mods = prepare_pm_require_bundle(union_source, language=language)
        specs = _detect_specs(_union)
    except ValueError as exc:
        raise RuntimeError(f"Script bundling failed: {exc}") from exc
    parts.append(_pm_require_imports_block(specs, local_mods))
    append_js_pm_preamble(parts, union_source, context, include_json_schema=True)
    return parts, needs_net, local_mods


def build_local_entry_bundle_text(
    union_source: str,
    context: ScriptInput,
    *,
    language: str,
    entry_uri: str,
    debug: bool = False,
) -> tuple[str, bool, dict[str, Any]]:
    """Preamble + dynamic ``import()`` of the mirrored entry module + drain."""
    parts, needs_net, local_mods = _build_preamble_parts(union_source, context, language=language)
    if debug:
        parts.append(_DEBUG_BASELINE)
    _append_user_script_line0(parts)
    parts.append(f"await import({json.dumps(entry_uri)});\n;\n")
    parts.append(_DENO_DRAIN_FILE.read_text(encoding="utf-8"))
    return "\n".join(parts), needs_net, local_mods


def _prepare_closure(
    script_id: int,
    entry_source: str,
    language: str,
) -> tuple[str, Path, dict[str, Any]]:
    """Sync mirror closure; return entry rel path, mirror path, and module map."""
    rel = rel_path_for_script_id(script_id)
    if rel is None:
        raise ValueError(f"Local script {script_id} has no mirror path")
    mods = resolve_union_closure(rel, language, entry_source=entry_source)
    sync_closure(mods)
    entry_path = mirror_path_for_rel(rel)
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(entry_source, encoding="utf-8", newline="\n")
    return rel, entry_path, mods


def run_local_entry(
    script_id: int,
    entry_source: str,
    language: str,
    context: ScriptInput,
) -> ScriptOutput:
    """Execute a local script tab as the Deno entry module over its import closure."""
    start = time.monotonic()
    deno = RuntimeSettings.deno_path()
    st = RuntimeSettings.validate_deno(deno)
    if not st["available"]:
        return _error_output(
            "Deno is not available. Open Settings, set the Deno path, or download the "
            "managed runtime. " + (st.get("error") or ""),
            (time.monotonic() - start) * 1000,
        )
    try:
        _rel, entry_path, mods = _prepare_closure(script_id, entry_source, language)
        union = union_source_for_closure(mods)
        text, needs_net, _local_mods = build_local_entry_bundle_text(
            union,
            context,
            language=language,
            entry_uri=entry_path.resolve().as_uri(),
            debug=False,
        )
    except (ValueError, RuntimeError) as exc:
        return _error_output(str(exc), (time.monotonic() - start) * 1000)

    ws = ensure_js_workspace()
    ext = "ts" if language == "typescript" else "mjs"
    out = _empty_output()
    try:
        with tempfile.TemporaryDirectory(prefix="postmark-local-") as tdir:
            bundle = Path(tdir) / f"bundle.{ext}"
            bundle.write_text(text, encoding="utf-8")
            dline, err_tail = _ipc_subprocess(
                Path(st["path"]),
                bundle,
                context,
                needs_net=needs_net,
                extra_read_paths=(str(ws.resolve()),),
            )
            if dline is not None:
                _apply_done_line(dline, out, context)
                return cast("ScriptOutput", out)
            from services.scripting.es_module_rules import format_process_stderr

            detail = format_process_stderr(err_tail)
            msg = (
                "Deno did not print a result line (the process may have crashed or been killed)."
                + (f" Deno said: {detail}" if detail else "")
            )
            return _error_output(msg, (time.monotonic() - start) * 1000)
    except OSError as exc:
        return _error_output(str(exc), (time.monotonic() - start) * 1000)


def debug_local_entry(
    script_id: int,
    entry_source: str,
    language: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    *,
    script_type: str = "pre_request",
    source_name: str = "",
) -> ScriptOutput:
    """Step-through debug with breakpoints mapped to the mirrored entry file URL."""
    from services.scripting.debug.deno_debug import debug_execute

    t0 = time.monotonic()
    try:
        _rel, entry_path, mods = _prepare_closure(script_id, entry_source, language)
        union = union_source_for_closure(mods)
        entry_uri = entry_path.resolve().as_uri()
        bundle_text, needs_net, _mods = build_local_entry_bundle_text(
            union,
            context,
            language=language,
            entry_uri=entry_uri,
            debug=True,
        )
    except (ValueError, RuntimeError) as exc:
        return _error_output(str(exc), (time.monotonic() - t0) * 1000)

    ws = ensure_js_workspace()
    return debug_execute(
        entry_source,
        context,
        protocol,
        script_type=script_type,
        source_name=source_name,
        language=language,
        preamble_bundle_text=bundle_text,
        needs_net=needs_net,
        breakpoint_url=entry_uri,
        user_first_line_0=0,
        extra_read_paths=(str(ws.resolve()),),
    )
