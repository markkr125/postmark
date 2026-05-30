"""Dialog listing inherited scripts in execution order with per-request disable."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.script_service import normalize_disabled_inherited
from ui.styling import theme
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget

logger = logging.getLogger(__name__)

_SCRIPT_TITLE = {"pre_request": "Pre-request", "test": "Post-response"}
_ST_IN_JSON = {
    "pre_request": "pre_request",
    "test": "test",
}
_CODE_VIEW_HEIGHT = 220
_BADGE_SIZE = 26


class InheritedChainDrawer(QDialog):
    """Modal listing inherited ancestor scripts with per-request enable toggles."""

    disabled_inherited_changed = Signal(list)
    edit_collection_requested = Signal(int)

    def __init__(
        self,
        parent: QWidget | None,
        *,
        script_type: str,
        blocks: list[dict[str, Any]],
        disabled_inherited: list[dict[str, int | str]],
        on_edit_collection_source: Callable[[int], None] | None = None,
    ) -> None:
        """Build the dialog with *blocks* and the current *disabled_inherited* set."""
        super().__init__(parent)
        self._on_edit_collection_source = on_edit_collection_source
        self._script_type = script_type
        self._st_json = _ST_IN_JSON[script_type]
        st_label = _SCRIPT_TITLE.get(script_type, "Script")
        self.setWindowTitle(f"Inherited {st_label} scripts")
        self.setModal(True)
        self.setMinimumSize(760, 560)
        self.resize(1000, 760)
        self.setAccessibleName(f"Inherited {st_label} scripts")

        self._other_st_entries: list[dict[str, int | str]] = [
            d
            for d in (disabled_inherited or [])
            if isinstance(d, dict) and d.get("script_type") not in (None, self._st_json)
        ]
        disabled_set = {
            (d["collection_id"], d["script_type"])
            for d in (disabled_inherited or [])
            if isinstance(d.get("collection_id"), int) and isinstance(d.get("script_type"), str)
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_help(len(blocks), script_type))
        root.addWidget(self._hsep())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body_host = QWidget()
        body = QVBoxLayout(body_host)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        self._checkboxes: list[tuple[int, QCheckBox]] = []
        total = len(blocks)
        for idx, b in enumerate(blocks, start=1):
            cid = int(b["collection_id"])
            is_off = (cid, self._st_json) in disabled_set
            body.addWidget(self._build_block(idx, total, b, cid, is_off))
        body.addStretch(1)

        scroll.setWidget(body_host)
        root.addWidget(scroll, 1)

        root.addWidget(self._hsep())
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.accept)
        btns.accepted.connect(self.accept)
        close_btn = btns.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setObjectName("outlineButton")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(btns)

    def _build_help(self, count: int, script_type: str) -> QWidget:
        order = (
            "top-to-bottom"
            if script_type == "pre_request"
            else "top-to-bottom (nearest folder first)"
        )
        word1 = "before" if script_type == "pre_request" else "after"
        if count == 1:
            line1 = f"1 script runs {word1} this request, {order}."
        else:
            line1 = f"{count} scripts run {word1} this request, {order}."
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        head = QLabel(line1)
        head.setStyleSheet(f"color: {theme.COLOR_TEXT}; font-weight: 600;")
        sub = QLabel(
            "Untick a row to skip it for this request only — siblings and other requests are unchanged."
        )
        sub.setStyleSheet(f"color: {theme.COLOR_TEXT_MUTED};")
        sub.setWordWrap(True)
        layout.addWidget(head)
        layout.addWidget(sub)
        return w

    def _hsep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(
            f"color: {theme.COLOR_BORDER}; background: {theme.COLOR_BORDER}; max-height: 1px;"
        )
        return f

    def _build_block(
        self,
        idx: int,
        total: int,
        b: dict[str, Any],
        cid: int,
        is_off: bool,
    ) -> QWidget:
        name = str(b.get("name", ""))
        code = str(b.get("code", ""))
        language = str(b.get("language", "javascript") or "javascript")
        line_count = max(
            1,
            code.count("\n") + (1 if code and not code.endswith("\n") else 0),
        )

        card = QFrame()
        card.setObjectName("inheritedBlockCard")
        card.setStyleSheet(
            f"QFrame#inheritedBlockCard {{"
            f" background: {theme.COLOR_HOVER_TREE_BG};"
            f" border: 1px solid {theme.COLOR_BORDER};"
            f" border-radius: 6px;"
            f" }}"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        badge = QLabel(str(idx))
        badge.setFixedSize(_BADGE_SIZE, _BADGE_SIZE)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {theme.COLOR_ACCENT};"
            f" color: {theme.COLOR_WHITE};"
            f" border-radius: {_BADGE_SIZE // 2}px;"
            f" font-weight: 700;"
        )
        badge.setToolTip(f"Execution order {idx} of {total}")
        header.addWidget(badge)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        title = QLabel(name)
        tfont = QFont(title.font())
        tfont.setBold(True)
        tfont.setPointSizeF(tfont.pointSizeF() + 1.0)
        title.setFont(tfont)
        title.setStyleSheet(f"color: {theme.COLOR_TEXT};")
        meta = QLabel(
            f"Collection \u00b7 {language.capitalize()} \u00b7 {line_count} line"
            f"{'s' if line_count != 1 else ''}"
        )
        meta.setStyleSheet(f"color: {theme.COLOR_TEXT_MUTED};")
        name_col.addWidget(title)
        name_col.addWidget(meta)
        header.addLayout(name_col, 1)

        edit_btn = QPushButton("Edit source")
        edit_btn.setObjectName("outlineButton")
        edit_btn.setIcon(phi("pencil-simple", size=14))
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Open the source collection to change this script")
        edit_btn.setAccessibleName(f"Edit source: {name}")
        # ``clicked`` emits ``(checked: bool)``; a bare ``lambda c=cid`` would bind
        # that bool to *c* and call ``_emit_edit(False)`` → collection id 0.
        edit_btn.clicked.connect(lambda _checked, c=cid: self._emit_edit(c))
        header.addWidget(edit_btn)

        enabled_cb = QCheckBox("Enabled")
        enabled_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        enabled_cb.setToolTip("When off, this script is skipped when sending this request")
        enabled_cb.setAccessibleName(
            f"Enabled: inherited script from {name} for this request (when checked)"
        )
        enabled_cb.blockSignals(True)
        enabled_cb.setChecked(not is_off)
        enabled_cb.blockSignals(False)
        self._checkboxes.append((cid, enabled_cb))
        header.addWidget(enabled_cb)

        outer.addLayout(header)

        # Opacity on the code area only so the header row (Edit source / Enabled)
        # never shares a QGraphicsEffect parent — some platforms mishandle hits or
        # painting for disabled-looking script blocks.
        code_host = QWidget(card)
        code_layout = QVBoxLayout(code_host)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)

        editor = CodeEditorWidget(read_only=True, parent=code_host)
        editor.set_language(language)
        editor.set_breakpoint_gutter_visible(False)
        editor.setFixedHeight(_CODE_VIEW_HEIGHT)
        editor.setFont(QFont("monospace"))
        editor.set_inherited_read_preview(True)
        editor.set_text(code)
        code_layout.addWidget(editor)
        outer.addWidget(code_host)

        opacity = QGraphicsOpacityEffect(code_host)
        opacity.setOpacity(0.5 if is_off else 1.0)
        code_host.setGraphicsEffect(opacity)

        t_init = QFont(title.font())
        t_init.setStrikeOut(bool(is_off))
        title.setFont(t_init)

        def _apply_state(enabled: bool) -> None:
            opacity.setOpacity(1.0 if enabled else 0.5)
            tf2 = QFont(title.font())
            tf2.setStrikeOut(not enabled)
            title.setFont(tf2)
            self._emit_disabled()

        enabled_cb.toggled.connect(_apply_state)
        return card

    def _emit_edit(self, collection_id: int) -> None:
        # Call synchronously so the host can record the id before ``accept()`` /
        # ``exec()`` returns (``edit_collection_requested`` may be queued across
        # QObject boundaries in some bindings).
        if self._on_edit_collection_source is not None:
            self._on_edit_collection_source(collection_id)
        n = self.receivers("2edit_collection_requested(int)")
        if n == 0 and self._on_edit_collection_source is None:
            logger.warning(
                "InheritedChainDrawer: edit_collection_requested has no receivers; "
                "collection_id=%s will not open a tab.",
                collection_id,
            )
        self.edit_collection_requested.emit(collection_id)
        self.accept()

    def _emit_disabled(self) -> None:
        new_list: list[dict[str, int | str]] = list(self._other_st_entries)
        for cid, cb in self._checkboxes:
            if not cb.isChecked():
                new_list.append({"collection_id": cid, "script_type": self._st_json})
        out = normalize_disabled_inherited(new_list)
        self.disabled_inherited_changed.emit([dict(d) for d in out])
