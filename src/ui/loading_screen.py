"""A visually appealing loading screen shown during app startup."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget


class LoadingScreen(QWidget):
    """A full-screen loading overlay with a pulsing logo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the loading screen."""
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        self._logo_label = QLabel()
        pixmap = QPixmap("data/images/logo.png")
        # Scale down if it's too large, but keep it crisp
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                200,
                200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._logo_label.setPixmap(pixmap)
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Opacity effect for pulsing
        self._opacity_effect = QGraphicsOpacityEffect(self._logo_label)
        self._logo_label.setGraphicsEffect(self._opacity_effect)

        # Animation
        self._animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._animation.setDuration(1500)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)  # Infinite loop
        self._animation.setKeyValueAt(0.0, 0.3)
        self._animation.setKeyValueAt(0.5, 1.0)
        self._animation.setKeyValueAt(1.0, 0.3)

        # Text
        self._text_label = QLabel("Loading Postmark...")
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._text_label.font()
        font.setPointSize(16)
        self._text_label.setFont(font)
        self._text_label.setStyleSheet("color: #888888;")

        layout.addWidget(self._logo_label)
        layout.addSpacing(20)
        layout.addWidget(self._text_label)

    def start_animation(self) -> None:
        """Start the pulsing animation."""
        self._animation.start()

    def stop_animation(self) -> None:
        """Stop the pulsing animation."""
        self._animation.stop()
        self._animation.stop()
