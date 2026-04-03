"""Version history dialog with timeline, search, and side-by-side diff."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.script_version_service import ScriptVersionService
from ui.styling.icons import phi

from .delegate import _VersionItemDelegate
from .diff_viewer import _DiffViewer
from .toolbar import _DiffToolbar

# Custom data role for version ID.
_ROLE_VERSION_ID = Qt.ItemDataRole.UserRole + 1

# Fraction of the primary screen dimensions used for the dialog.
_SCREEN_FRACTION = 0.8

# Height (in pixels) for version list items.
_LIST_ITEM_HEIGHT = 38


class VersionHistoryDialog(QDialog):
    """Dialog showing script version timeline and side-by-side diff."""

    def __init__(
        self,
        *,
        request_id: int | None,
        collection_id: int | None,
        current_pre: str,
        current_test: str,
        language: str = "javascript",
        initial_tab: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        """Build the version history dialog."""
        super().__init__(parent)
        self.setWindowTitle("Script Version History")

        # Size to 80 % of the primary screen.
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            w = int(geo.width() * _SCREEN_FRACTION)
            h = int(geo.height() * _SCREEN_FRACTION)
        else:
            w, h = 1200, 800
        self.resize(w, h)

        self._request_id = request_id
        self._collection_id = collection_id
        self._current_pre = current_pre
        self._current_test = current_test
        self._language = language
        self._restored: tuple[str, str] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(0)

        # Bottom button row (created early so _on_tab_changed can access)
        self._restore_btn = QPushButton("Restore Selected")
        self._restore_btn.setIcon(phi("arrow-counter-clockwise", color="#ffffff", size=14))
        self._restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restore_btn.setEnabled(False)
        self._restore_btn.clicked.connect(self._on_restore)

        # Script type tabs
        self._type_tabs = QTabWidget()
        self._type_tabs.setObjectName("versionTabs")
        self._type_tabs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._type_tabs.currentChanged.connect(self._on_tab_changed)

        # Pre-request tab
        pre_widget = QWidget()
        pre_layout = QVBoxLayout(pre_widget)
        pre_layout.setContentsMargins(0, 0, 0, 0)
        pre_layout.setSpacing(0)
        self._pre_toolbar, self._pre_list, self._pre_viewer = self._build_tab(
            pre_layout,
        )
        self._type_tabs.addTab(pre_widget, "Pre-request Script")

        # Test tab
        test_widget = QWidget()
        test_layout = QVBoxLayout(test_widget)
        test_layout.setContentsMargins(0, 0, 0, 0)
        test_layout.setSpacing(0)
        self._test_toolbar, self._test_list, self._test_viewer = self._build_tab(
            test_layout,
        )
        self._type_tabs.addTab(test_widget, "Test Script")

        root.addWidget(self._type_tabs, 1)

        # Bottom button row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 8, 8, 4)
        btn_row.addStretch()
        self._restore_btn.setObjectName("primaryButton")
        btn_row.addWidget(self._restore_btn)
        btn_row.addSpacing(8)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        # Load versions
        self._load_versions()

        # Select the requested initial tab
        if initial_tab:
            self._type_tabs.setCurrentIndex(initial_tab)

    # -- Layout helpers ------------------------------------------------

    def _build_tab(
        self,
        layout: QVBoxLayout,
    ) -> tuple[_DiffToolbar, QListWidget, _DiffViewer]:
        """Build a toolbar + version-list + diff-viewer triple."""
        # Full-width toolbar (search + nav + ws + copy + counter)
        toolbar = _DiffToolbar()
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Version list (search is in toolbar)
        version_list = QListWidget()
        version_list.setObjectName("versionList")
        version_list.setMinimumWidth(180)
        version_list.setMaximumWidth(240)
        version_list.setItemDelegate(_VersionItemDelegate(version_list))
        version_list.currentItemChanged.connect(self._on_version_selected)
        splitter.addWidget(version_list)

        # Sync search field width with the version-list panel.
        search = toolbar.search_widget
        splitter.splitterMoved.connect(
            lambda _pos, _idx: search.setFixedWidth(splitter.sizes()[0]),
        )

        # Wire search from toolbar to version list
        toolbar.search_changed.connect(
            lambda text: self._filter_list(version_list, text),
        )

        # Diff viewer (toolbar is above, not inside viewer)
        viewer = _DiffViewer(language=self._language)
        splitter.addWidget(viewer)

        # Wire toolbar <-> viewer
        toolbar.navigate_prev.connect(viewer.navigate_prev)
        toolbar.navigate_next.connect(viewer.navigate_next)
        toolbar.copy_requested.connect(viewer.copy_content)
        toolbar.whitespace_changed.connect(viewer.set_whitespace_mode)
        viewer.diff_count_changed.connect(toolbar.set_diff_count)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        initial_list_width = 220
        splitter.setSizes([initial_list_width, 900])
        splitter.setHandleWidth(1)
        search.setFixedWidth(initial_list_width)
        layout.addWidget(splitter, 1)
        return toolbar, version_list, viewer

    # -- Data loading --------------------------------------------------

    def _load_versions(self) -> None:
        """Fetch and display versions for both script types."""
        self._load_type_versions(self._pre_list, "pre_request", self._current_pre)
        self._load_type_versions(self._test_list, "test", self._current_test)

    def _load_type_versions(
        self,
        list_widget: QListWidget,
        script_type: str,
        current_content: str,
    ) -> None:
        """Populate *list_widget* with versions for *script_type*."""
        list_widget.clear()

        versions = ScriptVersionService.list_versions(
            request_id=self._request_id,
            collection_id=self._collection_id,
            script_type=script_type,
        )
        for v in versions:
            ts = v["created_at"]
            date_str = ts.strftime("%d/%m/%Y, %H:%M")
            item = QListWidgetItem(f"Change\n{date_str}")
            item.setData(_ROLE_VERSION_ID, v["id"])
            item.setData(Qt.ItemDataRole.UserRole, v["content"])
            item.setSizeHint(QSize(0, _LIST_ITEM_HEIGHT))
            list_widget.addItem(item)

        # Auto-select the first version if available.
        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)

    # -- Search / filter -----------------------------------------------

    @staticmethod
    def _filter_list(list_widget: QListWidget, text: str) -> None:
        """Show only list items whose content matches *text*."""
        needle = text.lower()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item is None:
                continue
            if not needle:
                item.setHidden(False)
                continue
            content = (item.data(Qt.ItemDataRole.UserRole) or "").lower()
            display = (item.text() or "").lower()
            item.setHidden(needle not in content and needle not in display)

    # -- Selection handling --------------------------------------------

    def _on_version_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """Show diff when a version is selected."""
        if current is None:
            return

        content = current.data(Qt.ItemDataRole.UserRole) or ""

        tab_idx = self._type_tabs.currentIndex()
        if tab_idx == 0:
            current_text = self._current_pre
            viewer = self._pre_viewer
        else:
            current_text = self._current_test
            viewer = self._test_viewer

        viewer.show_diff(content, current_text)
        # Dynamic "Before [date]" label on the left column header
        parts = (current.text() or "").split("\n")
        date_part = parts[1] if len(parts) > 1 else parts[0]
        viewer.set_version_info(f"Before {date_part}")

        self._restore_btn.setEnabled(True)

    def _on_tab_changed(self, _index: int) -> None:
        """Reset restore button when switching tabs."""
        self._restore_btn.setEnabled(False)

    # -- Restore -------------------------------------------------------

    def _on_restore(self) -> None:
        """Accept the dialog with the selected version's content."""
        tab_idx = self._type_tabs.currentIndex()
        list_widget = self._pre_list if tab_idx == 0 else self._test_list
        item = list_widget.currentItem()
        if item is None:
            return

        content = item.data(Qt.ItemDataRole.UserRole) or ""
        script_type = "pre_request" if tab_idx == 0 else "test"
        self._restored = (script_type, content)
        self.accept()

    def restored_content(self) -> tuple[str, str] | None:
        """Return ``(script_type, content)`` if the user chose Restore."""
        return self._restored
