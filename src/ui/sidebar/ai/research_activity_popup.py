"""Flyout showing workspace research progress and findings."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from ui.widgets.info_popup import InfoPopup


class AiResearchActivityPopup(InfoPopup):
    """Progress log + findings section for workspace research."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the research flyout layout."""
        super().__init__(parent)
        self.setObjectName("aiResearchActivityPopup")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        self._progress_label = QLabel("Progress")
        self._progress_label.setObjectName("aiResearchProgressHeader")
        root.addWidget(self._progress_label)

        self._progress = QTextEdit()
        self._progress.setObjectName("aiResearchProgressLog")
        self._progress.setReadOnly(True)
        self._progress.setMaximumHeight(120)
        root.addWidget(self._progress)

        self._findings_header = QLabel("Findings")
        self._findings_header.setObjectName("aiResearchFindingsHeader")
        root.addWidget(self._findings_header)

        self._findings = QTextEdit()
        self._findings.setObjectName("aiResearchFindingsBody")
        self._findings.setReadOnly(True)
        self._findings.setMinimumHeight(160)
        root.addWidget(self._findings)

    def set_progress_lines(self, lines: list[str]) -> None:
        """Replace the progress log text."""
        self._progress.setPlainText("\n".join(lines))

    def set_findings_text(self, text: str) -> None:
        """Replace the findings section."""
        self._findings.setPlainText(text)

    def show_near(self, anchor: QWidget) -> None:
        """Show the popup below *anchor*."""
        self.adjustSize()
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(pos)
        self.show()
        self.raise_()

    def toggle_near(self, anchor: QWidget) -> None:
        """Toggle visibility anchored to *anchor*."""
        if self.isVisible():
            self.hide()
        else:
            self.show_near(anchor)
