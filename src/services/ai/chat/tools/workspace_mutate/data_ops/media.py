"""Snippet and saved-response mutate ops."""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.bridge import OpenTargetDict
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)
from services.ai.chat.tools.workspace_mutate.data_ops.common import _finish


def _apply_snippet(
    *,
    verb: str,
    target_id: int | None,
    fields: dict[str, Any],
    mutation_id: str,
    open_after: bool,
) -> WorkspaceMutateObservation:
    from services.snippet_service import SnippetService

    ids: dict[str, int] = {}
    if verb == "create":
        name = str(fields.get("name") or "").strip()
        language = str(fields.get("language") or "javascript")
        body = str(fields.get("body") or "")
        category = str(fields.get("category") or "My snippets")
        context = str(fields.get("context") or "both")
        new_id = SnippetService.create(
            name=name,
            language=language,
            body=body,
            category=category,
            context=context,
        )
        ids["snippet_id"] = int(new_id)
        summary = f"Created snippet {name!r}"
    elif verb == "update":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        kwargs: dict[str, Any] = {}
        if "name" in fields:
            kwargs["name"] = str(fields["name"])
        if "body" in fields:
            kwargs["body"] = str(fields["body"])
        if "category" in fields:
            kwargs["category"] = str(fields["category"])
        if "context" in fields:
            kwargs["context"] = str(fields["context"])
        SnippetService.update(target_id, **kwargs)
        ids["snippet_id"] = int(target_id)
        summary = f"Updated snippet {target_id}"
    elif verb == "rename":
        # Category rename: fields.name is new category, fields.category is old,
        # language required. Single-snippet rename uses target_id + name.
        if target_id is not None:
            name = str(fields.get("name") or "").strip()
            if not name:
                return mutate_obs("ok: false\nerror: name_required\n")
            SnippetService.update(target_id, name=name)
            ids["snippet_id"] = int(target_id)
            summary = f"Renamed snippet to {name!r}"
        else:
            language = str(fields.get("language") or "").strip()
            old_cat = str(fields.get("category") or "").strip()
            new_cat = str(fields.get("name") or "").strip()
            if not language or not old_cat or not new_cat:
                return mutate_obs("ok: false\nerror: language_category_and_name_required\n")
            count = SnippetService.rename_category(language, old_cat, new_cat)
            summary = f"Renamed snippet category {old_cat!r} → {new_cat!r} ({count})"
    elif verb == "delete":
        if target_id is not None:
            SnippetService.delete(target_id)
            ids["snippet_id"] = int(target_id)
            summary = f"Deleted snippet {target_id}"
        else:
            language = str(fields.get("language") or "").strip()
            category = str(fields.get("category") or "").strip()
            if not language or not category:
                return mutate_obs("ok: false\nerror: language_and_category_required\n")
            count = SnippetService.delete_snippets_in_category(language, category)
            summary = f"Deleted {count} snippet(s) in category {category!r}"
    else:
        return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
    del open_after
    return _finish(
        mutation_id=mutation_id,
        verb=verb,
        entity="snippet",
        ids=ids,
        summary=summary,
        warnings=[],
        open_after=False,
        open_target=None,
    )


def _apply_saved_response(
    *,
    verb: str,
    target_id: int | None,
    collection_id: int | None,
    fields: dict[str, Any],
    mutation_id: str,
    open_after: bool,
) -> WorkspaceMutateObservation:
    from services.collection_service import CollectionService
    from services.request_history_service import (
        entry_to_http_response_dict,
        get_entry,
    )

    ids: dict[str, int] = {}
    open_target: OpenTargetDict | None = None
    if verb == "create":
        history_entry_id = fields.get("history_entry_id")
        request_id = fields.get("request_id") or collection_id
        name = str(fields.get("name") or "Example").strip() or "Example"
        if isinstance(history_entry_id, int) and history_entry_id > 0:
            entry = get_entry(history_entry_id)
            if entry is None:
                return mutate_obs("ok: false\nerror: history_entry_not_found\n")
            rid = entry.get("request_id")
            if not isinstance(rid, int) or rid <= 0:
                return mutate_obs("ok: false\nerror: history_has_no_request\n")
            http = entry_to_http_response_dict(entry)
            body = http.get("body")
            new_id = CollectionService.save_response(
                rid,
                name,
                http.get("status_text") if isinstance(http.get("status_text"), str) else None,
                http.get("status_code") if isinstance(http.get("status_code"), int) else None,
                http.get("headers") or [],
                body if isinstance(body, str) else None,
            )
            ids["saved_response_id"] = int(new_id)
            ids["request_id"] = int(rid)
            open_target = {"kind": "request", "id": int(rid)}
            summary = f"Saved example {name!r} from history #{history_entry_id}"
        elif isinstance(request_id, int) and request_id > 0:
            new_id = CollectionService.save_response(
                request_id,
                name,
                fields.get("status") if isinstance(fields.get("status"), str) else None,
                fields.get("code") if isinstance(fields.get("code"), int) else None,
                fields.get("headers") or [],
                fields.get("body") if isinstance(fields.get("body"), str) else None,
                preview_language=(
                    str(fields["preview_language"])
                    if fields.get("preview_language") is not None
                    else None
                ),
            )
            ids["saved_response_id"] = int(new_id)
            ids["request_id"] = int(request_id)
            open_target = {"kind": "request", "id": int(request_id)}
            summary = f"Saved example {name!r} on request {request_id}"
        else:
            return mutate_obs("ok: false\nerror: history_entry_id_or_request_id_required\n")
    elif verb == "rename":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        name = str(fields.get("name") or "").strip()
        if not name:
            return mutate_obs("ok: false\nerror: name_required\n")
        CollectionService.rename_saved_response(target_id, name)
        ids["saved_response_id"] = int(target_id)
        summary = f"Renamed saved response to {name!r}"
    elif verb == "duplicate":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        new_id = CollectionService.duplicate_saved_response(target_id)
        ids["saved_response_id"] = int(new_id)
        summary = f"Duplicated saved response {target_id} → {new_id}"
    elif verb == "delete":
        if target_id is None:
            return mutate_obs("ok: false\nerror: target_id_required\n")
        CollectionService.delete_saved_response(target_id)
        ids["saved_response_id"] = int(target_id)
        summary = f"Deleted saved response {target_id}"
    else:
        return mutate_obs(f"ok: false\nerror: unsupported_action\naction: {verb}\n")
    return _finish(
        mutation_id=mutation_id,
        verb=verb,
        entity="saved_response",
        ids=ids,
        summary=summary,
        warnings=[],
        open_after=open_after,
        open_target=open_target,
    )
