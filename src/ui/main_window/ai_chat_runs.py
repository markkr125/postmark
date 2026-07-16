"""Concurrent AI chat run orchestration for :class:`_AiChatControllerMixin`."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Any, Literal, cast

from PySide6.QtCore import QObject, QThread, Qt, Slot
from PySide6.QtWidgets import QMessageBox

from services.ai.ai_config import AiModelEntry
from services.ai.chat.response_text import pick_richest_text
from services.ai.chat.chat_run_limits import max_concurrent_chat_runs
from services.ai.chat.run_registry import AiChatRunContext, ChatRunRegistry
from services.ai.chat.session_service import ComposerRunContext
from services.ai.chat.workspace_snapshot import clear_workspace_snapshot, set_workspace_snapshot
from services.collection_service import CollectionService
from services.scripting.context import mask_sensitive_value

from ui.main_window.ai_chat_host_protocol import _AiChatHostProtocol

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)

_StopMode = Literal["pre_stream", "post_stream"]


class _AiChatRunsMixin:
    """Start, route, and finalize concurrent per-session chat workers."""

    _right_sidebar: RightSidebar
    _chat_run_registry: ChatRunRegistry
    _active_run_context: AiChatRunContext | None
    _stopped_generations: dict[int, _StopMode]
    _pending_title_session_id: str | None
    _active_ai_session_id: str | None
    _concurrency_warned_at_count: int

    @staticmethod
    def _host(obj: object) -> _AiChatHostProtocol:
        """Cast composed controller mixins for cross-mixin calls."""
        return cast(_AiChatHostProtocol, obj)

    def _init_chat_run_registry(self) -> None:
        """Create the run registry and connect worker fan-out signals."""
        self_q = cast(QObject, self)
        self._chat_run_registry = ChatRunRegistry(self_q)
        queued = Qt.ConnectionType.QueuedConnection
        self._chat_run_registry.chunk_received.connect(self._on_registry_chunk_received, queued)
        self._chat_run_registry.status_changed.connect(self._on_registry_status_changed, queued)
        self._chat_run_registry.usage_updated.connect(self._on_registry_usage_updated, queued)
        self._chat_run_registry.context_compacted.connect(
            self._on_registry_context_compacted,
            queued,
        )
        self._chat_run_registry.subagent_updated.connect(
            self._on_registry_subagent_updated,
            queued,
        )
        self._chat_run_registry.confirmation_needed.connect(
            self._on_registry_confirmation_needed,
            queued,
        )
        self._chat_run_registry.confirmation_cleared.connect(
            self._on_registry_confirmation_cleared,
            queued,
        )
        self._chat_run_registry.mutation_bridge_ready.connect(
            self._on_registry_mutation_bridge_ready,
            queued,
        )
        self._chat_run_registry.assistant_finished.connect(
            self._on_registry_assistant_finished,
            queued,
        )
        self._chat_run_registry.failed.connect(self._on_registry_failed, queued)
        self._chat_run_registry.run_finished.connect(self._on_registry_run_finished, queued)
        self._chat_run_registry.running_sessions_changed.connect(self._sync_running_chrome, queued)
        self._concurrency_warned_at_count = -1

    def _sync_running_chrome(self) -> None:
        """Refresh header badge and history running indicators."""
        count = self._chat_run_registry.count_running()
        self._right_sidebar.set_ai_active_run_count(count)
        popup = self._session_history_popup_if_visible()
        if popup is not None:
            popup.set_running_session_ids(self._chat_run_registry.running_session_ids())

    @staticmethod
    def _session_history_popup_if_visible():
        """Return the session history popover when it is open."""
        from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup

        popup = AiSessionHistoryPopup.instance()
        if popup.isVisible():
            return popup
        return None

    def _update_active_session_busy_state(self) -> None:
        """Sync composer busy chrome with the visible session's run state."""
        panel = self._right_sidebar.ai_chat_panel
        session_id = self._active_ai_session_id
        registry = getattr(self, "_chat_run_registry", None)
        if registry is None:
            return
        panel.set_run_busy(registry.is_running(session_id))

    def _maybe_warn_concurrent_load(self) -> None:
        """Advise when concurrent runs meet or exceed the Settings threshold."""
        limit = max_concurrent_chat_runs()
        count = self._chat_run_registry.count_running()
        if count < limit:
            self._concurrency_warned_at_count = -1
            return
        if count == self._concurrency_warned_at_count:
            return
        self._concurrency_warned_at_count = count
        QMessageBox.warning(
            self._right_sidebar,
            "High concurrent chat load",
            f"You have {count} chats running (advisory limit: {limit}). "
            "Additional sends are allowed, but many parallel agents can increase "
            "cost and load. Adjust the limit under Settings → AI → Agents, or stop runs "
            "from session history.",
        )

    def _start_chat_run(
        self,
        *,
        session_id: str,
        user_message_id: int,
        user_text: str,
        entry: AiModelEntry,
        agent_id: str,
        text: str,
        composer: ComposerRunContext | None,
    ) -> bool:
        """Persist UI state and spawn a worker for one assistant turn."""
        if self._chat_run_registry.is_running(session_id):
            return False
        self._maybe_warn_concurrent_load()

        try:
            snapshot = self._build_ai_workspace_snapshot()
        except Exception:
            logger.debug(
                "Workspace snapshot capture failed; using empty snapshot",
                exc_info=True,
            )
            snapshot = {
                "active_tab_index": 0,
                "active_collection_id": None,
                "current_env_id": None,
                "active_response": None,
                "tabs": [],
            }
        set_workspace_snapshot(session_id, snapshot)

        run_generation = self._chat_run_registry.next_run_generation()
        if session_id == self._active_ai_session_id:
            self._active_run_context = AiChatRunContext(
                session_id=session_id,
                user_message_id=user_message_id,
                user_text=user_text,
                run_generation=run_generation,
                model_id=str(entry["id"]),
            )

        panel = self._right_sidebar.ai_chat_panel
        if session_id == self._active_ai_session_id:
            panel.set_run_busy(True)
            panel.begin_assistant_stream()

        handle = self._chat_run_registry.start_run(
            session_id=session_id,
            run_generation=run_generation,
            user_message_id=user_message_id,
            user_text=user_text,
            model_id=str(entry["id"]),
            entry=entry,
            agent_id=agent_id,
            text=text,
            composer=composer,
        )
        if handle is None:
            if session_id == self._active_ai_session_id:
                self._active_run_context = None
                panel.set_run_busy(False)
            return False
        return True

    def _reattach_session_run_if_needed(self, session_id: str) -> None:
        """Resume streaming UI when switching back to a running session."""
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or session_id != self._active_ai_session_id:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.set_run_busy(True)
        panel.resume_assistant_stream(
            handle.thinking_buffer,
            handle.content_buffer,
            status=handle.status_text,
            subagent_records=handle.subagent_records,
        )
        pending = getattr(handle.worker, "_pending_confirmation", None)
        if pending is not None:
            panel.show_confirmation(pending)
        else:
            panel.clear_confirmation()
        metrics = handle.pending_sdk_metrics
        if metrics is not None:
            panel.deliver_context_usage_metrics(metrics)

    @Slot(str, int, str, str)
    def _on_registry_chunk_received(
        self,
        session_id: str,
        run_generation: int,
        thinking_delta: str,
        content_delta: str,
    ) -> None:
        """Deliver chunks only to the visible session's panel."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.deliver_assistant_chunk(thinking_delta, content_delta)

    @Slot(str, int, str)
    def _on_registry_status_changed(
        self,
        session_id: str,
        run_generation: int,
        status: str,
    ) -> None:
        """Update the activity row for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        self._right_sidebar.ai_chat_panel.deliver_activity_status(status)

    @Slot(str, int, object)
    def _on_registry_subagent_updated(
        self,
        session_id: str,
        run_generation: int,
        records: object,
    ) -> None:
        """Update subagent cards for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        self._right_sidebar.ai_chat_panel.deliver_subagent_update(records)

    @Slot(str, int, object)
    def _on_registry_confirmation_needed(
        self,
        session_id: str,
        run_generation: int,
        payload: object,
    ) -> None:
        """Show Approve chrome for the visible session only."""
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        if session_id != self._active_ai_session_id:
            return
        self._right_sidebar.ai_chat_panel.show_confirmation(payload)

    @Slot(str, int)
    def _on_registry_confirmation_cleared(self, session_id: str, run_generation: int) -> None:
        """Hide Approve chrome and drain mutation bridge events."""
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        if session_id == self._active_ai_session_id:
            self._right_sidebar.ai_chat_panel.clear_confirmation()
        self._drain_mutation_bridge()

    @Slot(str, int)
    def _on_registry_mutation_bridge_ready(self, session_id: str, run_generation: int) -> None:
        """Drain mutation bridge events after tool side effects."""
        del session_id, run_generation
        self._drain_mutation_bridge()

    def _drain_mutation_bridge(self) -> None:
        """Apply queued mutate/execute GUI side effects on the main thread."""
        from ui.main_window.mutation_drain import drain_mutation_bridge

        drain_mutation_bridge(cast(Any, self))

    def _reload_open_request_from_db(self, request_id: int) -> None:
        """Reload a materialised request tab from the database (Agent wins)."""
        from ui.main_window.mutation_drain import reload_open_request_from_db

        reload_open_request_from_db(cast(Any, self), request_id)

    def _reload_open_folder_from_db(self, collection_id: int) -> None:
        """Reload an open folder tab from the database (Agent wins)."""
        from ui.main_window.mutation_drain import reload_open_folder_from_db

        reload_open_folder_from_db(cast(Any, self), collection_id)

    def _close_tabs_for_mutation_ids(self, ids: dict[str, int]) -> None:
        """Close open tabs matching deleted request/collection ids."""
        from ui.main_window.mutation_drain import close_tabs_for_mutation_ids

        close_tabs_for_mutation_ids(cast(Any, self), ids)

    def _close_stale_workspace_tabs(self) -> None:
        """Close request/folder tabs whose DB rows no longer exist."""
        from ui.main_window.mutation_drain import close_stale_workspace_tabs

        close_stale_workspace_tabs(cast(Any, self))

    @Slot(str, int, object)
    def _on_registry_usage_updated(
        self,
        session_id: str,
        run_generation: int,
        metrics: object,
    ) -> None:
        """Refresh context usage for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.deliver_context_usage_metrics(metrics)
        panel.deliver_context_usage_refresh()

    @Slot(str, int)
    def _on_registry_context_compacted(self, session_id: str, run_generation: int) -> None:
        """Show compaction notice for the visible session only."""
        if session_id != self._active_ai_session_id:
            return
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        panel = self._right_sidebar.ai_chat_panel
        panel.on_context_compacted()
        panel.deliver_context_usage_refresh()

    @Slot(str, int, str, str)
    def _on_registry_assistant_finished(
        self,
        session_id: str,
        run_generation: int,
        thinking: str,
        content: str,
    ) -> None:
        """Marshal assistant finish onto the GUI thread."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_assistant_finish_requested.emit(  # type: ignore[attr-defined]
                session_id,
                run_generation,
                thinking,
                content,
            )
            return
        self._apply_registry_assistant_finished(session_id, run_generation, thinking, content)

    @Slot(str, int, str, str)
    def _apply_registry_assistant_finished(
        self,
        session_id: str,
        run_generation: int,
        thinking: str,
        content: str,
    ) -> None:
        """Finalize a successful assistant turn on the GUI thread."""
        if run_generation in self._stopped_generations:
            self._clear_visible_busy_if_needed(session_id)
            return
        if session_id == self._active_ai_session_id:
            self._host(self)._on_ai_assistant_finished(session_id, thinking, content)
        else:
            self._finalize_background_turn(
                session_id, run_generation, thinking, content, failed=False
            )
        self._drain_mutation_bridge()

    @Slot(str, int, str, str, str)
    def _on_registry_failed(
        self,
        session_id: str,
        run_generation: int,
        message: str,
        thinking: str,
        content: str,
    ) -> None:
        """Marshal chat failure onto the GUI thread."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_chat_fail_requested.emit(  # type: ignore[attr-defined]
                session_id,
                run_generation,
                message,
                thinking,
                content,
            )
            return
        self._apply_registry_failed(session_id, run_generation, message, thinking, content)

    @Slot(str, int, str, str, str)
    def _apply_registry_failed(
        self,
        session_id: str,
        run_generation: int,
        message: str,
        thinking: str,
        content: str,
    ) -> None:
        """Apply worker failure or user stop on the GUI thread."""
        handle = self._chat_run_registry.run_for(session_id)
        ctx = handle.context if handle is not None else None
        if ctx is None or ctx.run_generation != run_generation:
            self._clear_visible_busy_if_needed(session_id)
            return

        stopped = message.strip().lower() == "stopped"
        stop_mode = self._stopped_generations.get(run_generation)
        if stopped and stop_mode == "pre_stream":
            if session_id == self._active_ai_session_id:
                self._host(self)._rollback_pre_stream_stop(ctx)
            self._stopped_generations.pop(run_generation, None)
            self._drain_mutation_bridge()
            return

        visible = session_id == self._active_ai_session_id
        if stopped and stop_mode == "post_stream":
            if visible:
                self._host(self)._persist_stopped_assistant(session_id, thinking, content)
                panel = self._right_sidebar.ai_chat_panel
                panel.set_run_busy(False)
            else:
                self._finalize_background_turn(
                    session_id,
                    run_generation,
                    thinking,
                    content,
                    failed=True,
                    footer="Stopped.",
                )
            self._stopped_generations.pop(run_generation, None)
            self._drain_mutation_bridge()
            return

        if visible:
            self._host(self)._on_ai_chat_failed(session_id, message, thinking, content)
        else:
            footer = "Stopped." if stopped else self._host(self)._format_chat_error(message)
            self._finalize_background_turn(
                session_id,
                run_generation,
                thinking,
                content,
                failed=True,
                footer=footer,
            )
        self._drain_mutation_bridge()

    def _finalize_background_turn(
        self,
        session_id: str,
        run_generation: int,
        thinking: str,
        content: str,
        *,
        failed: bool,
        footer: str = "",
    ) -> None:
        """Persist a completed background assistant turn without panel streaming."""
        handle = self._chat_run_registry.run_for(session_id)
        if handle is None or handle.context.run_generation != run_generation:
            return
        thinking_text = pick_richest_text(thinking, handle.thinking_buffer)
        body = pick_richest_text(content, handle.content_buffer)
        host = self._host(self)
        if failed:
            display = host._compose_failure_transcript(body, footer)
        else:
            if not thinking_text.strip() and not body.strip():
                display = host._compose_failure_transcript("", "No response from model")
            else:
                display = body
        host._persist_assistant_turn(
            session_id,
            display,
            thinking=thinking_text,
            thinking_duration_seconds=None,
            model_id=handle.context.model_id,
            usage=handle.pending_sdk_metrics,
            update_panel=False,
        )
        self._pending_title_session_id = session_id
        if session_id == self._active_ai_session_id:
            self._update_active_session_busy_state()

    def _clear_visible_busy_if_needed(self, session_id: str) -> None:
        """Clear composer busy when a stale signal targets the visible session."""
        if session_id == self._active_ai_session_id:
            self._right_sidebar.ai_chat_panel.set_run_busy(False)

    @Slot(str, int)
    def _on_registry_run_finished(self, session_id: str, run_generation: int) -> None:
        """Clear active context and schedule title generation after thread exit."""
        ctx = self._active_run_context
        if (
            ctx is not None
            and ctx.session_id == session_id
            and ctx.run_generation == run_generation
        ):
            self._active_run_context = None
        if session_id == self._active_ai_session_id:
            self._update_active_session_busy_state()
        pending = self._pending_title_session_id
        if pending == session_id:
            self._pending_title_session_id = None
            self._host(self)._maybe_generate_session_title(session_id)
        if not self._chat_run_registry.is_running(session_id):
            clear_workspace_snapshot(session_id)

    def _cancel_session_run(self, session_id: str | None) -> None:
        """Interrupt one session worker without optimistic UI rollback."""
        if session_id is None:
            return
        self._chat_run_registry.cancel(session_id)
        if session_id == self._active_ai_session_id:
            self._right_sidebar.ai_chat_panel.set_run_busy(False)

    def _handle_chat_stop(self) -> None:
        """Optimistically finalize stop UI, then interrupt the visible session worker."""
        panel = self._right_sidebar.ai_chat_panel
        session_id = self._active_ai_session_id
        if session_id is None:
            panel.set_run_busy(False)
            return
        handle = self._chat_run_registry.run_for(session_id)
        ctx = handle.context if handle is not None else None
        if ctx is None:
            active_ctx = self._active_run_context
            if active_ctx is not None and active_ctx.session_id == session_id:
                ctx = active_ctx
        if ctx is None:
            panel.set_run_busy(False)
            return

        host = self._host(self)
        if panel.is_pre_stream_cancel():
            host._rollback_pre_stream_stop(ctx)
            host._mark_run_stopped(ctx.run_generation, pre_stream=True)
        else:
            host._finalize_stream_stop_optimistic(ctx)
            host._mark_run_stopped(ctx.run_generation, pre_stream=False)

        self._chat_run_registry.cancel(ctx.session_id)

    def _build_ai_workspace_snapshot(self) -> dict[str, Any]:
        """Capture open tabs and active-tab GUI state for workspace queries."""
        host = cast(Any, self)
        empty: dict[str, Any] = {
            "active_tab_index": 0,
            "active_collection_id": None,
            "current_env_id": None,
            "active_response": None,
            "tabs": [],
        }
        if not hasattr(host, "_tab_bar") or not hasattr(host, "_tabs"):
            return empty
        active_index = host._tab_bar.currentIndex()
        tabs: list[dict[str, Any]] = []

        for idx, ctx in host._tabs.items():
            name = self._snapshot_tab_name(host, idx, ctx)
            tab: dict[str, Any] = {
                "index": idx,
                "tab_type": ctx.tab_type,
                "name": name,
                "request_id": ctx.request_id,
                "collection_id": ctx.collection_id,
                "local_script_id": ctx.local_script_id,
                "is_dirty": bool(ctx.is_dirty),
                "is_active": idx == active_index,
            }
            if ctx.tab_type == "request" and ctx.editor is not None:
                tab["request_data"] = ctx.editor.get_request_data(cancel_pending_persist=False)
            if ctx.tab_type == "folder" and ctx.folder_editor is not None and ctx.is_dirty:
                tab["collection_data"] = ctx.folder_editor.get_collection_data()
            if ctx.tab_type == "environments" and ctx.is_dirty:
                tab["environment_dirty"] = True
                env_ed = getattr(ctx, "environment_editor", None)
                if env_ed is not None:
                    eid = getattr(env_ed, "_current_env_id", None)
                    if isinstance(eid, int):
                        tab["environment_id"] = eid
            if ctx.tab_type in ("request", "draft") and ctx.response_viewer is not None:
                viewer = ctx.response_viewer
                if viewer.has_live_response():
                    live = getattr(viewer, "_last_live_response", None)
                    if isinstance(live, dict):
                        tab["last_response"] = {
                            "status_code": live.get("status_code"),
                            "elapsed_ms": live.get("elapsed_ms"),
                        }
            if ctx.tab_type == "local_script" and ctx.local_script_editor is not None:
                content, language = ctx.local_script_editor._pane.get_content()
                tab["local_script_content"] = content
                tab["local_script_language"] = language
            overrides = getattr(ctx, "local_overrides", None)
            if isinstance(overrides, dict) and overrides:
                tab["local_overrides"] = {
                    str(key): mask_sensitive_value(str(key), str(val.get("value", "")))
                    for key, val in overrides.items()
                    if isinstance(val, dict)
                }
            tabs.append(tab)

        for idx, info in getattr(host, "_deferred_tabs", {}).items():
            if idx in host._tabs:
                continue
            deferred_type = str(info.get("type") or "request")
            if deferred_type == "local_script":
                tabs.append(
                    {
                        "index": idx,
                        "tab_type": "local_script",
                        "name": str(info.get("name") or "Script"),
                        "request_id": None,
                        "collection_id": None,
                        "local_script_id": info.get("script_id"),
                        "is_dirty": False,
                        "is_deferred": True,
                        "is_active": idx == active_index,
                    }
                )
            else:
                tabs.append(
                    {
                        "index": idx,
                        "tab_type": "request",
                        "name": str(info.get("name") or "Request"),
                        "request_id": info.get("request_id"),
                        "collection_id": None,
                        "local_script_id": None,
                        "is_dirty": False,
                        "is_deferred": True,
                        "is_active": idx == active_index,
                        "request_data": None,
                    }
                )

        active_ctx = host._tabs.get(active_index)
        active_collection_id = self._snapshot_active_collection_id(active_ctx)
        active_response = self._snapshot_active_response(active_ctx)
        env_selector = getattr(host, "_env_selector", None)
        current_env_id = env_selector.current_environment_id() if env_selector is not None else None

        return {
            "active_tab_index": active_index,
            "active_collection_id": active_collection_id,
            "current_env_id": current_env_id,
            "active_response": active_response,
            "captured_at": datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "tabs": tabs,
        }

    @staticmethod
    def _snapshot_tab_name(host: Any, idx: int, ctx: Any) -> str:
        """Resolve a display name for one materialized tab."""
        _method, bar_name = host._tab_bar.tab_request_info(idx)
        if bar_name:
            return str(bar_name)
        if ctx.draft_name:
            return str(ctx.draft_name)
        if ctx.tab_type == "folder" and ctx.folder_editor is not None:
            data = ctx.folder_editor.get_collection_data()
            return str(data.get("name") or "Folder")
        return "Tab"

    @staticmethod
    def _snapshot_active_collection_id(ctx: Any | None) -> int | None:
        """Resolve the collection context for the active tab."""
        if ctx is None:
            return None
        if ctx.tab_type == "folder" and ctx.collection_id is not None:
            return int(ctx.collection_id)
        if ctx.request_id is not None:
            row = CollectionService.get_request(int(ctx.request_id))
            if row is not None:
                return int(row.collection_id)
        if ctx.variable_collection_id is not None:
            return int(ctx.variable_collection_id)
        return None

    @staticmethod
    def _snapshot_active_response(ctx: Any | None) -> dict[str, Any] | None:
        """Build a JSON-safe live response payload for the active tab."""
        if ctx is None or ctx.response_viewer is None:
            return None
        viewer = ctx.response_viewer
        if not viewer.has_live_response():
            err_payload = getattr(viewer, "_last_error_response", None)
            if isinstance(err_payload, dict) and err_payload.get("error"):
                return {"send_error": str(err_payload.get("error", ""))}
            stored_id = getattr(viewer, "_viewing_stored_entry_id", None)
            if isinstance(stored_id, int):
                return {"viewing_stored_entry_id": stored_id}
            return None
        payload = viewer.get_save_response_data()
        if payload is None:
            return None
        data = dict(payload)
        live = getattr(viewer, "_last_live_response", None)
        if isinstance(live, dict):
            if live.get("elapsed_ms") is not None:
                data["elapsed_ms"] = live.get("elapsed_ms")
            if live.get("size_bytes") is not None:
                data["size_bytes"] = live.get("size_bytes")
        results: list[dict[str, Any]] | None = None
        if isinstance(live, dict):
            live_results = live.get("test_results")
            if isinstance(live_results, list) and live_results:
                results = live_results
        if results is None:
            viewer_results = getattr(viewer, "_test_results", None)
            if isinstance(viewer_results, list) and viewer_results:
                results = viewer_results
        if results:
            normalized: list[dict[str, Any]] = []
            for row in results:
                if not isinstance(row, dict):
                    continue
                item: dict[str, Any] = {
                    "name": str(row.get("name", "")),
                    "passed": bool(row.get("passed")),
                }
                err = row.get("error")
                if err:
                    item["error"] = str(err)
                normalized.append(item)
            passed = sum(1 for row in normalized if row.get("passed"))
            failed = len(normalized) - passed
            data["test_summary"] = {"passed": passed, "failed": failed}
            failures = [row for row in normalized if not row.get("passed")]
            passes = [row for row in normalized if row.get("passed")]
            copied = failures[:20]
            if len(copied) < 20:
                copied.extend(passes[: 20 - len(copied)])
            data["test_results"] = copied
        if isinstance(live, dict):
            raw_logs = live.get("console_logs")
            if isinstance(raw_logs, list) and raw_logs:
                log_copy: list[dict[str, Any]] = []
                for entry in raw_logs[:50]:
                    if not isinstance(entry, dict):
                        continue
                    log_copy.append(
                        {
                            "level": str(entry.get("level", "log")),
                            "message": str(entry.get("message", "")),
                        }
                    )
                if log_copy:
                    data["console_logs"] = log_copy
            timing = live.get("timing")
            if isinstance(timing, dict):
                data["timing"] = dict(timing)
            network = live.get("network")
            if isinstance(network, dict):
                data["network"] = dict(network)
            for size_key in (
                "request_headers_size",
                "request_body_size",
                "response_headers_size",
                "response_uncompressed_size",
            ):
                if live.get(size_key) is not None:
                    data[size_key] = live.get(size_key)
            for var_key in ("variable_changes", "pre_request_variable_changes"):
                changes = live.get(var_key)
                if isinstance(changes, dict) and changes:
                    bounded = {str(k): str(v) for k, v in list(changes.items())[:20]}
                    if bounded:
                        data[var_key] = bounded
        return data


__all__ = ["_AiChatRunsMixin"]
