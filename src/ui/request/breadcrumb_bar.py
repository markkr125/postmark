"""Breadcrumb bar showing the path from root collection to the current request."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.theme import COLOR_ACCENT, COLOR_BREADCRUMB_SEP, COLOR_TEXT_MUTED


class BreadcrumbBar(QWidget):
    """Clickable breadcrumb trail showing collection > folder > request path.

    Signals:
        item_clicked(str, int): Emitted when a breadcrumb segment is
            clicked with ``(item_type, item_id)``.
    """

    item_clicked = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the breadcrumb bar."""
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 2, 8, 2)
        self._layout.setSpacing(4)
        self._layout.addStretch()

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

        for i, seg in enumerate(segments):
            if i > 0:
                sep = QLabel("\u203a")
                sep.setStyleSheet(
                    f"color: {COLOR_BREADCRUMB_SEP}; font-size: 12px; padding: 0 2px;"
                )
                self._layout.addWidget(sep)

            label = QLabel(seg["name"])
            is_last = i == len(segments) - 1
            color = COLOR_TEXT_MUTED if is_last else COLOR_ACCENT
            style = f"color: {color}; font-size: 12px;"
            if not is_last:
                style += " text-decoration: none;"
            label.setStyleSheet(style)

            if not is_last:
                seg_type = seg["type"]
                seg_id = seg["id"]
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.setProperty("seg_type", seg_type)
                label.setProperty("seg_id", seg_id)
                label.installEventFilter(self)

            self._layout.addWidget(label)

        self._layout.addStretch()

    def clear(self) -> None:
        """Remove all breadcrumb segments."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Emit ``item_clicked`` when a breadcrumb segment is pressed."""
        if event.type() == QEvent.Type.MouseButtonPress:
            seg_type = obj.property("seg_type")
            seg_id = obj.property("seg_id")
            if seg_type is not None and seg_id is not None:
                self.item_clicked.emit(str(seg_type), int(seg_id))
                return True
        return super().eventFilter(obj, event)
