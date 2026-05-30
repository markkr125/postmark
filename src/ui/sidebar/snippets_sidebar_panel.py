"""Left-flyout tree of user snippets: language → category → snippet."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.snippet_service import SnippetService, UserSnippetDict
from ui.sidebar.snippets_tree_constants import (
    KIND_CATEGORY,
    KIND_LANGUAGE,
    KIND_SNIPPET,
    ROLE_LANG_KEY,
    ROLE_NODE_KIND,
    ROLE_SNIPPET_BODY,
    ROLE_SNIPPET_CATEGORY,
    ROLE_SNIPPET_CONTEXT,
    ROLE_SNIPPET_COUNT,
    ROLE_SNIPPET_ID,
)
from ui.sidebar.snippets_tree_context import SnippetsTreeContextMenus
from ui.sidebar.snippets_tree_delegate import SnippetsTreeDelegate
from ui.sidebar.snippets_tree_rename import SnippetsInlineRename
from ui.styling.icons import phi
from ui.styling.language_icons import language_icon_pixmap
from ui.styling.theme import (
    LEFT_NAV_PANEL_MARGIN_H_LEFT_PX,
    LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX,
)
from ui.widgets.sidebar_section_info import (
    SNIPPETS_INTRO,
    SidebarSectionInfoPopup,
    make_sidebar_info_button,
    toggle_sidebar_section_info,
)
from ui.widgets.snippets.snippet_capture_dialog import SnippetCaptureDialog

_LIST_FRAME_SHIM_PX = 1
_LIST_BODY_PAD_H_PX = 3
_LIST_ROWS_BOTTOM_MARGIN_PX = 4
_PANEL_ROOT_BOTTOM_MARGIN_PX = 14
_PANEL_HEADER_LIST_GAP_PX = 6
_TREE_ICON_PX = 16

# Editor language keys passed to :class:`SnippetService` (not DB short codes).
_LANG_SPECS: tuple[tuple[str, str], ...] = (
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("python", "Python"),
)


class SnippetsSidebarPanel(QWidget):
    """Tree of user snippets with New and per-row edit (like local scripts)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build header, search, New control, and bordered tree."""
        super().__init__(parent)
        self.setObjectName("snippetsSidebarPanel")
        self.setMinimumHeight(96)
        self._rows_by_id: dict[int, UserSnippetDict] = {}
        self._info_btn: QToolButton | None = None
        self._info_popup: SidebarSectionInfoPopup | None = None
        self._filter_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(
            LEFT_NAV_PANEL_MARGIN_H_LEFT_PX,
            0,
            LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX,
            _PANEL_ROOT_BOTTOM_MARGIN_PX,
        )
        root.setSpacing(_PANEL_HEADER_LIST_GAP_PX)

        header = QHBoxLayout()
        header.setContentsMargins(0, 6, 0, 0)
        header.setSpacing(4)
        title = QLabel("Snippets")
        title.setObjectName("sidebarSectionLabel")
        header.addWidget(title)

        self._info_btn = make_sidebar_info_button(
            self,
            tooltip="What are snippets?",
            on_toggle=self._toggle_section_info,
        )
        header.addWidget(self._info_btn)
        header.addStretch()

        self._new_btn = QToolButton(self)
        self._new_btn.setText("New")
        self._new_btn.setIcon(phi("plus", size=14))
        self._new_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._new_btn.setObjectName("sidebarToolButton")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.setToolTip("Create a new snippet")
        self._new_btn.clicked.connect(self._on_new_clicked)
        header.addWidget(self._new_btn)
        root.addLayout(header)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search snippets")
        self._search.setObjectName("sidebarSearch")
        self._search.setMinimumHeight(28)
        self._search.addAction(phi("magnifying-glass"), QLineEdit.ActionPosition.LeadingPosition)
        self._search.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("snippetsSidebarScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._list_host = QWidget()
        self._list_host.setObjectName("snippetsSidebarList")
        self._list_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        list_outer = QVBoxLayout(self._list_host)
        list_outer.setContentsMargins(
            _LIST_FRAME_SHIM_PX,
            _LIST_FRAME_SHIM_PX,
            _LIST_FRAME_SHIM_PX,
            _LIST_FRAME_SHIM_PX,
        )
        list_outer.setSpacing(0)

        self._list_body = QWidget(self._list_host)
        self._list_body.setObjectName("snippetsSidebarListBody")
        list_outer.addWidget(self._list_body, 1)

        body_layout = QVBoxLayout(self._list_body)
        body_layout.setContentsMargins(
            _LIST_BODY_PAD_H_PX,
            0,
            _LIST_BODY_PAD_H_PX,
            _LIST_ROWS_BOTTOM_MARGIN_PX,
        )
        body_layout.setSpacing(0)

        self._tree = QTreeWidget(self._list_body)
        self._tree.setObjectName("snippetsTree")
        self._delegate = SnippetsTreeDelegate(self._tree)
        self._tree.setItemDelegate(self._delegate)
        self._tree.setHeaderHidden(True)
        self._tree.hideColumn(1)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setUniformRowHeights(True)
        self._tree.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemExpanded.connect(self._on_folder_expanded)
        self._tree.itemCollapsed.connect(self._on_folder_collapsed)
        self._inline_rename = SnippetsInlineRename(
            self._tree,
            on_mutated=self.refresh_after_mutation,
            parent_widget=self,
        )
        self._context_menus = SnippetsTreeContextMenus(self)
        self._context_menus.attach(self._tree)
        body_layout.addWidget(self._tree, 1)

        self._empty_label = QLabel("No snippets yet.")
        self._empty_label.setObjectName("emptyStateLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        body_layout.addWidget(self._empty_label)

        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, 1)

        self._rebuild()

    def refresh(self) -> None:
        """Reload the snippet tree from the database."""
        self._rebuild()

    def _toggle_section_info(self) -> None:
        """Show or hide the snippets section help popup."""
        if self._info_btn is None:
            return
        holder = [self._info_popup]
        toggle_sidebar_section_info(
            self._info_btn,
            holder,
            title="Snippets",
            body=SNIPPETS_INTRO,
            parent=self,
        )
        self._info_popup = holder[0]

    def _on_search_changed(self, text: str) -> None:
        """Filter visible tree rows by substring."""
        self._filter_text = text.strip().lower()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            if child is not None:
                self._filter_recursive(child, self._filter_text)

    def _filter_recursive(self, item: QTreeWidgetItem, needle: str) -> bool:
        """Hide *item* unless it or a descendant matches *needle*."""
        kind = item.data(0, ROLE_NODE_KIND)
        if kind == KIND_SNIPPET:
            name = (item.text(1) or item.text(0) or "").lower()
            category = str(item.data(0, ROLE_SNIPPET_CATEGORY) or "").lower()
            body = str(item.data(0, ROLE_SNIPPET_BODY) or "").lower()
            haystack = f"{name} {category} {body}"
        else:
            haystack = (item.text(0) or "").lower()

        any_child = False
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None and self._filter_recursive(child, needle):
                any_child = True

        if not needle:
            item.setHidden(False)
            return True

        visible = needle in haystack or any_child
        item.setHidden(not visible)
        if visible and kind in (KIND_LANGUAGE, KIND_CATEGORY):
            item.setExpanded(True)
        return visible

    def _rebuild(self) -> None:
        """Build language → category → snippet tree nodes."""
        self._rows_by_id.clear()
        self._tree.clear()

        any_snippets = False
        icon_sz = _TREE_ICON_PX

        for lang_key, lang_title in _LANG_SPECS:
            rows = SnippetService.list_all(lang_key)
            if not rows:
                continue
            any_snippets = True

            lang_item = QTreeWidgetItem([lang_title, lang_title])
            lang_item.setData(0, ROLE_NODE_KIND, KIND_LANGUAGE)
            lang_item.setData(0, ROLE_LANG_KEY, lang_key)
            lang_item.setData(0, ROLE_SNIPPET_COUNT, len(rows))
            lang_item.setIcon(0, language_icon_pixmap(lang_key, size=icon_sz))
            lang_item.setExpanded(True)

            by_cat: dict[str, list[UserSnippetDict]] = defaultdict(list)
            for row in rows:
                by_cat[str(row.get("category") or "My snippets")].append(row)

            for cat_name in sorted(by_cat.keys(), key=str.lower):
                cat_item = QTreeWidgetItem(lang_item, [cat_name, cat_name])
                cat_item.setData(0, ROLE_NODE_KIND, KIND_CATEGORY)
                cat_item.setData(0, ROLE_SNIPPET_CATEGORY, cat_name)
                cat_item.setIcon(0, phi("folder", size=icon_sz))
                cat_item.setExpanded(True)

                for snip in sorted(by_cat[cat_name], key=lambda r: str(r["name"]).lower()):
                    sid = int(snip["id"])
                    self._rows_by_id[sid] = snip
                    name = str(snip["name"])
                    leaf = QTreeWidgetItem(cat_item, ["", name])
                    leaf.setText(1, name)
                    leaf.setData(0, ROLE_NODE_KIND, KIND_SNIPPET)
                    leaf.setData(0, ROLE_SNIPPET_ID, sid)
                    leaf.setData(0, ROLE_LANG_KEY, lang_key)
                    leaf.setData(0, ROLE_SNIPPET_CATEGORY, str(snip.get("category") or ""))
                    leaf.setData(0, ROLE_SNIPPET_CONTEXT, str(snip.get("context") or "both"))
                    leaf.setData(0, ROLE_SNIPPET_BODY, str(snip.get("body") or ""))
                    leaf.setChildIndicatorPolicy(
                        QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator
                    )

            self._tree.addTopLevelItem(lang_item)

        self._tree.setVisible(any_snippets)
        self._empty_label.setVisible(not any_snippets)
        if self._filter_text:
            self._on_search_changed(self._search.text())

    def _on_folder_expanded(self, item: QTreeWidgetItem) -> None:
        """Open-folder icon while expanded."""
        if item.data(0, ROLE_NODE_KIND) == KIND_CATEGORY:
            item.setIcon(0, phi("folder-open", size=_TREE_ICON_PX))

    def _on_folder_collapsed(self, item: QTreeWidgetItem) -> None:
        """Closed-folder icon when collapsed."""
        if item.data(0, ROLE_NODE_KIND) == KIND_CATEGORY:
            item.setIcon(0, phi("folder", size=_TREE_ICON_PX))

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Open edit on snippet rows; toggle folders on language/category."""
        if self._inline_rename.is_active():
            return
        kind = item.data(0, ROLE_NODE_KIND)
        if kind == KIND_SNIPPET:
            sid = item.data(0, ROLE_SNIPPET_ID)
            if isinstance(sid, int):
                row = self._rows_by_id.get(sid)
                if row is not None:
                    self._open_edit_dialog(row)
            return
        if kind in (KIND_LANGUAGE, KIND_CATEGORY):
            item.setExpanded(not item.isExpanded())

    def _language_for_new_snippet(self) -> str:
        """Default language for sidebar New from tree selection or JavaScript."""
        current = self._tree.currentItem()
        item: QTreeWidgetItem | None = current
        while item is not None:
            if item.data(0, ROLE_NODE_KIND) == KIND_LANGUAGE:
                key = item.data(0, ROLE_LANG_KEY)
                if isinstance(key, str) and key:
                    return key
            item = item.parent()
        return "javascript"

    def _on_new_clicked(self) -> None:
        """Open create dialog for a new sidebar snippet."""
        self.open_create_snippet_dialog(language=self._language_for_new_snippet())

    def open_create_snippet_dialog(self, *, language: str, category: str = "") -> None:
        """Open sidebar create mode with optional *category* preset."""
        dlg = SnippetCaptureDialog(
            from_sidebar=True,
            language=language,
            script_type="pre_request",
            initial_category=category,
            parent=self.window(),
        )
        self._run_dialog(dlg)

    def refresh_after_mutation(self) -> None:
        """Refresh this panel and the snippet picker after a context-menu delete."""
        win = self.window()
        if hasattr(win, "refresh_snippets_sidebar"):
            win.refresh_snippets_sidebar()  # type: ignore[attr-defined]
        else:
            self.refresh()

    def open_edit_snippet_by_id(self, snippet_id: int) -> None:
        """Open edit dialog when *snippet_id* is known (e.g. from context menu)."""
        row = self._rows_by_id.get(snippet_id)
        if row is not None:
            self._open_edit_dialog(row)

    def _open_edit_dialog(self, snip: UserSnippetDict) -> None:
        """Open edit dialog for an existing snippet."""
        dlg = SnippetCaptureDialog(
            snippet_id=int(snip["id"]),
            edit_row=snip,
            parent=self.window(),
        )
        self._run_dialog(dlg)

    def _run_dialog(self, dlg: SnippetCaptureDialog) -> None:
        """Show *dlg* and refresh this panel and the picker on Accepted."""
        from PySide6.QtWidgets import QDialog

        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        win = self.window()
        if hasattr(win, "refresh_snippets_sidebar"):
            win.refresh_snippets_sidebar()  # type: ignore[attr-defined]
        else:
            self.refresh()
