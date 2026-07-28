"""Shared ImportService apply path for ``postmark_import``.

Bridge / audit events still use ``entity: import`` so the GUI drain refreshes
the collection tree after an approved import.
"""

from __future__ import annotations

from typing import Any

from services.ai.chat.mutation.audit import append_mutation_audit
from services.ai.chat.mutation.bridge import enqueue_mutation_event
from services.ai.chat.tools.workspace_mutate.common import (
    WorkspaceMutateObservation,
    mutate_obs,
)


def apply_workspace_import(
    *,
    fields: dict[str, Any],
    mutation_id: str,
    collection_name_suffix: str = "",
) -> WorkspaceMutateObservation:
    """Import collections/environments, optionally suffixing root collection names."""
    from pathlib import Path

    from services.import_service import ImportService

    try:
        if "text" in fields:
            summary_dict = ImportService.import_text(str(fields["text"]))
        elif "curl" in fields:
            summary_dict = ImportService.import_curl(str(fields["curl"]))
        elif "url" in fields:
            summary_dict = ImportService.import_url(str(fields["url"]))
        elif "path" in fields:
            path = Path(str(fields["path"]))
            if path.is_dir():
                summary_dict = ImportService.import_folder(path)
            else:
                summary_dict = ImportService.import_files([path])
        else:
            return mutate_obs("ok: false\nerror: import_source_required\n")
    except Exception as exc:
        return mutate_obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")

    env_count = int(summary_dict.get("environments_imported") or 0)
    coll_count = int(summary_dict.get("collections_imported") or 0)
    req_count = int(summary_dict.get("requests_imported") or 0)
    errors = list(summary_dict.get("errors") or [])
    created = [
        {"id": int(ref["id"]), "name": str(ref["name"])}
        for ref in (summary_dict.get("imported_collections") or [])
        if isinstance(ref, dict) and ref.get("id")
    ]
    suffix = collection_name_suffix.strip()
    rename_warnings: list[str] = []
    if suffix and created:
        from services.collection_service import CollectionService

        for ref in created:
            collection_id = ref["id"]
            if not isinstance(collection_id, int):
                continue
            old_name = str(ref["name"]).strip()
            new_name = f"{old_name} {suffix}".strip()
            try:
                CollectionService.rename_collection(collection_id, new_name)
                ref["name"] = new_name
            except Exception as exc:
                rename_warnings.append(
                    f"Could not rename imported collection {ref['id']}: {type(exc).__name__}"
                )
    collection_links = [f"[{ref['name']}](postmark://collection/{ref['id']})" for ref in created]
    summary = (
        f"Imported {coll_count} collection(s), {req_count} request(s), {env_count} environment(s)"
    )
    if suffix and created and not rename_warnings:
        summary += f"; added {suffix!r} to {len(created)} root collection name(s)"
    warnings = [str(e) for e in errors[:10]] + rename_warnings
    enqueue_mutation_event(
        {
            "type": "mutated",
            "entity": "import",
            "action": "create",
            "ids": {},
            "warnings": warnings,
            "payload": {
                "environments_imported": env_count,
                "collections_imported": coll_count,
                "requests_imported": req_count,
            },
        }
    )
    append_mutation_audit(
        {
            "mutation_id": mutation_id,
            "action": "create",
            "entity": "import",
            "ids": {},
            "summary": summary,
        }
    )
    lines = [
        "ok: true",
        f"mutation_id: {mutation_id}",
        f"summary: {summary}",
        "action: create",
        "entity: import",
        f"collections_imported: {coll_count}",
        f"requests_imported: {req_count}",
        f"environments_imported: {env_count}",
    ]
    if created:
        lines.append(f"imported_collections: {created}")
        lines.append(f"collection_links: {collection_links}")
        lines.append(
            "next_step: Import is complete. Do not import this source again in this turn; "
            "use imported_collections and collection_links for any follow-up."
        )
    if warnings:
        lines.append(f"errors: {warnings}")
    return mutate_obs("\n".join(lines) + "\n")
