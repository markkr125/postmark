"""Tests for script Problems tab (language-server diagnostics list)."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTabWidget

from services.lsp.client import Diagnostic
from ui.request.request_editor.scripts.lsp_problems_tab import (
    ScriptLspProblemsTab,
    format_problem_line,
)
from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel
from ui.widgets.code_editor.editor_widget import CodeEditorWidget


class TestScriptLspProblemsTab:
    """``ScriptLspProblemsTab`` binds to ``CodeEditorWidget.lsp_diagnostics_changed``."""

    def test_lists_diagnostics_and_clears(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)

        d = Diagnostic(
            line=2,
            column=0,
            end_line=2,
            end_column=3,
            severity="error",
            message="not defined",
            source="deno-ts",
        )
        editor.notify_lsp_diagnostics([d])
        assert tab._list.count() == 1
        assert tab._list.item(0).text() == format_problem_line(d)
        assert "Ln 3, Col 1" in tab._list.item(0).text()
        assert "not defined" in tab._list.item(0).text()

        editor.notify_lsp_diagnostics([])
        assert tab._list.count() == 0
        assert tab._stack.currentIndex() == 0

    def test_sorts_by_position(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)

        second = Diagnostic(1, 0, 1, 1, "warning", "b", "x")
        first = Diagnostic(0, 5, 0, 6, "error", "a", "x")
        editor.notify_lsp_diagnostics([second, first])
        assert tab._list.count() == 2
        assert "a" in tab._list.item(0).text()
        assert "b" in tab._list.item(1).text()

    def test_click_navigates_to_diagnostic(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)
        editor.setPlainText("line0\nline1\nline2\n")
        d = Diagnostic(2, 0, 2, 5, "error", "msg", "src")
        editor.notify_lsp_diagnostics([d])
        item = tab._list.item(0)
        assert item is not None
        tab._list.itemClicked.emit(item)
        assert editor.textCursor().blockNumber() == 2

    def test_severity_colours_differ(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)
        editor.notify_lsp_diagnostics(
            [
                Diagnostic(0, 0, 0, 1, "error", "e", "s"),
                Diagnostic(1, 0, 1, 1, "warning", "w", "s"),
            ]
        )
        err_rgb = tab._list.item(0).foreground().color().rgba()
        warn_rgb = tab._list.item(1).foreground().color().rgba()
        assert err_rgb != warn_rgb

    def test_problem_rows_have_severity_icons(self, qapp, qtbot) -> None:
        """Each row gets a non-null Phosphor icon matching severity."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)
        editor.notify_lsp_diagnostics(
            [
                Diagnostic(0, 0, 0, 1, "error", "e", "s"),
                Diagnostic(1, 0, 1, 1, "hint", "h", "s"),
            ]
        )
        assert not tab._list.item(0).icon().isNull()
        assert not tab._list.item(1).icon().isNull()

    def test_selection_preserves_severity_foreground_brush(self, qapp, qtbot) -> None:
        """Selection must not replace row foreground — severity hues stay readable."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)
        editor.notify_lsp_diagnostics([Diagnostic(0, 0, 0, 1, "hint", "hint body", "s")])
        item = tab._list.item(0)
        assert item is not None
        before = item.foreground().color().rgba()
        tab._list.setCurrentItem(item)
        tab._list.setCurrentRow(0)
        qapp.processEvents()
        assert item.foreground().color().rgba() == before

    def test_copy_problem_line_sets_clipboard(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)
        d = Diagnostic(1, 2, 1, 3, "info", "hello", "pyright")
        editor.notify_lsp_diagnostics([d])
        item = tab._list.item(0)
        assert item is not None
        tab._copy_problem_line(item)
        assert QGuiApplication.clipboard().text() == format_problem_line(d)

    def test_problem_count_changed_emits(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        tab.set_editor(editor)
        counts: list[int] = []
        tab.problem_count_changed.connect(counts.append)
        d = Diagnostic(0, 0, 0, 1, "error", "x", "s")
        editor.notify_lsp_diagnostics([d])
        editor.notify_lsp_diagnostics([])
        assert counts == [1, 0]

    def test_empty_state_in_bordered_frame(self, qapp, qtbot) -> None:
        """Empty Problems view uses ``scriptLspProblemsEmptyFrame`` (QSS matches list)."""
        tab = ScriptLspProblemsTab()
        qtbot.addWidget(tab)
        host = tab._stack.widget(0)
        assert host is not None
        assert host.objectName() == "scriptLspProblemsEmptyFrame"


class TestScriptOutputPanelProblemsBinding:
    """``ScriptOutputPanel`` exposes Output | Problems tabs and ``bind_script_editor``."""

    def test_bind_and_tabs_present(self, qapp, qtbot) -> None:
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        panel = ScriptOutputPanel(script_type="pre_request")
        qtbot.addWidget(panel)
        panel.bind_script_editor(editor)

        tabs = panel.findChild(QTabWidget, "scriptOutputTabs")
        assert tabs is not None
        assert tabs.count() == 3
        assert tabs.tabText(0) == "Output"
        assert tabs.tabText(1) == "Debugger"
        assert tabs.tabText(2) == "Problems (0)"

        tabs.setCurrentIndex(2)
        d = Diagnostic(0, 0, 0, 1, "error", "x", "src")
        editor.notify_lsp_diagnostics([d])
        assert panel._problems_tab._list.count() == 1
        assert tabs.tabText(2) == "Problems (1)"
