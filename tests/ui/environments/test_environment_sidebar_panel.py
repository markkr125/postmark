"""Tests for EnvironmentSidebarPanel (left column global environment picker)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton

from ui.environments.environment_sidebar_panel import EnvironmentSidebarPanel
from ui.widgets.sidebar_section_info import ENVIRONMENTS_INTRO, SidebarSectionInfoPopup


def _name_labels(panel: EnvironmentSidebarPanel) -> list[QLabel]:
    """Return environment name labels in visual order (top to bottom)."""
    labels = panel.findChildren(QLabel, "environmentSidebarNameLabel")
    return sorted(labels, key=lambda lb: lb.mapTo(panel, lb.rect().topLeft()).y())


def _set_active_buttons(panel: EnvironmentSidebarPanel) -> list[QPushButton]:
    """Return **Set active** buttons in visual order (top to bottom)."""
    buttons = panel.findChildren(QPushButton, "environmentSidebarSetActiveButton")
    return sorted(buttons, key=lambda b: b.mapTo(panel, b.rect().topLeft()).y())


def _clear_buttons(panel: EnvironmentSidebarPanel) -> list[QPushButton]:
    """Return **Clear** buttons (active row only, typically one)."""
    return panel.findChildren(QPushButton, "environmentSidebarClearButton")


class TestEnvironmentSidebarPanel:
    """Behaviour of the resizable environments section under collections."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Panel starts with no active environment."""
        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        assert panel.current_environment_id() is None
        assert _name_labels(panel) == []

    def test_refresh_builds_rows(self, qapp: QApplication, qtbot) -> None:
        """refresh() loads environments from the service layer."""
        from services.environment_service import EnvironmentService

        EnvironmentService.create_environment("SidebarEnvA")

        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        panel.refresh()
        names = [lb.text() for lb in _name_labels(panel)]
        assert len(names) >= 1
        assert "SidebarEnvA" in names

    def test_active_mutual_exclusion(self, qapp: QApplication, qtbot) -> None:
        """Only one row may be active; **Set active** switches which row shows **Clear**."""
        from services.environment_service import EnvironmentService

        EnvironmentService.create_environment("ExA")
        EnvironmentService.create_environment("ExB")

        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        panel.refresh()

        set_btns = _set_active_buttons(panel)
        assert len(set_btns) >= 2
        set_btns[0].click()
        assert panel.current_environment_id() is not None
        assert len(_clear_buttons(panel)) == 1

        set_btns = _set_active_buttons(panel)
        assert len(set_btns) >= 1
        set_btns[0].click()
        assert len(_clear_buttons(panel)) == 1
        assert panel.current_environment_id() is not None

    def test_clear_active_emits_none(self, qapp: QApplication, qtbot) -> None:
        """**Clear** on the active row clears global selection."""
        from services.environment_service import EnvironmentService

        EnvironmentService.create_environment("ExClear")

        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        panel.refresh()

        _set_active_buttons(panel)[0].click()
        assert panel.current_environment_id() is not None

        with qtbot.waitSignal(panel.environment_changed, timeout=1000) as blocker:
            _clear_buttons(panel)[0].click()
        assert blocker.args == [None]
        assert panel.current_environment_id() is None

    def test_manage_emits(self, qapp: QApplication, qtbot) -> None:
        """Manage button emits manage_requested."""
        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        with qtbot.waitSignal(panel.manage_requested, timeout=1000):
            panel._manage_btn.click()

    def test_environments_info_popup(self, qapp: QApplication, qtbot) -> None:
        """Info button opens the environments explainer popup."""
        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        panel.show()
        qtbot.waitExposed(panel)

        info_btn = panel.findChild(QToolButton, "sidebarSectionInfoButton")
        assert info_btn is not None

        panel._toggle_section_info()
        popup = panel._info_popup
        assert popup is not None
        assert isinstance(popup, SidebarSectionInfoPopup)
        assert popup.isVisible()

        texts = [label.text() for label in popup.findChildren(QLabel)]
        assert "Environments" in texts
        assert ENVIRONMENTS_INTRO in texts

        close_btn = popup.findChild(QToolButton, "infoPopupCloseButton")
        assert close_btn is not None
        close_btn.click()
        assert not popup.isVisible()

    def test_empty_list_shows_hint_click_emits_manage(self, qapp: QApplication, qtbot) -> None:
        """With no environments, a hint is shown; clicking it matches **Manage**."""
        panel = EnvironmentSidebarPanel()
        qtbot.addWidget(panel)
        panel.refresh()

        hint = panel.findChild(QLabel, "environmentSidebarEmptyHint")
        assert hint is not None

        with qtbot.waitSignal(panel.manage_requested, timeout=1000):
            qtbot.mouseClick(hint, Qt.MouseButton.LeftButton)
