"""Read-only detail tabs for :class:`HistoryPanel`."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.code_editor import CodeEditorWidget


class _HistoryPanelDetailTabsMixin:
    """Build Headers / Request Headers / Request Body tabs on ``_detail_tabs``."""

    _detail_tabs: QTabWidget

    def _refresh_request_body_view(self, _mode: str | None = None) -> None: ...

    def _make_copy_btn(self, slot: object) -> QPushButton:
        return QPushButton()

    def _copy_editor(self, editor: CodeEditorWidget) -> None: ...

    def _make_empty_label(self, text: str) -> QLabel:
        return QLabel()

    _headers_edit: CodeEditorWidget
    _headers_empty_label: QLabel
    _req_headers_edit: CodeEditorWidget
    _req_headers_empty_label: QLabel
    _req_body_edit: CodeEditorWidget
    _req_body_empty_label: QLabel
    _req_body_view_combo: QComboBox

    def _build_headers_tab(self) -> None:
        """Construct the Headers tab."""
        editor, empty, _ = self._build_readonly_tab("Headers", "No response headers")
        self._headers_edit = editor
        self._headers_empty_label = empty

    def _build_request_headers_tab(self) -> None:
        """Construct the Request Headers tab."""
        editor, empty, _ = self._build_readonly_tab("Request Headers", "No request headers")
        self._req_headers_edit = editor
        self._req_headers_empty_label = empty

    def _build_request_body_tab(self) -> None:
        """Construct the Request Body tab with Pretty/Raw combo."""
        editor, empty, combo = self._build_readonly_tab(
            "Request Body",
            "No request body",
            view_combo=True,
        )
        self._req_body_edit = editor
        self._req_body_empty_label = empty
        assert combo is not None
        self._req_body_view_combo = combo
        self._req_body_view_combo.currentTextChanged.connect(self._refresh_request_body_view)

    def _build_readonly_tab(
        self,
        title: str,
        empty_text: str,
        *,
        view_combo: bool = False,
    ) -> tuple[CodeEditorWidget, QLabel, QComboBox | None]:
        """Build a read-only tab with optional Pretty/Raw combo."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)
        combo: QComboBox | None = None
        if view_combo:
            combo = QComboBox()
            combo.addItems(["Pretty", "Raw"])
            combo.setFixedWidth(90)
            toolbar.addWidget(combo)
        toolbar.addStretch()
        editor = CodeEditorWidget(read_only=True)
        copy_btn = self._make_copy_btn(lambda e=editor: self._copy_editor(e))
        toolbar.addWidget(copy_btn)
        layout.addLayout(toolbar)
        empty_label = self._make_empty_label(empty_text)
        layout.addWidget(empty_label, 1)
        layout.addWidget(editor, 1)
        self._detail_tabs.addTab(tab, title)
        return editor, empty_label, combo
