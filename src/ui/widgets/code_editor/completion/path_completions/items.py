"""Completion items for path strings: pm.require('local:…') and ESM imports."""

from __future__ import annotations

from ui.widgets.code_editor.completion.engine import CompletionItem


def local_require_completion_items(
    path_prefix: str,
    language: str,
    *,
    prefix_local: bool = False,
) -> list[CompletionItem]:
    """Return virtual-path completions for ``pm.require('local:…')``."""
    from services.local_script_service import LocalScriptService

    paths = LocalScriptService.list_virtual_paths(language=language)
    lower = path_prefix.lower()
    items: list[CompletionItem] = []
    seen_labels: set[str] = set()

    def _insert_text(rel: str) -> str:
        return f"local:{rel}" if prefix_local else rel

    # Offer folder prefixes (e.g. ``auth/``) when typing a partial path.
    if path_prefix and not path_prefix.endswith("/"):
        dir_prefix = lower
        if "/" in dir_prefix:
            dir_prefix = dir_prefix.rsplit("/", 1)[0] + "/"
        else:
            dir_prefix = f"{dir_prefix}/" if dir_prefix else ""
        folder_hints: set[str] = set()
        for rel in paths:
            rl = rel.lower()
            if dir_prefix and rl.startswith(dir_prefix):
                rest = rl[len(dir_prefix) :]
                if "/" in rest:
                    folder_hints.add(rel[: len(dir_prefix) + rest.index("/") + 1])
        for hint in sorted(folder_hints):
            if hint.lower() in seen_labels:
                continue
            seen_labels.add(hint.lower())
            items.append(
                CompletionItem(
                    label=hint,
                    kind="folder",
                    type_str="local folder",
                    doc=f"Local scripts under {hint}",
                    signature="",
                    insert_text=_insert_text(hint),
                )
            )

    for rel in paths:
        if lower and not rel.lower().startswith(lower):
            continue
        if rel.lower() in seen_labels:
            continue
        seen_labels.add(rel.lower())
        items.append(
            CompletionItem(
                label=rel,
                kind="module",
                type_str="local script",
                doc=f"Local script: local:{rel}",
                signature="",
                insert_text=_insert_text(rel),
            )
        )
    return items


def is_esm_import_context(text_before_cursor: str, language: str) -> bool:
    """True when the cursor is in a relative ESM import string (JS/TS only)."""
    if language not in ("javascript", "typescript"):
        return False
    from services.scripting.local_scripts_project.import_graph import esm_import_string_tail

    tail = esm_import_string_tail(text_before_cursor)
    return tail is not None and (tail == "" or tail.startswith("."))


def esm_import_completion_items(
    text_before_cursor: str,
    language: str,
    script_id: int | None,
) -> list[CompletionItem]:
    """Return sibling-path completions for a relative ESM import."""
    if script_id is None:
        return []
    from services.scripting.local_scripts_project.import_graph import (
        esm_import_string_tail,
        relative_import_suggestions,
    )
    from services.scripting.local_scripts_project.mirror import rel_path_for_script_id

    tail = esm_import_string_tail(text_before_cursor) or ""
    from_rel = rel_path_for_script_id(script_id)
    return [
        CompletionItem(
            label=spec,
            kind="module",
            type_str="local script",
            doc=f"Import {spec}",
            signature="",
            insert_text=spec,
        )
        for spec in relative_import_suggestions(from_rel, tail, language)
    ]
