"""UI tests for Settings → AI → Agents page."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QSpinBox

from services.ai.chat.chat_run_limits import max_concurrent_chat_runs
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
    settings.sync()
    yield
    settings.remove("ai/max_concurrent_runs")
    settings.remove("ai/max_parallel_subagents")
    settings.sync()


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


def test_initial_category_agents(qapp: QApplication, qtbot) -> None:
    """initial_category=Agents selects the Agents child under AI."""
    dialog = SettingsDialog(ThemeManager(qapp), initial_category="Agents")
    qtbot.addWidget(dialog)
    current = dialog._cat_tree.currentItem()
    assert current is not None and current.text(0) == "Agents"
    assert dialog._stack.currentIndex() == dialog._page_indices["ai_agents"]
    assert dialog._ai_agents_controller is not None
