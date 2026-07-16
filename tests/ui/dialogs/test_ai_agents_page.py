"""UI tests for Settings → AI → Agents page."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QCheckBox, QListWidget, QPushButton, QSpinBox

from services.ai.chat.chat_run_limits import max_concurrent_chat_runs
from services.ai.chat.mutation.auto_approve import add_rule, clear_rules, list_rules
from services.ai.chat.subagent_limits import max_parallel_subagents
from ui.dialogs.settings.ai_agents import build_ai_agents_page
from ui.dialogs.settings_dialog import SettingsDialog
from ui.styling.theme_manager import ThemeManager


@pytest.fixture(autouse=True)
def _clear_agent_settings() -> Iterator[None]:
    """Use an isolated QSettings scope for each test."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/max_concurrent_runs")
    settings.remove("ai/max_parallel_subagents")
    settings.remove("ai/agent_auto_approve_rules")
    settings.sync()
    clear_rules()
    yield
    settings.remove("ai/max_concurrent_runs")
    settings.remove("ai/max_parallel_subagents")
    settings.remove("ai/agent_auto_approve_rules")
    settings.sync()
    clear_rules()


def test_agents_page_builds_spinbox(qapp: QApplication, qtbot) -> None:
    """Agents page exposes the concurrent-run spinbox with the persisted default."""
    page, ctrl = build_ai_agents_page(lambda: None)
    qtbot.addWidget(page)
    spin = page.findChild(QSpinBox, "aiAgentsConcurrentRunsSpin")
    assert spin is not None
    assert spin.value() == max_concurrent_chat_runs()
    ctrl.apply()
    assert max_concurrent_chat_runs() == spin.value()


def test_agents_page_parallel_subagents_spin(qapp: QApplication, qtbot) -> None:
    """Agents page exposes parallel subagent cap spinbox."""
    page, ctrl = build_ai_agents_page(lambda: None)
    qtbot.addWidget(page)
    spin = page.findChild(QSpinBox, "aiAgentsMaxParallelSubagentsSpin")
    assert spin is not None
    assert spin.value() == max_parallel_subagents()
    spin.setValue(7)
    ctrl.apply()
    assert max_parallel_subagents() == 7


def test_agents_page_persists_on_apply(qapp: QApplication, qtbot) -> None:
    """Changing the spinbox and applying writes ai/max_concurrent_runs."""
    page, ctrl = build_ai_agents_page(lambda: None)
    qtbot.addWidget(page)
    spin = page.findChild(QSpinBox, "aiAgentsConcurrentRunsSpin")
    assert spin is not None
    spin.setValue(16)
    ctrl.apply()
    assert max_concurrent_chat_runs() == 16


def test_agents_page_has_no_workspace_mutations_checkbox(qapp: QApplication, qtbot) -> None:
    """Agent edits are mode-gated; the old master checkbox is gone."""
    page, _ctrl = build_ai_agents_page(lambda: None)
    qtbot.addWidget(page)
    assert page.findChild(QCheckBox, "aiAgentsWorkspaceMutationsCheck") is None


def test_agents_page_auto_approve_list(qapp: QApplication, qtbot) -> None:
    """Auto-approve list shows persisted rules and Remove clears them."""
    assert add_rule("mutate:create:collection")
    page, _ctrl = build_ai_agents_page(lambda: None)
    qtbot.addWidget(page)
    lst = page.findChild(QListWidget, "aiAgentsAutoApproveList")
    assert lst is not None
    assert lst.count() == 1
    assert "Create collection" in (lst.item(0).text() if lst.item(0) else "")
    remove_all = page.findChild(QPushButton, "aiAgentsAutoApproveRemoveAll")
    assert remove_all is not None
    assert remove_all.isEnabled()
    remove_all.click()
    assert lst.count() == 0
    assert list_rules() == []
    add_btn = page.findChild(QPushButton, "aiAgentsAutoApproveAdd")
    remove_btn = page.findChild(QPushButton, "aiAgentsAutoApproveRemove")
    assert add_btn is not None
    assert remove_btn is not None
    assert remove_btn.isEnabled() is False


def test_initial_category_agents(qapp: QApplication, qtbot) -> None:
    """initial_category=Agents selects the Agents child under AI."""
    dialog = SettingsDialog(ThemeManager(qapp), initial_category="Agents")
    qtbot.addWidget(dialog)
    current = dialog._cat_tree.currentItem()
    assert current is not None and current.text(0) == "Agents"
    assert dialog._stack.currentIndex() == dialog._page_indices["ai_agents"]
    assert dialog._ai_agents_controller is not None
