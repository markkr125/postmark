"""Custom delegate that paints method badges for request items in the tree.

Using a ``QStyledItemDelegate`` instead of per-row ``setItemWidget`` avoids
creating thousands of ``QWidget`` / ``QLabel`` objects — saving ~50-60 KB per
request item in memory.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QWidget,
)

from ui.collections.tree.constants import (
    ITEM_TYPE_SCRIPT,
    ROLE_ITEM_TYPE,
    ROLE_LANGUAGE,
    ROLE_METHOD,
    ROLE_MODULE_FORMAT,
    is_leaf_item_type,
)
from ui.local_scripts.script_filename import (
    SCRIPT_TREE_ICON_SIZE,
    script_basename_from_stored,
    script_file_extension,
    script_name_rect,
    script_tooltip,
)
from ui.styling.language_icons import language_icon_pixmap, resolve_script_language
from ui.styling.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    BADGE_MIN_WIDTH,
    COLOR_TEXT_MUTED,
    TREE_ROW_HEIGHT,
    method_color,
    method_short_label,
)
from ui.widgets.sidebar_section_info import SidebarSectionInfoPopup
from ui.widgets.sidebar_tree_row_info import (
    name_rect_before_info,
    paint_tree_row_info_button,
    script_info_body,
    show_tree_row_info_popup,
    tree_row_info_editor_event,
)

# Horizontal gap between badge/icon and name label (px).
_BADGE_NAME_SPACING = 6

# Left padding before the badge or language icon (px).
_LEFT_PADDING = 2

# Square language icon size in the tree (matches ``BADGE_HEIGHT``).
_SCRIPT_ICON_SIZE = SCRIPT_TREE_ICON_SIZE


class CollectionTreeDelegate(QStyledItemDelegate):
    """Paint method badge + request name without creating child widgets.

    Folder items fall through to the default ``QStyledItemDelegate``
    implementation so they keep their standard icon + text rendering.
    Local-script leaves also paint a trailing (i) info control.
    """

    def __init__(
        self,
        tree: QTreeWidget,
        *,
        tree_kind: str = "collections",
        parent: QWidget | None = None,
    ) -> None:
        """Attach to *tree*; show row (i) only for ``local_scripts`` script leaves."""
        super().__init__(parent or tree)
        self._tree = tree
        self._tree_kind = tree_kind
        self._info_popup: SidebarSectionInfoPopup | None = None

    # ------------------------------------------------------------------
    # QStyledItemDelegate overrides
    # ------------------------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint a coloured method badge followed by the request name."""
        item_type = index.data(ROLE_ITEM_TYPE)
        if not is_leaf_item_type(item_type):
            super().paint(painter, option, index)
            return

        # 1. Let the style draw selection / hover background
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            # Draw background only — suppress text and icon.
            opt = QStyleOptionViewItem(option)
            opt.text = ""
            opt.icon = QIcon()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)

        method = index.data(ROLE_METHOD) or "GET"
        language = index.data(ROLE_LANGUAGE)
        # Read the display name from the QTreeWidgetItem's column 1 text
        tree = self.parent()
        name = ""
        if isinstance(tree, QTreeWidget):
            item = tree.itemFromIndex(index)
            if item is not None:
                name = item.text(1) or ""
                if item_type == ITEM_TYPE_SCRIPT and language is None:
                    language = item.data(0, ROLE_LANGUAGE)
        rect: QRect = option.rect  # type: ignore[assignment]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = option.palette  # type: ignore[assignment]
        text_color = palette.text().color()

        badge_x = rect.left() + _LEFT_PADDING
        badge_y = rect.top() + (rect.height() - BADGE_HEIGHT) // 2

        if item_type == ITEM_TYPE_SCRIPT:
            lang = resolve_script_language(language, method_badge=method)
            icon = language_icon_pixmap(lang, size=_SCRIPT_ICON_SIZE)
            icon_rect = QRect(badge_x, badge_y, _SCRIPT_ICON_SIZE, _SCRIPT_ICON_SIZE)
            painter.drawPixmap(icon_rect, icon)
            mod_fmt = index.data(ROLE_MODULE_FORMAT) or "esm"
            if isinstance(tree, QTreeWidget):
                item = tree.itemFromIndex(index)
                if item is not None:
                    basename = script_basename_from_stored(name)
                    item.setToolTip(0, script_tooltip(basename, lang, mod_fmt))
            name_rect = script_name_rect(rect)
            if self._tree_kind == "local_scripts":
                name_rect = name_rect_before_info(name_rect, rect)
            self._paint_script_label(painter, name, lang, mod_fmt, name_rect, text_color)
            if self._tree_kind == "local_scripts":
                paint_tree_row_info_button(painter, rect)
            painter.restore()
            return
        else:
            badge_rect = QRect(badge_x, badge_y, BADGE_MIN_WIDTH, BADGE_HEIGHT)
            bg_colour = QColor(method_color(method))
            painter.setBrush(bg_colour)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, BADGE_BORDER_RADIUS, BADGE_BORDER_RADIUS)

            badge_font = QFont(painter.font())
            badge_font.setPixelSize(BADGE_FONT_SIZE)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, method_short_label(method))
            name_x = badge_rect.right() + _BADGE_NAME_SPACING

        # Request / script name
        name_rect = QRect(name_x, rect.top(), rect.right() - name_x, rect.height())

        name_font = QFont(painter.font())
        name_font.setPixelSize(12)
        name_font.setBold(False)

        # Request name: keep normal text colour when selected (same as unfocused
        # tree text) so the row does not flip to white on the blue selection tint.
        painter.setPen(QPen(text_color))
        painter.setFont(name_font)

        # Elide text if it exceeds the available width
        fm = QFontMetrics(name_font)
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        painter.restore()

    def _paint_script_label(
        self,
        painter: QPainter,
        basename: str,
        language: str,
        module_format: str,
        name_rect: QRect,
        text_color: QColor,
    ) -> None:
        """Paint basename in normal colour and extension in muted colour."""
        base = script_basename_from_stored(basename)
        ext = script_file_extension(language, module_format)
        name_font = QFont(painter.font())
        name_font.setPixelSize(12)
        name_font.setBold(False)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        ext_width = fm.horizontalAdvance(ext) if ext else 0
        base_max = max(0, name_rect.width() - ext_width)
        elided_base = fm.elidedText(base or "", Qt.TextElideMode.ElideRight, base_max)
        painter.setPen(QPen(text_color))
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignVCenter,
            elided_base,
        )
        if ext and ext_width > 0:
            base_width = fm.horizontalAdvance(elided_base)
            ext_rect = QRect(
                name_rect.left() + base_width,
                name_rect.top(),
                name_rect.width() - base_width,
                name_rect.height(),
            )
            painter.setPen(QPen(QColor(COLOR_TEXT_MUTED)))
            painter.drawText(ext_rect, Qt.AlignmentFlag.AlignVCenter, ext)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        """Return a fixed row height for request items."""
        item_type = index.data(ROLE_ITEM_TYPE)
        if is_leaf_item_type(item_type):
            return QSize(0, TREE_ROW_HEIGHT)
        return super().sizeHint(option, index)

    def editorEvent(  # type: ignore[override]
        self,
        event: QEvent,
        model,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Open script row info when the trailing (i) is clicked."""
        if self._tree_kind != "local_scripts":
            return super().editorEvent(event, model, option, index)
        if index.data(ROLE_ITEM_TYPE) != ITEM_TYPE_SCRIPT:
            return super().editorEvent(event, model, option, index)

        if tree_row_info_editor_event(
            event,
            tree=self._tree,
            index=index,
            on_info=lambda: self._toggle_script_info(index),
        ):
            return True
        return super().editorEvent(event, model, option, index)

    def _toggle_script_info(self, index: QModelIndex | QPersistentModelIndex) -> None:
        """Show or hide script metadata for *index*."""
        item = self._tree.itemFromIndex(index)
        if item is None:
            return
        basename = str(item.text(1) or "")
        language = str(index.data(ROLE_LANGUAGE) or "javascript")
        module_format = str(index.data(ROLE_MODULE_FORMAT) or "esm")
        title = script_basename_from_stored(basename) or "Script"
        body = script_info_body(
            basename=basename,
            language=language,
            module_format=module_format,
        )
        if self._info_popup is not None and self._info_popup.isVisible():
            self._info_popup.close()
            return
        self._info_popup = SidebarSectionInfoPopup(title, body, self._tree.window())
        show_tree_row_info_popup(self._info_popup, self._tree, index)

    def createEditor(  # type: ignore[override]
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget | None:
        """Suppress the default editor for request items.

        Request rename is handled by ``CollectionTree._rename_request``
        which creates its own ``QLineEdit`` overlay.
        """
        item_type = index.data(ROLE_ITEM_TYPE)
        if is_leaf_item_type(item_type):
            return None
        return super().createEditor(parent, option, index)
