"""Breadcrumb bar showing the path from root collection to the current request.

The last segment is editable: double-clicking it starts inline rename.
Non-last segments are clickable — they emit ``item_clicked`` for navigation.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from ui.theme import COLOR_ACCENT, COLOR_BREADCRUMB_SEP, COLOR_TEXT_MUTED


class _EditableLabel(QWidget):
    """Label that becomes an inline QLineEdit on double-click.

    Signals:
        rename_requested(str): Emitted with the new text when the user
            commits a rename (Enter or focus-out).
    """

    rename_requested = Signal(str)

    def __init__(
        self,
        text: str,
        *,
        style: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the editable label."""
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = QLabel(text)
        self._label.setStyleSheet(style)
        self._label.setCursor(Qt.CursorShape.IBeamCursor)
        layout.addWidget(self._label)

        self._edit = QLineEdit(text)
        self._edit.setStyleSheet("font-size: 13px; padding: 0; margin: 0;")
        self._edit.hide()
        layout.addWidget(self._edit)

        self._edit.returnPressed.connect(self._commit)
        self._edit.installEventFilter(self)

        self._original_text = text

    # -- Public API ----------------------------------------------------

    def text(self) -> str:
        """Return the current label text."""
        return self._label.text()

    def set_text(self, text: str) -> None:
        """Update the displayed label text (non-editing)."""
        self._label.setText(text)
        self._original_text = text

    # -- Event handling ------------------------------------------------

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Enter edit mode on double-click."""
        self._start_edit()
        event.accept()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Handle Escape (cancel) and focus-out (commit) on the line edit."""
        if obj is self._edit:
            if event.type() == QEvent.Type.KeyPress:
                key_event: QKeyEvent = event  # type: ignore[assignment]
                if key_event.key() == Qt.Key.Key_Escape:
                    self._cancel()
                    return True
            elif event.type() == QEvent.Type.FocusOut:
                focus_event: QFocusEvent = event  # type: ignore[assignment]
                # Ignore focus loss from context menus / popups
                if focus_event.reason() not in (
                    Qt.FocusReason.PopupFocusReason,
                    Qt.FocusReason.MenuBarFocusReason,
                ):
                    self._commit()
                    return True
        return super().eventFilter(obj, event)

    # -- Internal helpers ----------------------------------------------

    def _start_edit(self) -> None:
        """Switch from label to inline line-edit."""
        self._original_text = self._label.text()
        self._edit.setText(self._original_text)
        self._label.hide()
        self._edit.show()
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._edit.selectAll()

    def _commit(self) -> None:
        """Accept the edit and emit ``rename_requested`` if text changed."""
        new_text = self._edit.text().strip()
        self._edit.hide()
        self._label.show()
        if not new_text:
            # Reject empty names — revert to original
            return
        if new_text != self._original_text:
            self._label.setText(new_text)
            self._original_text = new_text
            self.rename_requested.emit(new_text)

    def _cancel(self) -> None:
        """Cancel editing and revert to the original text."""
        self._edit.hide()
        self._label.show()


class BreadcrumbBar(QWidget):
    """Clickable breadcrumb trail showing collection > folder > request path.

    Signals:
        item_clicked(str, int): Emitted when a non-last breadcrumb segment
            is clicked with ``(item_type, item_id)``.
        last_segment_renamed(str): Emitted when the user renames the last
            breadcrumb segment (the current request/folder).
    """

    item_clicked = Signal(str, int)
    last_segment_renamed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the breadcrumb bar."""
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(6)
        self._layout.addStretch()

        # Reference to the editable last-segment widget (if any)
        self._editable_label: _EditableLabel | None = None
        # Metadata about the last segment for callers to identify it
        self._last_segment: dict | None = None

    def set_path(self, segments: list[dict]) -> None:
        """Update the displayed path.

        Each segment dict should have ``name``, ``type`` (``folder`` or
        ``request``), and ``id`` keys.
        """
        # Clear existing widgets
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        self._editable_label = None
        self._last_segment = None

        for i, seg in enumerate(segments):
            if i > 0:
                sep = QLabel("/")
                sep.setStyleSheet(
                    f"color: {COLOR_BREADCRUMB_SEP}; font-size: 13px;"
                    f" padding: 0 4px; font-weight: bold;"
                )
                self._layout.addWidget(sep)

            is_last = i == len(segments) - 1

            if is_last:
                # Editable last segment
                style = f"color: {COLOR_TEXT_MUTED}; font-size: 13px; font-weight: normal;"
                editable = _EditableLabel(seg["name"], style=style)
                editable.rename_requested.connect(self.last_segment_renamed.emit)
                self._layout.addWidget(editable)
                self._editable_label = editable
                self._last_segment = seg
            else:
                label = QLabel(seg["name"])
                style = (
                    f"color: {COLOR_ACCENT}; font-size: 13px;"
                    f" font-weight: 500; text-decoration: none;"
                )
                label.setStyleSheet(style)
                seg_type = seg["type"]
                seg_id = seg["id"]
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.setProperty("seg_type", seg_type)
                label.setProperty("seg_id", seg_id)
                label.installEventFilter(self)
                self._layout.addWidget(label)

        self._layout.addStretch()

    @property
    def last_segment_info(self) -> dict | None:
        """Return the metadata dict for the last breadcrumb segment."""
        return self._last_segment

    def update_last_segment_text(self, text: str) -> None:
        """Programmatically update the last segment's display text."""
        if self._editable_label is not None:
            self._editable_label.set_text(text)

    def clear(self) -> None:
        """Remove all breadcrumb segments."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        self._editable_label = None
        self._last_segment = None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Emit ``item_clicked`` when a breadcrumb segment is pressed."""
        if event.type() == QEvent.Type.MouseButtonPress:
            seg_type = obj.property("seg_type")
            seg_id = obj.property("seg_id")
            if seg_type is not None and seg_id is not None:
                self.item_clicked.emit(str(seg_type), int(seg_id))
                return True
        return super().eventFilter(obj, event)
