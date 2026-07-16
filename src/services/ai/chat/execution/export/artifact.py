"""Export workspace artifacts for agent execute."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_CONTENT_CAP = 100_000


def run_export_workspace_artifact(
    *,
    kind: str | None,
    history_entry_id: int | None = None,
    run_history_id: int | None = None,
    write_path: str | None = None,
) -> dict[str, Any]:
    """Export test results or collection-run rows as text content."""
    from services.ai.chat.execution.binary.path_policy import validate_binary_path
    from services.request_history_service import RequestHistoryService
    from services.run_export import export_run_results_csv, export_run_results_json
    from services.run_history_service import RunHistoryService
    from services.test_export import export_test_results_json, export_test_results_junit

    artifact_kind = (kind or "").strip()
    if artifact_kind not in {
        "test_results_json",
        "test_results_junit",
        "run_csv",
        "run_json",
    }:
        return {
            "ok": False,
            "error": "invalid_artifact_kind",
            "message": f"Unsupported kind: {kind!r}",
        }

    content = ""
    ids: dict[str, int] = {}
    summary = ""

    if artifact_kind in {"test_results_json", "test_results_junit"}:
        if history_entry_id is None:
            return {
                "ok": False,
                "error": "history_entry_id_required",
                "message": "history_entry_id required for test result export",
            }
        entry = RequestHistoryService.get_entry(history_entry_id)
        if entry is None:
            return {
                "ok": False,
                "error": "history_not_found",
                "message": f"id={history_entry_id}",
            }
        response = entry.get("response") if isinstance(entry, dict) else None
        tests: list[Any] | None = None
        if isinstance(response, dict):
            raw = response.get("test_results")
            if isinstance(raw, list):
                tests = raw
        if not tests:
            snap = entry.get("original_request") if isinstance(entry, dict) else None
            if isinstance(snap, dict):
                raw2 = snap.get("test_results")
                if isinstance(raw2, list):
                    tests = raw2
        if not tests:
            raw3 = entry.get("test_results") if isinstance(entry, dict) else None
            if isinstance(raw3, list):
                tests = raw3
        if not tests:
            return {
                "ok": False,
                "error": "empty_test_results",
                "message": "No test results on history entry",
            }
        suite = str(entry.get("request_name") or f"history-{history_entry_id}")
        if artifact_kind == "test_results_json":
            content = export_test_results_json(tests)
        else:
            content = export_test_results_junit(tests, suite_name=suite)
        ids["history_entry_id"] = int(history_entry_id)
        summary = f"Exported {artifact_kind} from history #{history_entry_id}"
    else:
        if run_history_id is None:
            return {
                "ok": False,
                "error": "run_history_id_required",
                "message": "run_history_id required for run export",
            }
        results = RunHistoryService.get_run_results(run_history_id)
        if not results:
            return {
                "ok": False,
                "error": "empty_run_results",
                "message": "No results on run history",
            }
        if artifact_kind == "run_csv":
            content = export_run_results_csv(results)
        else:
            content = export_run_results_json(results)
        ids["run_history_id"] = int(run_history_id)
        summary = f"Exported {artifact_kind} from run #{run_history_id}"

    if write_path:
        path, err = validate_binary_path(write_path)
        if err or path is None:
            return {"ok": False, "error": err or "binary_path_not_allowed", "message": write_path}
        try:
            Path(path).write_text(content, encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": "write_failed", "message": str(exc)}

    preview = content
    if len(preview) > _CONTENT_CAP:
        preview = preview[:_CONTENT_CAP] + "\n… (truncated)"

    return {
        "ok": True,
        "summary": summary,
        "artifact_kind": artifact_kind,
        "content": preview,
        "ids": ids,
        "warnings": ["wrote_file"] if write_path else [],
    }
