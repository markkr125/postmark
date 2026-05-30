"""Shared key-value list helpers for sidebar panels.

Used by :class:`VariablesPanel` and :class:`DebugPanel` for consistent
variable rows, section headers with source dots, and separators.
Long debug values render in a collapsed row with an expand toggle.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi

# Key column width (debug output and variables sidebar).
DEFAULT_KV_KEY_WIDTH: int = 220
# Collapse long single-line blobs and any multi-line value into an expandable row.
_VALUE_COLLAPSE_CHAR_THRESHOLD: int = 120


class ElidedLabel(QLabel):
    """QLabel that elides text with an ellipsis when space is tight."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text: str) -> None:
        """Store full text and trigger repaint."""
        self._full_text = text
        super().setText(text)

    def paintEvent(self, _event: object) -> None:
        """Draw text with right-elision when it overflows."""
        painter = QPainter(self)
        fm = self.fontMetrics()
        elided = fm.elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            self.width(),
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter), elided)
        painter.end()


def _should_collapse_value(value: str) -> bool:
    """Return True when the value row should start collapsed with an expand control."""
    if "\n" in value or "\r" in value:
        return True
    return len(value) > _VALUE_COLLAPSE_CHAR_THRESHOLD


def _collapsed_preview(value: str, max_chars: int = 96) -> str:
    """One-line preview for the collapsed state."""
    one = value.replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    if len(one) > max_chars:
        return one[: max_chars - 1] + "\u2026"
    if "\n" in value:
        return one + " \u2026"
    return one


def _style_kv_line_edit(w: QLineEdit, *, is_key: bool) -> None:
    """Configure a borderless read-only line edit for key or value display."""
    w.setReadOnly(True)
    w.setFrame(False)
    w.setObjectName("variableKeyLabel" if is_key else "variableValueLabel")
    w.setCursor(Qt.CursorShape.IBeamCursor)
    w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    w.setSizePolicy(
        QSizePolicy.Policy.Expanding if not is_key else QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )


def add_section_header(layout: QVBoxLayout, title: str, source: str) -> None:
    """Add a section header with a colored source dot and *title*."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 8, 0, 4)
    row.setSpacing(6)

    dot = QLabel("\u2022")
    dot.setObjectName("sidebarSourceDot")
    dot.setProperty("varSource", source)
    dot.setFixedWidth(12)
    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(dot)

    label = QLabel(title)
    label.setObjectName("sidebarSectionLabel")
    row.addWidget(label)
    row.addStretch()

    layout.addLayout(row)


class _CollapsibleKvRow(QWidget):
    """One KV row whose value is hidden behind a toggle until expanded."""

    def __init__(
        self,
        name: str,
        value: str,
        tooltip: str | None,
        key_width: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._full_value = value
        self._expanded = False

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 4, 8, 4)
        root.setSpacing(10)

        self._key_edit = QLineEdit(name)
        self._key_edit.setFixedWidth(key_width)
        _style_kv_line_edit(self._key_edit, is_key=True)
        self._key_edit.setToolTip(name)
        root.addWidget(self._key_edit, 0, Qt.AlignmentFlag.AlignTop)

        # Toggle sits between key and value so it does not float when preview hides.
        toggle_rail = QWidget()
        toggle_rail.setFixedWidth(32)
        rail_lay = QHBoxLayout(toggle_rail)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)

        self._toggle = QToolButton()
        self._toggle.setObjectName("kvValueExpandToggle")
        self._icon_size = 14
        self._toggle.setIcon(phi("caret-right", size=self._icon_size))
        self._toggle.setAutoRaise(True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._toggle.setFixedSize(28, 28)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setToolTip("Show full value")
        self._toggle.clicked.connect(self._on_toggle)
        rail_lay.addStretch()
        rail_lay.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        rail_lay.addStretch()
        root.addWidget(toggle_rail, 0, Qt.AlignmentFlag.AlignTop)

        value_host = QWidget()
        value_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        value_col = QVBoxLayout(value_host)
        value_col.setSpacing(2)
        value_col.setContentsMargins(0, 0, 0, 0)

        self._preview = QLineEdit(_collapsed_preview(value))
        _style_kv_line_edit(self._preview, is_key=False)
        tip = tooltip if tooltip is not None else value
        self._preview.setToolTip(tip)
        value_col.addWidget(self._preview)

        self._body = QPlainTextEdit()
        self._body.setObjectName("variableValueEditor")
        self._body.setReadOnly(True)
        self._body.setPlainText(value)
        self._body.setMaximumBlockCount(0)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._body.setFixedHeight(0)
        self._body.hide()
        self._body.setToolTip(tip)
        value_col.addWidget(self._body)

        root.addWidget(value_host, 1, Qt.AlignmentFlag.AlignTop)

    def _on_toggle(self) -> None:
        """Expand or collapse the full-value editor."""
        self._expanded = not self._expanded
        if self._expanded:
            self._toggle.setIcon(phi("caret-down", size=self._icon_size))
            self._toggle.setToolTip("Hide full value")
            self._preview.hide()
            self._body.show()
            self._body.setMinimumHeight(72)
            self._body.setMaximumHeight(220)
        else:
            self._toggle.setIcon(phi("caret-right", size=self._icon_size))
            self._toggle.setToolTip("Show full value")
            self._preview.setText(_collapsed_preview(self._full_value))
            self._preview.show()
            self._body.hide()
            self._body.setFixedHeight(0)
            self._body.setMinimumHeight(0)
            self._body.setMaximumHeight(16777215)


def add_kv_row(
    layout: QVBoxLayout,
    name: str,
    value: str,
    tooltip: str | None = None,
    *,
    key_width: int = DEFAULT_KV_KEY_WIDTH,
) -> None:
    """Add a single key-value row; long values use a collapsed expander."""
    if _should_collapse_value(value):
        layout.addWidget(_CollapsibleKvRow(name, value, tooltip, key_width))
        return

    row = QHBoxLayout()
    row.setContentsMargins(18, 4, 8, 4)
    row.setSpacing(10)

    key_edit = QLineEdit(name)
    key_edit.setFixedWidth(key_width)
    _style_kv_line_edit(key_edit, is_key=True)
    key_edit.setToolTip(name)
    row.addWidget(key_edit)

    val_edit = QLineEdit(value)
    _style_kv_line_edit(val_edit, is_key=False)
    if tooltip is not None:
        val_edit.setToolTip(tooltip)
    row.addWidget(val_edit, 1)

    layout.addLayout(row)


def add_separator(layout: QVBoxLayout) -> None:
    """Add a thin horizontal separator line."""
    sep = QLabel()
    sep.setObjectName("sidebarSeparator")
    sep.setFixedHeight(1)
    layout.addWidget(sep)
