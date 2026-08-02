"""Inline pending-tool Approve card in the assistant transcript."""

from __future__ import annotations

from typing import TypedDict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.widgets.busy_spinner import BrailleSpinner


class PendingActionDict(TypedDict, total=False):
    """One pending mutate/execute action for Approve chrome."""

    tool_name: str
    kind: str | None
    kind_label: str
    title: str
    detail: str
    summary: str
    url: str
    risk: str


class PendingToolCard(QFrame):
    """Compact pending-action card with optional Allow / Reject / Always allow."""

    approve_requested = Signal()
    reject_requested = Signal()
    always_allow_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an empty card until an action is applied."""
        super().__init__(parent)
        self.setObjectName("aiChatPendingToolCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        header = QWidget(self)
        header.setObjectName("aiChatPendingToolHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._icon = QLabel(header)
        self._icon.setObjectName("aiChatPendingToolIcon")
        self._icon.setPixmap(phi("shield-warning", size=14).pixmap(14, 14))
        self._icon.setFixedSize(16, 16)
        header_row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title = QLabel(header)
        self._title.setObjectName("aiChatPendingToolTitle")
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._title, 1)
        root.addWidget(header)

        detail_row = QWidget(self)
        detail_layout = QHBoxLayout(detail_row)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)
        self._starting_spinner = BrailleSpinner(detail_row)
        self._starting_spinner.hide()
        detail_layout.addWidget(self._starting_spinner, 0, Qt.AlignmentFlag.AlignTop)

        self._detail = QLabel(detail_row)
        self._detail.setObjectName("aiChatPendingToolDetail")
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        detail_layout.addWidget(self._detail, 1)
        root.addWidget(detail_row)

        buttons = QWidget(self)
        buttons.setObjectName("aiChatPendingToolButtons")
        btn_row = QHBoxLayout(buttons)
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(8)

        self._allow = QPushButton("Allow")
        self._allow.setObjectName("aiChatPendingAllow")
        self._allow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._allow.clicked.connect(self.approve_requested.emit)
        btn_row.addWidget(self._allow)

        self._reject = QPushButton("Reject")
        self._reject.setObjectName("aiChatPendingReject")
        self._reject.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reject.clicked.connect(self.reject_requested.emit)
        btn_row.addWidget(self._reject)

        self._always = QPushButton("Always allow")
        self._always.setObjectName("aiChatPendingAlwaysAllow")
        self._always.setCursor(Qt.CursorShape.PointingHandCursor)
        self._always.clicked.connect(self.always_allow_requested.emit)
        btn_row.addWidget(self._always)

        btn_row.addStretch()
        root.addWidget(buttons)
        self._buttons = buttons

        self._kind: str | None = None
        self._continue_prompt = False
        self.hide()

    def kind(self) -> str | None:
        """Return the catalog kind for this card, if any."""
        return self._kind

    def apply_action(self, action: PendingActionDict, *, show_buttons: bool) -> None:
        """Update the card from *action* and toggle per-card buttons."""
        from services.ai.chat.confirmation_payload import CONTINUE_ITERATIONS_KIND

        title = (
            str(action.get("title") or action.get("kind_label") or "").strip() or "Pending action"
        )
        detail = str(action.get("detail") or action.get("summary") or "").strip()
        url = str(action.get("url") or "").strip()
        if url and url not in detail:
            detail = f"{detail}\n{url}" if detail else url
        if not detail:
            detail = title
        kind_raw = action.get("kind")
        self._kind = (
            str(kind_raw).strip() if isinstance(kind_raw, str) and kind_raw.strip() else None
        )
        self._continue_prompt = self._kind == CONTINUE_ITERATIONS_KIND
        risk = str(action.get("risk") or "normal").strip().lower()
        destructive = risk == "destructive" or (
            self._kind is not None and self._kind.startswith("mutate:delete:")
        )

        self._title.setText(title)
        self._detail.setText(detail)
        self._starting_spinner.stop()
        self._starting_spinner.hide()
        self._icon.setPixmap(
            phi(
                "arrow-clockwise"
                if self._continue_prompt
                else ("warning-circle" if destructive else "shield-warning"),
                size=14,
            ).pixmap(14, 14)
        )
        self.setProperty("risk", "destructive" if destructive else "normal")
        style = self.style()
        style.unpolish(self)
        style.polish(self)

        if self._continue_prompt:
            self._allow.setText("Continue")
            self._reject.setText("Stop")
            self._always.hide()
            self._always.setEnabled(False)
        else:
            self._allow.setText("Allow")
            self._reject.setText("Reject")
            self._always.show()
            self._always.setEnabled(bool(self._kind))
            if self._kind:
                from services.ai.chat.mutation.auto_approve import kind_label

                self._always.setText(f"Always allow: {kind_label(self._kind)}")
            else:
                self._always.setText("Always allow")
        self._buttons.setVisible(show_buttons)
        self.show()

    def set_starting(self) -> None:
        """Disable approval controls and show immediate execution feedback."""
        for button in (self._allow, self._reject, self._always):
            button.setEnabled(False)
            button.setCursor(Qt.CursorShape.ArrowCursor)
        self._starting_spinner.show()
        self._starting_spinner.start()
        verb = "Continuing…" if self._continue_prompt else "Starting…"
        suffix = f" — {verb}"
        if not self._detail.text().endswith(suffix):
            text = self._detail.text()
            for old in (" — Starting…", " — Continuing…"):
                if text.endswith(old):
                    text = text[: -len(old)]
                    break
            self._detail.setText(f"{text}{suffix}")


__all__ = ["PendingActionDict", "PendingToolCard"]
