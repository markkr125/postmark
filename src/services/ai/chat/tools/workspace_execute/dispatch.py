"""Dispatch ``postmark_workspace_execute`` operations to execution helpers."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.ai.chat.tools.workspace_execute.tool import (
    WorkspaceExecuteAction,
    WorkspaceExecuteObservation,
)


def _obs(text: str) -> WorkspaceExecuteObservation:
    """Build an observation from plain text."""
    return WorkspaceExecuteObservation.from_text(text)


def execute_workspace_action(action: WorkspaceExecuteAction) -> WorkspaceExecuteObservation:
    """Dispatch execute operations and enqueue bridge / audit events."""
    from services.ai.chat.mutation.audit import append_mutation_audit
    from services.ai.chat.mutation.bridge import enqueue_mutation_event

    execution_id = uuid4().hex[:12]
    try:
        result = _dispatch_operation(action)
        if isinstance(result, WorkspaceExecuteObservation):
            return result
    except Exception as exc:
        return _obs(f"ok: false\nerror: {type(exc).__name__}\nmessage: {exc}\n")

    if not result.get("ok"):
        return _obs(
            "ok: false\n"
            f"execution_id: {execution_id}\n"
            f"error: {result.get('error', 'failed')}\n"
            f"message: {result.get('message', '')}\n"
        )

    return _finish_success(
        action, execution_id, result, enqueue_mutation_event, append_mutation_audit
    )


def _dispatch_operation(
    action: WorkspaceExecuteAction,
) -> dict[str, Any] | WorkspaceExecuteObservation:
    """Run the matching execute helper; return an observation on validation errors."""
    from services.ai.chat.execution.agent_local_script import run_agent_local_script
    from services.ai.chat.execution.agent_send import (
        run_agent_replay_history,
        run_agent_scripts,
        run_agent_send_draft,
        run_agent_send_request,
    )
    from services.ai.chat.execution.runner import run_agent_collection, run_agent_iterations

    def _as_dict(result: Any) -> dict[str, Any]:
        return dict(result) if not isinstance(result, dict) else result

    if action.operation == "send_request":
        if action.request_id is None:
            return _obs("ok: false\nerror: request_id_required\n")
        return _as_dict(
            run_agent_send_request(
                request_id=action.request_id,
                environment_id=action.environment_id,
                persist_globals=action.persist_globals,
                record_history=action.record_history,
                include_scripts=action.include_scripts,
            )
        )
    if action.operation == "send_draft":
        return _as_dict(
            run_agent_send_draft(
                environment_id=action.environment_id,
                persist_globals=action.persist_globals,
                record_history=action.record_history,
                include_scripts=action.include_scripts,
            )
        )
    if action.operation == "replay_history":
        if action.history_entry_id is None:
            return _obs("ok: false\nerror: history_entry_id_required\n")
        return _as_dict(
            run_agent_replay_history(
                history_entry_id=action.history_entry_id,
                environment_id=action.environment_id,
                persist_globals=action.persist_globals,
                record_history=action.record_history,
                include_scripts=action.include_scripts,
            )
        )
    if action.operation == "run_scripts":
        if action.request_id is None:
            return _obs("ok: false\nerror: request_id_required\n")
        return _as_dict(
            run_agent_scripts(
                request_id=action.request_id,
                phase=action.script_phase,
                environment_id=action.environment_id,
                persist_globals=action.persist_globals,
            )
        )
    if action.operation == "run_local_script":
        if action.local_script_id is None:
            return _obs("ok: false\nerror: local_script_id_required\n")
        return _as_dict(
            run_agent_local_script(
                local_script_id=action.local_script_id,
                environment_id=action.environment_id,
                persist_globals=action.persist_globals,
            )
        )
    if action.operation == "run_collection":
        if action.collection_id is None:
            return _obs("ok: false\nerror: collection_id_required\n")
        return _as_dict(
            run_agent_collection(
                collection_id=action.collection_id,
                request_ids=action.request_ids,
                environment_id=action.environment_id,
                iterations=action.iterations,
                delay_ms=action.delay_ms,
                iteration_data=action.iteration_data,
                persist_globals=action.persist_globals,
                scripts_enabled=action.scripts_enabled,
            )
        )
    if action.operation == "run_iterations":
        if action.request_id is None:
            return _obs("ok: false\nerror: request_id_required\n")
        if not action.iteration_data:
            return _obs("ok: false\nerror: iteration_data_required\n")
        return _as_dict(
            run_agent_iterations(
                request_id=action.request_id,
                iteration_data=list(action.iteration_data),
                iteration_count=action.iteration_count,
                environment_id=action.environment_id,
                persist_globals=action.persist_globals,
                mock_response=action.mock_response,
            )
        )
    if action.operation == "fetch_graphql_schema":
        from services.ai.chat.execution.graphql.fetch import run_fetch_graphql_schema

        return run_fetch_graphql_schema(
            request_id=action.request_id,
            url=action.url,
            environment_id=action.environment_id,
            search=action.search,
        )
    if action.operation == "generate_snippet":
        from services.ai.chat.execution.codegen.snippet import run_generate_snippet

        return run_generate_snippet(
            request_id=action.request_id,
            language=action.language,
            draft=action.draft,
        )
    if action.operation == "export_workspace_artifact":
        from services.ai.chat.execution.export.artifact import run_export_workspace_artifact

        return run_export_workspace_artifact(
            kind=action.artifact_kind,
            history_entry_id=action.history_entry_id,
            run_history_id=action.run_history_id,
            write_path=action.write_path,
        )
    if action.operation == "oauth_get_token":
        from services.ai.chat.execution.oauth.get_token import run_oauth_get_token

        return run_oauth_get_token(
            request_id=action.request_id,
            environment_id=action.environment_id,
            bound_var=action.bound_var,
            oauth_config=action.oauth_config,
            update_auth_placeholder=action.update_auth_placeholder,
        )
    return _obs(f"ok: false\nerror: unsupported_operation\noperation: {action.operation}\n")


def _finish_success(
    action: WorkspaceExecuteAction,
    execution_id: str,
    result: dict[str, Any],
    enqueue_mutation_event: Any,
    append_mutation_audit: Any,
) -> WorkspaceExecuteObservation:
    """Enqueue bridge/audit and format a successful observation."""
    ids = dict(result.get("ids") or {})
    history_entry_id = ids.get("history_entry_id")
    request_id = ids.get("request_id")
    local_script_id = ids.get("local_script_id")
    collection_id = ids.get("collection_id")
    deep_links: list[str] = []
    if isinstance(history_entry_id, int) and history_entry_id > 0:
        deep_links.append(f"postmark://history/{history_entry_id}?focus=response")
    if isinstance(request_id, int) and request_id > 0:
        deep_links.append(f"postmark://request/{request_id}")
    if isinstance(local_script_id, int) and local_script_id > 0:
        deep_links.append(f"postmark://script/{local_script_id}")
    if isinstance(collection_id, int) and collection_id > 0:
        deep_links.append(f"postmark://collection/{collection_id}?focus=runs")
    payload: dict[str, object] = {
        "execution_id": execution_id,
        "summary": str(result.get("summary") or ""),
        "status_code": result.get("status_code"),
        "url": result.get("url"),
        "ok": True,
    }
    if action.operation == "run_scripts":
        payload["script_phase"] = action.script_phase
        if result.get("test_results") is not None:
            payload["test_results"] = result.get("test_results")
        if result.get("console_logs") is not None:
            payload["console_logs"] = result.get("console_logs")
    elif action.operation == "run_local_script":
        if result.get("test_results") is not None:
            payload["test_results"] = result.get("test_results")
        if result.get("console_logs") is not None:
            payload["console_logs"] = result.get("console_logs")
    elif action.operation == "run_collection":
        if result.get("test_results") is not None:
            payload["test_results"] = result.get("test_results")
    elif action.operation == "run_iterations":
        payload["script_phase"] = "test"
        if result.get("test_results") is not None:
            payload["test_results"] = result.get("test_results")
        if result.get("console_logs") is not None:
            payload["console_logs"] = result.get("console_logs")
        iterations_payload = result.get("iterations")
        if iterations_payload is not None:
            payload["iterations"] = iterations_payload
    elif action.operation == "fetch_graphql_schema":
        if result.get("schema") is not None:
            payload["schema"] = result.get("schema")
    enqueue_mutation_event(
        {
            "type": "executed",
            "action": action.operation,
            "ids": ids,
            "payload": payload,
        }
    )
    append_mutation_audit(
        {
            "execution_id": execution_id,
            "operation": action.operation,
            "ids": ids,
            "summary": result.get("summary"),
        }
    )
    lines = [
        "ok: true",
        f"execution_id: {execution_id}",
        f"operation: {action.operation}",
        f"summary: {result.get('summary', '')}",
    ]
    for key in (
        "status_code",
        "url",
        "test_results",
        "console_logs",
        "script_phase",
        "ids",
        "warnings",
        "bound_var",
        "token_type",
        "expires_in",
        "auth_updated",
        "language",
        "artifact_kind",
        "content_preview",
    ):
        if key in result and result[key] is not None:
            lines.append(f"{key}: {result[key]}")
    if isinstance(history_entry_id, int) and history_entry_id > 0:
        lines.append(f"history_entry_id: {history_entry_id}")
    if deep_links:
        lines.append(f"deep_links: {deep_links}")
    if result.get("body_preview"):
        lines.append(f"body_preview: {result['body_preview']}")
    if result.get("schema_summary"):
        lines.append(f"schema_summary: {result['schema_summary']}")
    if result.get("snippet"):
        lines.append(f"snippet: {result['snippet']}")
    if result.get("content"):
        lines.append(f"content: {result['content']}")
    return _obs("\n".join(lines) + "\n")
