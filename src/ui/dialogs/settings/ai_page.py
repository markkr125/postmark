"""Settings dialog — AI providers/models page."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled
from services.ai.provider_catalog import (
    ModelSpec,
    capability_tags_for_entry,
    context_display_for_entry,
    cost_display_for_entry,
    ollama_default_context_tokens,
    provider_connection_key,
    provider_group_label,
)
from services.scripting.secret_store import get_default_store
from ui.dialogs.settings.ai_page_actions import (
    CAPABILITIES_COLUMN,
    ENABLED_COLUMN,
    NAME_COLUMN,
    configure_ai_models_tree_header,
    entries_from_model_specs,
    make_provider_gear_button,
)
from ui.dialogs.settings.ai_provider_dialog import AiProviderDialog
from ui.dialogs.settings.ai_provider_workers import AiProviderSetupWorker, AiRefreshUiBridge
from ui.styling.icons import phi
from ui.styling.theme import current_palette
from ui.widgets.ai_models_enable_delegate import (
    AiModelsEnableDelegate,
    model_row_enabled,
    set_model_row_enabled,
)
from ui.widgets.ai_models_tree_delegate import AiModelsTreeDelegate

_GROUP_PREFIX = "group:"
_PROVIDER_ROLE = Qt.ItemDataRole.UserRole + 1
_TREE_COLUMN_COUNT = 6
_TREE_BATCH_SIZE = 24


def _provider_group_key(entry: AiModelEntry) -> str:
    """Stable id for grouping rows that share one provider connection."""
    return provider_connection_key(entry)


def _model_belongs_to_provider(entry: AiModelEntry, *, group_key: str, auth_ref: str) -> bool:
    """True when *entry* is part of the provider group being replaced."""
    if auth_ref:
        return entry.get("auth_ref") == auth_ref
    return _provider_group_key(entry) == group_key


def splice_provider_models(
    models: list[AiModelEntry],
    *,
    group_key: str,
    auth_ref: str,
    new_rows: list[AiModelEntry],
) -> list[AiModelEntry]:
    """Replace one provider's rows in place so tree order stays stable."""
    indices = [
        i
        for i, row in enumerate(models)
        if _model_belongs_to_provider(row, group_key=group_key, auth_ref=auth_ref)
    ]
    if not indices:
        return models + list(new_rows)
    start, end = indices[0], indices[-1] + 1
    return models[:start] + list(new_rows) + models[end:]


class AiPageController:
    """Owns AI page state and the configured-models tree."""

    def __init__(
        self,
        page: QWidget,
        tree: QTreeWidget,
        status: QLabel,
        buttons: dict[str, QPushButton],
        on_changed: Callable[[], None],
    ) -> None:
        """Wire the AI settings page widgets and load persisted config."""
        self._page = page
        self._tree = tree
        self._status = status
        self._buttons = buttons
        self._on_changed = on_changed
        self._refresh_bridge = AiRefreshUiBridge(self, page)
        self.models: list[AiModelEntry] = AiConfig.get_models()
        self._refresh_thread: QThread | None = None
        self._refresh_worker: AiProviderSetupWorker | None = None
        self._refresh_group_key = ""
        self._tree_load_generation = 0
        self._tree_load_queue: list[AiModelEntry] = []
        self._tree_load_groups: dict[str, QTreeWidgetItem] = {}

        buttons["add"].clicked.connect(self._on_add_provider)
        buttons["expand_all"].clicked.connect(self._expand_all_provider_groups)
        buttons["collapse_all"].clicked.connect(self._collapse_all_provider_groups)
        self._tree.itemClicked.connect(self._on_model_row_clicked)
        self._schedule_reload_tree()

    def _persist(self) -> None:
        """Write models to QSettings immediately (survives restart without Apply)."""
        AiConfig.save_all(self.models)

    def _on_model_row_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Toggle the enable checkbox when any cell on a model row is clicked."""
        row_id = item.data(NAME_COLUMN, Qt.ItemDataRole.UserRole)
        if not isinstance(row_id, str) or row_id.startswith(_GROUP_PREFIX):
            return
        enabled = not model_row_enabled(item, column=ENABLED_COLUMN)
        set_model_row_enabled(item, column=ENABLED_COLUMN, enabled=enabled)
        self._on_model_enabled_toggled(item, enabled)

    def _on_model_enabled_toggled(self, item: QTreeWidgetItem, enabled: bool) -> None:
        """Sync left-aligned enable checkbox to persisted model rows."""
        row_id = item.data(NAME_COLUMN, Qt.ItemDataRole.UserRole)
        if not isinstance(row_id, str) or row_id.startswith(_GROUP_PREFIX):
            return
        entry = self._entry_by_id(row_id)
        if entry is None:
            return
        if entry.get("enabled") == enabled:
            return
        entry["enabled"] = enabled
        self._tree.viewport().update()
        self._persist()
        self._on_changed()
        self._refresh_buttons()

    def _merge_entries(self, new_entries: list[AiModelEntry], *, replace_auth_ref: str) -> None:
        """Replace rows for *replace_auth_ref* and append *new_entries* (dedupe by model id)."""
        if replace_auth_ref:
            self.models = [e for e in self.models if e.get("auth_ref") != replace_auth_ref]
        existing_models = {e["model"] for e in self.models}
        for row in new_entries:
            if row["model"] in existing_models:
                continue
            self.models.append(row)
            existing_models.add(row["model"])

    def _find_provider_item(self, group_key: str) -> QTreeWidgetItem | None:
        marker = f"{_GROUP_PREFIX}{group_key}"
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is not None and item.data(NAME_COLUMN, Qt.ItemDataRole.UserRole) == marker:
                return item
        return None

    def _set_provider_actions_enabled(self, group_key: str, enabled: bool) -> None:
        parent = self._find_provider_item(group_key)
        if parent is None:
            return
        widget = self._tree.itemWidget(parent, CAPABILITIES_COLUMN)
        if widget is not None:
            widget.setEnabled(enabled)

    def _set_provider_models_enabled(self, group_key: str, *, enabled: bool) -> None:
        """Enable or disable every model row under one provider connection."""
        changed = False
        for entry in self.models:
            if _provider_group_key(entry) != group_key:
                continue
            if entry.get("enabled") == enabled:
                continue
            entry["enabled"] = enabled
            changed = True
        parent = self._find_provider_item(group_key)
        if parent is not None:
            for i in range(parent.childCount()):
                child = parent.child(i)
                set_model_row_enabled(child, column=ENABLED_COLUMN, enabled=enabled)
            self._tree.viewport().update()
        if changed:
            self._persist()
            self._on_changed()

    def _model_child_item(self, entry: AiModelEntry) -> QTreeWidgetItem:
        child = QTreeWidgetItem(
            [
                "",
                entry["label"],
                entry["model"],
                context_display_for_entry(entry),
                cost_display_for_entry(entry),
                "",
            ]
        )
        set_model_row_enabled(child, column=ENABLED_COLUMN, enabled=model_entry_enabled(entry))
        child.setData(NAME_COLUMN, Qt.ItemDataRole.UserRole, entry["id"])
        tags = capability_tags_for_entry(entry)
        if tags:
            child.setData(CAPABILITIES_COLUMN, Qt.ItemDataRole.UserRole, tags)
        return child

    def _update_provider_model_children(self, group_key: str, rows: list[AiModelEntry]) -> None:
        """Replace only the model rows under *group_key*; leave provider actions intact."""
        parent = self._find_provider_item(group_key)
        if parent is None:
            self._reload_tree()
            return
        self._tree.blockSignals(True)
        self._tree.setUpdatesEnabled(False)
        try:
            while parent.childCount() > 0:
                parent.removeChild(parent.child(0))
            for entry in rows:
                parent.addChild(self._model_child_item(entry))
            parent.setExpanded(True)
        finally:
            self._tree.setUpdatesEnabled(True)
            self._tree.blockSignals(False)

    def _detach_embedded_tree_widgets(self) -> None:
        """Remove embedded widgets before :meth:`QTreeWidget.clear` (avoids orphan windows)."""
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            if parent is None:
                continue
            widget = self._tree.itemWidget(parent, CAPABILITIES_COLUMN)
            if widget is not None:
                self._tree.removeItemWidget(parent, CAPABILITIES_COLUMN)
                widget.setParent(self._tree)
                widget.hide()
                widget.deleteLater()

    def _detach_provider_action_widgets(self) -> None:
        """Backward-compatible alias for tests and callers."""
        self._detach_embedded_tree_widgets()

    def _schedule_reload_tree(self) -> None:
        """Populate the tree after the Models page is shown (keeps navigation responsive)."""
        self._tree_load_generation += 1
        self._status.setText("Loading models…")
        QTimer.singleShot(0, lambda: self._begin_reload_tree(self._tree_load_generation))

    def _begin_reload_tree(self, generation: int) -> None:
        if generation != self._tree_load_generation:
            return
        self._detach_provider_action_widgets()
        self._tree.setUpdatesEnabled(False)
        try:
            self._tree.clear()
            self._tree_load_groups = {}
            self._tree_load_queue = list(self.models)
            seen_groups: set[str] = set()
            for entry in self.models:
                group_key = _provider_group_key(entry)
                if group_key in seen_groups:
                    continue
                seen_groups.add(group_key)
                self._tree_load_groups[group_key] = self._make_provider_item(group_key, entry)
        finally:
            self._tree.setUpdatesEnabled(True)
        self._reload_tree_batch(generation)

    def _make_provider_item(self, group_key: str, entry: AiModelEntry) -> QTreeWidgetItem:
        """Create one provider header row (name in Name col, gear in Capabilities)."""
        label = provider_group_label(entry)
        parent = QTreeWidgetItem(["", label, "", "", "", ""])
        parent.setData(NAME_COLUMN, Qt.ItemDataRole.UserRole, f"{_GROUP_PREFIX}{group_key}")
        name_font = QFont(parent.font(NAME_COLUMN))
        name_font.setBold(True)
        parent.setFont(NAME_COLUMN, name_font)
        self._apply_provider_header_style(parent)
        self._tree.addTopLevelItem(parent)
        gear = make_provider_gear_button(
            on_edit=partial(self._on_edit_provider_group, group_key),
            on_refresh=partial(self._on_refresh_provider_group, group_key),
            on_select_all=partial(self._set_provider_models_enabled, group_key, enabled=True),
            on_deselect_all=partial(self._set_provider_models_enabled, group_key, enabled=False),
            on_remove=partial(self._on_remove_group, group_key),
        )
        self._tree.setItemWidget(parent, CAPABILITIES_COLUMN, gear)
        return parent

    def _reload_tree_batch(self, generation: int) -> None:
        if generation != self._tree_load_generation:
            return
        if not self._tree_load_queue:
            self._expand_all_provider_groups()
            self._status.setText("")
            self._refresh_buttons()
            return
        batch = self._tree_load_queue[:_TREE_BATCH_SIZE]
        self._tree_load_queue = self._tree_load_queue[_TREE_BATCH_SIZE:]
        self._tree.blockSignals(True)
        self._tree.setUpdatesEnabled(False)
        try:
            for entry in batch:
                parent = self._tree_load_groups.get(_provider_group_key(entry))
                if parent is not None:
                    parent.addChild(self._model_child_item(entry))
        finally:
            self._tree.setUpdatesEnabled(True)
            self._tree.blockSignals(False)
        QTimer.singleShot(0, lambda: self._reload_tree_batch(generation))

    def _expand_all_provider_groups(self) -> None:
        """Expand every provider group so all models are visible when the page opens."""
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is not None:
                item.setExpanded(True)

    def _apply_provider_header_style(self, item: QTreeWidgetItem) -> None:
        """Visually distinguish provider header rows from model child rows."""
        item.setData(NAME_COLUMN, _PROVIDER_ROLE, True)
        brush = QBrush(QColor(current_palette()["bg_alt"]))
        for col in range(_TREE_COLUMN_COUNT):
            item.setBackground(col, brush)

    def _reload_tree(self) -> None:
        """Rebuild the full tree (user actions). Batched like the initial load."""
        self._schedule_reload_tree()

    def _refresh_buttons(self) -> None:
        busy = self._refresh_thread is not None
        self._buttons["add"].setEnabled(not busy)
        self._buttons["expand_all"].setEnabled(not busy)
        self._buttons["collapse_all"].setEnabled(not busy)

    def _entry_by_id(self, model_id: str) -> AiModelEntry | None:
        for e in self.models:
            if e["id"] == model_id:
                return e
        return None

    def _entry_for_group(self, group_key: str) -> AiModelEntry | None:
        for e in self.models:
            if _provider_group_key(e) == group_key:
                return e
        return None

    def _provider_display_names_in_use(self, *, except_group_key: str = "") -> set[str]:
        """Display names already taken by other provider connections."""
        names: set[str] = set()
        for row in self.models:
            if except_group_key and _provider_group_key(row) == except_group_key:
                continue
            name = str(row.get("provider_display_name") or "").strip()
            if name:
                names.add(name)
        return names

    def _on_add_provider(self) -> None:
        dlg = AiProviderDialog(
            entry=None,
            existing_provider_display_names=frozenset(self._provider_display_names_in_use()),
            parent=self._page,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            added = dlg.result_entries()
            self._merge_entries(added, replace_auth_ref="")
            self._reload_tree()
            self._status.setText(f"Added {len(added)} model(s).")
            self._persist()
            self._on_changed()

    def _on_edit_provider_group(self, group_key: str) -> None:
        entry = self._entry_for_group(group_key)
        if entry is None:
            return
        group_rows = [e for e in self.models if _provider_group_key(e) == group_key]
        dlg = AiProviderDialog(
            entry=entry,
            existing_entries=group_rows,
            existing_provider_display_names=frozenset(
                self._provider_display_names_in_use(except_group_key=group_key)
            ),
            parent=self._page,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            added = dlg.result_entries()
            old_ref = dlg.replace_auth_ref()
            self._merge_entries(added, replace_auth_ref=old_ref)
            self._reload_tree()
            self._status.setText(f"Updated provider — {len(added)} model(s).")
            self._persist()
            self._on_changed()

    def _on_remove_group(self, group_key: str) -> None:
        removed = [e for e in self.models if _provider_group_key(e) == group_key]
        if not removed:
            return
        store = get_default_store()
        refs = {e["auth_ref"] for e in removed if e.get("auth_ref")}
        for ref in refs:
            with contextlib.suppress(Exception):
                store.delete(ref)
        removed_ids = {e["id"] for e in removed}
        self.models = [e for e in self.models if e["id"] not in removed_ids]
        self._reload_tree()
        self._status.setText(f"Removed provider ({len(removed)} model(s)).")
        self._persist()
        self._on_changed()

    def _cancel_refresh(self) -> None:
        thread = self._refresh_thread
        worker = self._refresh_worker
        group_key = self._refresh_group_key
        if worker is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                worker.finished.disconnect(self._refresh_bridge.deliver_finished)
                if thread is not None:
                    worker.finished.disconnect(thread.quit)
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            thread.wait(5000)
        if group_key:
            self._set_provider_actions_enabled(group_key, True)
        self._refresh_thread = None
        self._refresh_worker = None
        self._refresh_group_key = ""

    def _on_refresh_provider_group(self, group_key: str) -> None:
        if self._refresh_thread is not None:
            return
        entry = self._entry_for_group(group_key)
        if entry is None:
            return
        self._refresh_group_key = group_key
        self._status.setText("Refreshing models…")
        self._set_provider_actions_enabled(group_key, False)
        self._refresh_buttons()
        self._refresh_thread = QThread()
        self._refresh_worker = AiProviderSetupWorker()
        ollama_ctx = (
            ollama_default_context_tokens(entry) if entry.get("provider") == "ollama" else 0
        )
        self._refresh_worker.set_params(
            provider_key=entry["provider"],
            base_url=entry.get("base_url", ""),
            api_version=entry.get("api_version", ""),
            auth_kind=entry["auth_kind"],
            auth_ref=entry.get("auth_ref", ""),
            entry_id=entry["id"],
            ollama_default_context=ollama_ctx,
        )
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(
            self._refresh_bridge.deliver_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._refresh_worker.finished.connect(
            self._refresh_thread.quit,
            Qt.ConnectionType.QueuedConnection,
        )
        self._refresh_thread.finished.connect(
            self._on_refresh_thread_done,
            Qt.ConnectionType.QueuedConnection,
        )
        self._refresh_thread.start()

    def _apply_refresh_result(self, ok: bool, detail: str, models_obj: object) -> None:
        """Update one provider's model rows on the GUI thread only."""
        group_key = self._refresh_group_key
        entry = self._entry_for_group(group_key) if group_key else None
        if not ok or entry is None or not group_key:
            self._status.setText(detail if detail else "Refresh failed.")
            if group_key:
                self._set_provider_actions_enabled(group_key, True)
            return
        models = models_obj if isinstance(models_obj, tuple) else ()
        specs = tuple(m for m in models if isinstance(m, ModelSpec))
        display_name = provider_group_label(entry)
        new_rows = entries_from_model_specs(entry, specs, provider_display_name=display_name)
        auth_ref = entry.get("auth_ref", "")
        prev_enabled = {
            e["model"]: model_entry_enabled(e)
            for e in self.models
            if _model_belongs_to_provider(e, group_key=group_key, auth_ref=auth_ref)
        }
        for row in new_rows:
            row["enabled"] = prev_enabled.get(row["model"], False)
        self.models = splice_provider_models(
            self.models,
            group_key=group_key,
            auth_ref=auth_ref,
            new_rows=new_rows,
        )
        group_rows = [
            row
            for row in self.models
            if _model_belongs_to_provider(row, group_key=group_key, auth_ref=auth_ref)
        ]
        self._update_provider_model_children(group_key, group_rows)
        self._status.setText(f"Refreshed — {len(new_rows)} tool-capable model(s).")
        self._persist()
        self._on_changed()

    def _on_refresh_thread_done(self) -> None:
        group_key = self._refresh_group_key
        worker = self._refresh_worker
        thread = self._refresh_thread
        self._refresh_worker = None
        self._refresh_thread = None
        self._refresh_group_key = ""
        if group_key:
            self._set_provider_actions_enabled(group_key, True)
        self._refresh_buttons()
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    def _collapse_all_provider_groups(self) -> None:
        """Collapse every provider group in the models tree."""
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item is not None:
                item.setExpanded(False)

    def apply(self) -> None:
        """Persist models (idempotent)."""
        self._persist()

    def cleanup(self) -> None:
        """Stop background refresh before the settings dialog closes."""
        self._tree_load_generation += 1
        self._cancel_refresh()


def build_ai_page(on_changed: Callable[[], None]) -> tuple[QWidget, AiPageController]:
    """Build the AI settings page and return it with its controller."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    heading = QLabel("AI")
    heading.setObjectName("titleLabel")
    layout.addWidget(heading)

    blurb = QLabel(
        "Add a provider to import tool-capable models. Enable each model with the "
        "checkbox (new models start disabled). Cost is USD per 1M tokens when known. "
        "Capabilities appear as colored tags (hover for details): suggest "
        "(fill-in-the-middle), tools, vision. Drag column borders "
        "to resize. Use row actions to edit, refresh, or remove. "
        "API keys live in your keychain."
    )
    blurb.setObjectName("mutedLabel")
    blurb.setWordWrap(True)
    layout.addWidget(blurb)

    tree = QTreeWidget()
    tree.setObjectName("aiModelsTree")
    tree.setColumnCount(_TREE_COLUMN_COUNT)
    tree.setHeaderLabels(["", "Name", "Model", "Context", "Cost", "Capabilities"])
    tree.setRootIsDecorated(True)
    tree.setIndentation(16)
    tree.setUniformRowHeights(True)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    configure_ai_models_tree_header(tree)
    enable_delegate = AiModelsEnableDelegate(tree, enabled_column=ENABLED_COLUMN)
    tree.setItemDelegateForColumn(ENABLED_COLUMN, enable_delegate)
    tree.setItemDelegateForColumn(
        CAPABILITIES_COLUMN,
        AiModelsTreeDelegate(tree, capabilities_column=CAPABILITIES_COLUMN),
    )
    layout.addWidget(tree, 1)

    btn_row = QHBoxLayout()
    buttons: dict[str, QPushButton] = {}
    for key, text, icon in (
        ("add", "Add provider", "plus"),
        ("expand_all", "Expand all", "arrows-out"),
        ("collapse_all", "Collapse all", "arrows-in"),
    ):
        b = QPushButton(text)
        b.setObjectName("outlineButton")
        b.setIcon(phi(icon))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons[key] = b
        btn_row.addWidget(b)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    status = QLabel("")
    status.setObjectName("mutedLabel")
    status.setWordWrap(True)
    layout.addWidget(status)

    controller = AiPageController(page, tree, status, buttons, on_changed)
    return page, controller


__all__ = ["AiPageController", "build_ai_page", "splice_provider_models"]
