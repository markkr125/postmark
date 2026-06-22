"""GUI-thread capture of app context for AI chat tools."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from database.data_paths import session_disk_dir
from services.ai.chat.app_context.snapshot import (
    SNAPSHOT_FILENAME,
    ActiveTabSnapshot,
    AppContextSnapshot,
    EnvironmentSnapshot,
    OpenTabEntry,
    TreeSelectionSnapshot,
    truncate_preview,
)
from services.ai.chat.context_redaction import redact_text
from services.environment_service import EnvironmentService
from ui.collections.tree.constants import ITEM_TYPE_SCRIPT, ROLE_ITEM_ID, ROLE_ITEM_TYPE
from ui.request.request_editor.editor_widget import _TAB_NAMES

if TYPE_CHECKING:
    from ui.request.navigation.tab_manager import TabContext


class _AppContextSnapshotMixin:
    """Capture MainWindow tab/editor state into the session workspace snapshot."""

    _tabs: dict[int, Any]
    _deferred_tabs: dict[int, dict[str, Any]]
    collection_widget: Any
    local_scripts_widget: Any
    _env_selector: Any

    def _current_tab_context(self) -> TabContext | None: ...

    def write_app_context_snapshot(self, session_id: str, send_mode: str) -> None:
        """Write ``app_context_snapshot.json`` atomically before a chat run."""
        disk = session_disk_dir(session_id)
        disk.mkdir(parents=True, exist_ok=True)
        mode: Literal["agent", "ask", "plan"]
        normalized = (send_mode or "agent").strip().lower()
        if normalized not in ("agent", "ask", "plan"):
            normalized = "agent"
        mode = normalized  # type: ignore[assignment]

        ctx = self._current_tab_context()
        snapshot: AppContextSnapshot = {
            "captured_at": datetime.now(UTC).isoformat(),
            "send_mode": mode,
            "active_tab": self._active_tab_snapshot(ctx),
            "open_tabs": self._open_tab_entries(),
            "deferred_tabs": self._deferred_tab_entries(),
            "environment": self._environment_snapshot(),
            "tree_selection": self._tree_selection_snapshot(ctx),
        }
        tmp = disk / f"{SNAPSHOT_FILENAME}.tmp"
        final = disk / SNAPSHOT_FILENAME
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, final)

    def _environment_snapshot(self) -> EnvironmentSnapshot:
        env_id = self._env_selector.current_environment_id()
        name: str | None = None
        if env_id is not None:
            for env in EnvironmentService.fetch_all():
                if int(env["id"]) == int(env_id):
                    name = str(env.get("name") or "")
                    break
        return EnvironmentSnapshot(id=env_id, name=name)

    def _tree_selection_snapshot(self, ctx: TabContext | None) -> TreeSelectionSnapshot:
        none_sel: TreeSelectionSnapshot = {
            "kind": "none",
            "collection_id": None,
            "local_script_id": None,
            "label": None,
        }
        coll_id = self.collection_widget.selected_collection_id()
        if coll_id is not None and (ctx is None or ctx.collection_id != coll_id):
            return TreeSelectionSnapshot(
                kind="collection",
                collection_id=coll_id,
                local_script_id=None,
                label=None,
            )
        tree = self.local_scripts_widget._tree_widget._tree
        item = tree.currentItem()
        if item is not None:
            item_type = item.data(0, ROLE_ITEM_TYPE)
            item_id = item.data(0, ROLE_ITEM_ID)
            if item_type == ITEM_TYPE_SCRIPT and item_id is not None:
                sid = int(item_id)
                if ctx is None or ctx.local_script_id != sid:
                    return TreeSelectionSnapshot(
                        kind="local_script",
                        collection_id=None,
                        local_script_id=sid,
                        label=item.text(0),
                    )
        return none_sel

    def _open_tab_entries(self) -> list[OpenTabEntry]:
        entries: list[OpenTabEntry] = []
        for ctx in self._tabs.values():
            entries.append(self._context_to_tab_entry(ctx))
        return entries

    def _deferred_tab_entries(self) -> list[OpenTabEntry]:
        entries: list[OpenTabEntry] = []
        for info in self._deferred_tabs.values():
            entries.append(self._deferred_to_tab_entry(info))
        return entries

    def _context_to_tab_entry(self, ctx: TabContext) -> OpenTabEntry:
        label = self._context_label(ctx)
        return OpenTabEntry(
            tab_type=ctx.tab_type,  # type: ignore[typeddict-item]
            request_id=ctx.request_id,
            collection_id=ctx.collection_id,
            local_script_id=ctx.local_script_id,
            label=label,
            is_dirty=bool(ctx.is_dirty),
            is_preview=bool(ctx.is_preview),
        )

    def _deferred_to_tab_entry(self, info: dict[str, Any]) -> OpenTabEntry:
        if info.get("type") == "local_script" or info.get("script_id") is not None:
            sid = info.get("script_id")
            return OpenTabEntry(
                tab_type="local_script",
                request_id=None,
                collection_id=None,
                local_script_id=int(sid) if sid is not None else None,
                label=str(info.get("name") or "Script"),
                is_dirty=False,
                is_preview=False,
            )
        return OpenTabEntry(
            tab_type="request",
            request_id=info.get("request_id"),
            collection_id=None,
            local_script_id=None,
            label=str(info.get("name") or "Request"),
            is_dirty=False,
            is_preview=False,
        )

    def _context_label(self, ctx: TabContext) -> str:
        if ctx.tab_type == "request" and ctx.editor is not None:
            data = ctx.editor.get_request_data()
            method = str(data.get("method") or "")
            name = str(data.get("name") or ctx.draft_name or "Request")
            return f"{method} {name}".strip()
        if ctx.tab_type == "folder" and ctx.folder_editor is not None:
            return str(ctx.folder_editor.get_collection_data().get("name") or "Folder")
        if ctx.tab_type == "local_script" and ctx.local_script_editor is not None:
            content, _lang = ctx.local_script_editor._pane.get_content()
            return f"Script ({len(content)} chars)"
        if ctx.tab_type == "environments":
            return "Environments"
        return ctx.tab_type

    def _active_tab_snapshot(self, ctx: TabContext | None) -> ActiveTabSnapshot:
        if ctx is None:
            return ActiveTabSnapshot(
                tab_type="none",
                request_id=None,
                collection_id=None,
                local_script_id=None,
                title="",
                method=None,
                is_dirty=False,
                is_preview=False,
                draft_name=None,
                active_sub_tab=None,
                editor_preview="",
            )
        title = self._context_label(ctx)
        method: str | None = None
        if ctx.tab_type == "request" and ctx.editor is not None:
            method = str(ctx.editor.get_request_data().get("method") or "")
        sub_tab = self._request_sub_tab_label(ctx)
        preview = truncate_preview(self._preview_for_context(ctx, sub_tab))
        return ActiveTabSnapshot(
            tab_type=ctx.tab_type,
            request_id=ctx.request_id,
            collection_id=ctx.collection_id,
            local_script_id=ctx.local_script_id,
            title=title,
            method=method,
            is_dirty=bool(ctx.is_dirty),
            is_preview=bool(ctx.is_preview),
            draft_name=ctx.draft_name,
            active_sub_tab=sub_tab,
            editor_preview=preview,
        )

    def _request_sub_tab_label(self, ctx: TabContext) -> str | None:
        if ctx.tab_type != "request" or ctx.editor is None:
            return None
        idx = ctx.editor._tabs.currentIndex()
        if 0 <= idx < len(_TAB_NAMES):
            return _TAB_NAMES[idx]
        return None

    def _preview_for_context(self, ctx: TabContext, sub_tab: str | None) -> str:
        if ctx.tab_type == "request" and ctx.editor is not None:
            editor = ctx.editor
            data = editor.get_request_data()
            if sub_tab in ("Headers", "Auth"):
                headers = editor.get_headers_text() or ""
                url = str(data.get("url") or "")
                return redact_text(f"URL: {url}\n\nHeaders:\n{headers}")
            if sub_tab == "Body":
                return redact_text(str(data.get("body") or ""))
            if sub_tab == "Scripts":
                scripts = data.get("scripts") or {}
                pre = scripts.get("pre_request") or ""
                test = scripts.get("test") or ""
                return redact_text(f"Pre-request:\n{pre}\n\nTest:\n{test}")
            method = str(data.get("method") or "")
            url = redact_text(str(data.get("url") or ""))
            name = str(data.get("name") or "")
            return f"{method} {name}\n{url}"
        if ctx.tab_type == "folder" and ctx.folder_editor is not None:
            coll = ctx.folder_editor.get_collection_data()
            return f"{coll.get('name', '')}\n{coll.get('description', '')}"
        if ctx.tab_type == "local_script" and ctx.local_script_editor is not None:
            content, _lang = ctx.local_script_editor._pane.get_content()
            return redact_text(content)
        if ctx.tab_type == "environments":
            env = self._environment_snapshot()
            return str(env.get("name") or "")
        return ""
