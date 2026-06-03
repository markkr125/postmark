"""AI page builds in SettingsDialog; add/apply/remove behave; remove wipes key."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

import services.scripting.secret_store as _ss
from services.ai.ai_config import AiConfig, AiModelEntry, model_entry_enabled
from ui.dialogs.settings_dialog import SettingsDialog
from ui.styling.theme_manager import ThemeManager


def _wait_for_ai_tree(ctrl, qtbot) -> None:
    """Wait until batched tree population finishes."""
    qtbot.waitUntil(
        lambda: not ctrl._tree_load_queue and ctrl._status.text() != "Loading models…",
        timeout=5000,
    )


def _entry(model_id: str = "m1") -> AiModelEntry:
    return {
        "id": model_id,
        "provider": "openai",
        "label": "GPT",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "token",
        "auth_ref": f"ai:{model_id}",
    }


def test_page_builds_and_registers(qapp: QApplication, qtbot) -> None:
    """SettingsDialog exposes the AI page index; Models page builds lazily."""
    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    assert "ai_models" in dialog._page_indices
    assert "ai_overview" in dialog._page_indices
    assert dialog._ai_controller is None
    dialog._ensure_ai_models_page()
    assert dialog._ai_controller is not None


def test_tree_expands_all_providers_after_load(qapp: QApplication, qtbot) -> None:
    """Opening the Models page expands every provider group."""
    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [
        _entry("m1"),
        {**_entry("m2"), "provider": "ollama", "model": "ollama/llama3", "auth_ref": "ai:m2"},
    ]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    for i in range(ctrl._tree.topLevelItemCount()):
        item = ctrl._tree.topLevelItem(i)
        assert item is not None
        assert item.isExpanded()


def test_provider_gear_button_uses_gear_menu(qapp: QApplication) -> None:
    """Provider gear widget uses one gear button instead of three inline action buttons."""
    from ui.dialogs.settings.ai_page_actions import make_provider_gear_button

    wrap = make_provider_gear_button(
        on_edit=lambda: None,
        on_refresh=lambda: None,
        on_select_all=lambda: None,
        on_deselect_all=lambda: None,
        on_remove=lambda: None,
    )
    action_btns = wrap.findChildren(QPushButton, "aiProviderActionsButton")
    assert len(action_btns) == 1
    assert wrap.findChildren(QPushButton, "outlineButton") == []


def test_initial_category_models(qapp: QApplication, qtbot) -> None:
    """initial_category=Models selects the Models child under AI."""
    dialog = SettingsDialog(ThemeManager(qapp), initial_category="Models")
    qtbot.addWidget(dialog)
    current = dialog._cat_tree.currentItem()
    assert current is not None and current.text(0) == "Models"
    assert dialog._stack.currentIndex() == dialog._page_indices["ai_models"]
    assert dialog._ai_controller is not None


def test_initial_category_ai_overview(qapp: QApplication, qtbot) -> None:
    """initial_category=AI selects the AI parent overview row."""
    dialog = SettingsDialog(ThemeManager(qapp), initial_category="AI")
    qtbot.addWidget(dialog)
    current = dialog._cat_tree.currentItem()
    assert current is not None and current.text(0) == "AI"
    assert dialog._stack.currentIndex() == dialog._page_indices["ai_overview"]


def test_persist_writes_immediately(qapp: QApplication, qtbot) -> None:
    """_persist() writes models without pressing Settings Apply."""
    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models.append(_entry("m1"))
    ctrl._persist()
    assert [e["id"] for e in AiConfig.get_models()] == ["m1"]


def test_add_then_apply_persists(qapp: QApplication, qtbot) -> None:
    """apply() is idempotent after _persist()."""
    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models.append(_entry("m2"))
    ctrl._persist()
    ctrl.apply()
    assert [e["id"] for e in AiConfig.get_models()] == ["m2"]


def test_remove_deletes_secret(qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove deletes ai:m1 from the secret store."""
    deleted: list[str] = []

    class _Spy:
        backend_id = "spy"

        def put(self, r: str, s: str) -> None: ...

        def get(self, r: str) -> str | None:
            return None

        def delete(self, r: str) -> None:
            deleted.append(r)

    monkeypatch.setattr(_ss, "get_default_store", lambda: _Spy())
    import ui.dialogs.settings.ai_page as page_mod

    monkeypatch.setattr(page_mod, "get_default_store", lambda: _Spy())

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [_entry("m1")]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    group_key = page_mod._provider_group_key(ctrl.models[0])
    ctrl._on_remove_group(group_key)
    assert "ai:m1" in deleted
    assert ctrl.models == []


def test_remove_provider_group(qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider-row remove deletes all models and credentials for that connection."""
    deleted: list[str] = []

    class _Spy:
        backend_id = "spy"

        def put(self, r: str, s: str) -> None: ...

        def get(self, r: str) -> str | None:
            return None

        def delete(self, r: str) -> None:
            deleted.append(r)

    monkeypatch.setattr(_ss, "get_default_store", lambda: _Spy())
    import ui.dialogs.settings.ai_page as page_mod

    monkeypatch.setattr(page_mod, "get_default_store", lambda: _Spy())

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    shared_ref = "ai:openai-home"
    ctrl.models = [
        {
            **_entry("m1"),
            "auth_ref": shared_ref,
            "model": "openai/gpt-4o",
        },
        {
            **_entry("m2"),
            "auth_ref": shared_ref,
            "model": "openai/gpt-4o-mini",
        },
    ]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    group_key = page_mod._provider_group_key(ctrl.models[0])
    ctrl._on_remove_group(group_key)
    assert ctrl.models == []
    assert shared_ref in deleted


def test_reload_tree_twice_keeps_action_widgets_parented(qapp: QApplication, qtbot) -> None:
    """Clearing the tree must not leave provider action buttons as top-level windows."""
    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [
        _entry("m1"),
        {
            **_entry("m2"),
            "provider": "ollama",
            "model": "ollama/llama3",
            "auth_ref": "ai:m2",
        },
    ]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    for i in range(ctrl._tree.topLevelItemCount()):
        item = ctrl._tree.topLevelItem(i)
        assert item is not None
        from ui.dialogs.settings.ai_page_actions import CAPABILITIES_COLUMN

        widget = ctrl._tree.itemWidget(item, CAPABILITIES_COLUMN)
        assert widget is not None
        assert not widget.isWindow()


def test_capability_tags_stored_on_model_row(
    qapp: QApplication,
    qtbot,
) -> None:
    """Model rows store capability tag metadata for the tree delegate (no per-row widgets)."""
    from ui.dialogs.settings.ai_page_actions import CAPABILITIES_COLUMN

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    entry = _entry("m1")
    entry["tools"] = True
    entry["insert"] = True
    entry["text"] = False
    ctrl.models = [entry]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    parent = ctrl._tree.topLevelItem(0)
    assert parent is not None and parent.childCount() == 1
    child = parent.child(0)
    assert ctrl._tree.itemWidget(child, CAPABILITIES_COLUMN) is None
    raw = child.data(CAPABILITIES_COLUMN, Qt.ItemDataRole.UserRole)
    assert isinstance(raw, list)
    assert [t["label"] for t in raw] == ["suggest", "tools"]


def test_refresh_updates_children_without_clearing_tree(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh replaces model rows only; provider action widgets stay embedded."""
    from services.ai.provider_catalog import ModelSpec

    import ui.dialogs.settings.ai_page as page_mod

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [_entry("m1")]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    cleared: list[bool] = []

    def _spy_clear() -> None:
        cleared.append(True)

    monkeypatch.setattr(ctrl._tree, "clear", _spy_clear)
    group_key = page_mod._provider_group_key(ctrl.models[0])
    ctrl._refresh_group_key = group_key
    specs = (ModelSpec("openai/gpt-4o", "GPT-4o", 128000, True, True),)
    ctrl._apply_refresh_result(True, "ok", specs)
    assert cleared == []
    parent = ctrl._find_provider_item(group_key)
    assert parent is not None
    assert parent.childCount() == 1
    from ui.dialogs.settings.ai_page_actions import CAPABILITIES_COLUMN

    widget = ctrl._tree.itemWidget(parent, CAPABILITIES_COLUMN)
    assert widget is not None
    assert not widget.isWindow()


def test_model_rows_start_unchecked(qapp: QApplication, qtbot) -> None:
    """New model rows show an unchecked Enabled checkbox."""
    from ui.dialogs.settings.ai_page_actions import ENABLED_COLUMN
    from ui.widgets.ai_models_enable_delegate import model_row_enabled

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [_entry("m1")]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    parent = ctrl._tree.topLevelItem(0)
    assert parent is not None
    child = parent.child(0)
    assert child is not None
    assert not model_row_enabled(child, column=ENABLED_COLUMN)
    assert ctrl.models[0].get("enabled") is not True


def test_enabling_model_persists(qapp: QApplication, qtbot) -> None:
    """Clicking a model row toggles enabled and updates QSettings."""
    from ui.dialogs.settings.ai_page_actions import NAME_COLUMN

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [_entry("m1")]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    parent = ctrl._tree.topLevelItem(0)
    assert parent is not None
    child = parent.child(0)
    assert child is not None
    ctrl._on_model_row_clicked(child, NAME_COLUMN)
    qtbot.waitUntil(lambda: ctrl.models[0].get("enabled") is True, timeout=2000)
    assert AiConfig.get_models()[0].get("enabled") is True
    ctrl._on_model_row_clicked(child, NAME_COLUMN)
    qtbot.waitUntil(lambda: ctrl.models[0].get("enabled") is not True, timeout=2000)


def test_provider_select_all_and_deselect_all(qapp: QApplication, qtbot) -> None:
    """Provider gear menu can enable or disable every model in the group."""
    import ui.dialogs.settings.ai_page as page_mod
    from ui.dialogs.settings.ai_page_actions import ENABLED_COLUMN
    from ui.widgets.ai_models_enable_delegate import model_row_enabled

    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    shared_ref = "ai:openai-home"
    ctrl.models = [
        {**_entry("m1"), "auth_ref": shared_ref, "model": "openai/gpt-4o"},
        {**_entry("m2"), "auth_ref": shared_ref, "model": "openai/gpt-4o-mini"},
    ]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    group_key = page_mod._provider_group_key(ctrl.models[0])
    ctrl._set_provider_models_enabled(group_key, enabled=True)
    assert all(model_entry_enabled(e) for e in ctrl.models)
    parent = ctrl._find_provider_item(group_key)
    assert parent is not None
    for i in range(parent.childCount()):
        assert model_row_enabled(parent.child(i), column=ENABLED_COLUMN)
    ctrl._set_provider_models_enabled(group_key, enabled=False)
    assert not any(model_entry_enabled(e) for e in ctrl.models)


def test_expand_and_collapse_all_providers(qapp: QApplication, qtbot) -> None:
    """Expand all / Collapse all toggle every provider group."""
    dialog = SettingsDialog(ThemeManager(qapp))
    qtbot.addWidget(dialog)
    dialog._ensure_ai_models_page()
    ctrl = dialog._ai_controller
    assert ctrl is not None
    ctrl.models = [
        _entry("m1"),
        {**_entry("m2"), "provider": "ollama", "model": "ollama/llama3", "auth_ref": "ai:m2"},
    ]
    ctrl._reload_tree()
    _wait_for_ai_tree(ctrl, qtbot)
    assert ctrl._tree.topLevelItemCount() == 2
    ctrl._collapse_all_provider_groups()
    for i in range(ctrl._tree.topLevelItemCount()):
        item = ctrl._tree.topLevelItem(i)
        assert item is not None
        assert not item.isExpanded()
    ctrl._expand_all_provider_groups()
    for i in range(ctrl._tree.topLevelItemCount()):
        item = ctrl._tree.topLevelItem(i)
        assert item is not None
        assert item.isExpanded()
