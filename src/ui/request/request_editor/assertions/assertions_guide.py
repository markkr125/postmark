"""Help dialog and launcher for the declarative Assertions tab."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui.styling import theme
from ui.styling.icons import phi

_ROW_HEADING = "Response checks without script code"
_HELP_BUTTON_LABEL = "How it works"
_HELP_DIALOG_TITLE = "Assertions"

_GUIDE_TITLE = _ROW_HEADING

_GUIDE_BODY_HTML = (
    "<p>Each row is a rule evaluated <b>after you Send</b>, once the response is back. "
    "Enabled rows compile into <code>pm.test</code> blocks and run with your "
    "post-response <b>Scripts</b> tests.</p>"
    "<p>Pass and fail results appear in the response <b>Test Results</b> tab under "
    "<b>Declarative Assertions</b>.</p>"
    "<p><b>Subject</b> examples:</p>"
    "<ul style='margin-top:4px;margin-bottom:4px;padding-left:1.2em'>"
    "<li><code>res.status</code> — HTTP status code</li>"
    "<li><code>res.time</code> — response time (ms)</li>"
    "<li><code>res.body</code> — response body text</li>"
    "<li><code>res.body.id</code> — JSON field (dot path)</li>"
    '<li><code>res.headers["Content-Type"]</code> — header value</li>'
    "</ul>"
    "<p>For loops, custom parsing, or multi-step logic, use the <b>Scripts</b> tab instead.</p>"
)

_SELECTABLE = (
    Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
)


def _help_dialog_html() -> str:
    """Return full selectable HTML for the help dialog."""
    return f"<h2 style='margin-top:0'>{_GUIDE_TITLE}</h2>{_GUIDE_BODY_HTML}"


class AssertionsHelpDialog(QDialog):
    """Modal explaining declarative assertion rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the help dialog with selectable body text and Close."""
        super().__init__(parent)
        self.setWindowTitle(_HELP_DIALOG_TITLE)
        self.setModal(True)
        self.resize(520, 440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        body = QTextBrowser(self)
        body.setObjectName("assertionsHelpBody")
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setOpenExternalLinks(False)
        body.setReadOnly(True)
        body.setTextInteractionFlags(_SELECTABLE)
        body.setHtml(_help_dialog_html())
        outer.addWidget(body, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setObjectName("outlineButton")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        outer.addWidget(buttons)


def build_assertions_help_button_row(parent: QWidget | None = None) -> QWidget:
    """Return a styled banner with heading + button opening :class:`AssertionsHelpDialog`."""
    host = QWidget(parent)
    host.setObjectName("assertionsHelpRow")

    layout = QHBoxLayout(host)
    layout.setContentsMargins(12, 8, 10, 8)
    layout.setSpacing(8)

    icon = QLabel(host)
    icon.setObjectName("assertionsHelpIcon")
    icon.setPixmap(phi("lightbulb", color=theme.COLOR_ACCENT, size=16).pixmap(16, 16))
    layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

    heading = QLabel(_ROW_HEADING, host)
    heading.setObjectName("assertionsHelpHeading")
    heading.setTextInteractionFlags(_SELECTABLE)
    layout.addWidget(heading, 0, Qt.AlignmentFlag.AlignVCenter)

    layout.addStretch()

    help_btn = QPushButton(_HELP_BUTTON_LABEL, host)
    help_btn.setObjectName("assertionsHowItWorksButton")
    help_btn.setIcon(phi("question"))
    help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    help_btn.setToolTip("Open a guide to declarative response checks")
    help_btn.clicked.connect(lambda: AssertionsHelpDialog(host.window()).exec())
    layout.addWidget(help_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    return host
