"""Create New dialog for local script folders and scripts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from database.models.local_scripts.virtual_paths import MODULE_FORMAT_COMMONJS, MODULE_FORMAT_ESM
from ui.collections.new_item_popup import _Tile
from ui.request.request_editor.scripts.script_language import code_to_display, normalise_script_code
from ui.styling.language_icons import language_icon_pixmap


class _LanguageTile(QPushButton):
    """Clickable tile with a brand language icon and label."""

    def __init__(
        self,
        language: str,
        label: str,
        *,
        module_format: str = MODULE_FORMAT_ESM,
        parent: QWidget | None = None,
    ) -> None:
        """Build a tile for *language* (javascript | typescript | python)."""
        super().__init__(parent)
        self._language = normalise_script_code(language)
        self._module_format = module_format
        self.setObjectName("newItemTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(148, 116)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon_label.setPixmap(language_icon_pixmap(self._language, size=40))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)

        text_label = QLabel(label)
        text_label.setObjectName("newItemTileLabel")
        text_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        text_label.setWordWrap(True)
        text_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        text_label.setMaximumWidth(128)
        text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(text_label, 0, Qt.AlignmentFlag.AlignHCenter)

    @property
    def language(self) -> str:
        """Normalized language code for this tile."""
        return self._language

    @property
    def module_format(self) -> str:
        """Module format (``esm`` or ``commonjs``) for this tile."""
        return self._module_format


class NewLocalScriptItemPopup(QDialog):
    """Modal dialog to create a new local script (by language) or folder."""

    new_script_clicked = Signal(str, str)  # language, module_format
    new_folder_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the tile grid for language scripts vs folder creation."""
        super().__init__(parent)
        self.setWindowTitle("Create New")
        self.setObjectName("newItemPopup")
        self.setFixedSize(600, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        title = QLabel("What do you want to create?")
        title.setObjectName("newItemTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tiles: list[tuple[int, int, str, str, str]] = [
            (0, 0, "javascript", code_to_display("javascript"), MODULE_FORMAT_ESM),
            (0, 1, "typescript", code_to_display("typescript"), MODULE_FORMAT_ESM),
            (0, 2, "python", code_to_display("python"), MODULE_FORMAT_ESM),
            (1, 0, "javascript", "JavaScript\n(CommonJS)", MODULE_FORMAT_COMMONJS),
        ]
        for row, col, code, label, mod_fmt in tiles:
            tile = _LanguageTile(code, label, module_format=mod_fmt, parent=self)
            tile.clicked.connect(
                lambda checked=False, lang=code, fmt=mod_fmt: self._on_script(lang, fmt)
            )
            grid.addWidget(tile, row, col)

        folder_tile = _Tile("folder", "Folder", self)
        folder_tile.clicked.connect(self._on_folder)
        grid.addWidget(folder_tile, 1, 1)

        layout.addLayout(grid)
        layout.addStretch()

    def _on_script(self, language: str, module_format: str) -> None:
        self.new_script_clicked.emit(normalise_script_code(language), module_format)
        self.accept()

    def _on_folder(self) -> None:
        self.new_folder_clicked.emit()
        self.accept()
