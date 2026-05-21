"""Single advanced script editor pane (toolbar, editor, output)."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from functools import partial
from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.script_version_service import ScriptVersionService
from services.scripting.runtime_settings import RuntimeSettings
from ui.request.request_editor.scripts.inherited_banner import InheritedScriptsBanner
from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel
from ui.request.request_editor.scripts.script_editor_pane.options import ScriptEditorPaneOptions
from ui.request.request_editor.scripts.script_language import (
    code_to_display,
    detect_script_language,
    normalise_script_code,
)
from ui.sidebar.debug_panel import DebugControls
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.runtime_banner import RuntimeBanner
from ui.widgets.search_replace_bar import SearchReplaceBar

_VERSION_CAPTURE_MS = 2000
_AUTO_SAVE_CAPTURE_MS = 500
_BANNER_CHECK_MS = 800
_SPLIT_FULL_WIDTH_LINE_HEIGHT = 1
_SPLIT_FULL_WIDTH_LINE_TOP_MARGIN = 5


class ScriptEditorPane(QWidget):
    """One script editor stack: toolbar, code editor, status bar, and output panel."""

    dirty_changed = Signal(bool)
    save_requested = Signal()
    open_scripting_settings_requested = Signal()
    debug_step_requested = Signal(str)
    content_changed = Signal()

    def __init__(
        self,
        options: ScriptEditorPaneOptions,
        *,
        inherited_banner: InheritedScriptsBanner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Build the pane from *options*."""
        super().__init__(parent)
        self._options = options
        self._script_type = options.script_type
        self._loading = False
        self._lang_auto = True
        self._auto_save_enabled = True
        self._request_id: int | None = None
        self._collection_id: int | None = None
        self._local_script_id: int | None = None
        self._version_script_type = (
            "local_script" if options.host_kind == "local_script" else options.script_type
        )
        self.run_all_callback: Callable[[], None] | None = None
        self.live_response_run_callback: Callable[..., None] | None = None
        self.persist_content_callback: Callable[[], None] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._editor = CodeEditorWidget()
        self._editor.set_language("javascript")
        self._editor.set_snippet_capture_context(script_type=options.script_type)
        self._editor.setPlaceholderText(options.placeholder)
        self._editor.set_breakpoint_gutter_visible(True)
        self._editor.setMinimumHeight(80)
        self._editor.textChanged.connect(self._on_editor_text_changed)

        self._runtime_banner = RuntimeBanner()
        self._runtime_banner.setVisible(False)
        self._runtime_banner.download_completed.connect(self._update_runtime_banner)
        self._runtime_banner.open_settings_clicked.connect(
            self.open_scripting_settings_requested.emit
        )

        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._runtime_banner)

        self._search_bar = SearchReplaceBar(self._editor, editor_pane)
        editor_layout.addWidget(self._search_bar)
        editor_layout.addWidget(self._editor, 1)

        self._build_toolbar(root, inherited_banner=inherited_banner)
        self._build_status_bar(editor_layout)

        self._editor.textChanged.connect(self._schedule_banner_check)
        self._editor.textChanged.connect(self._on_script_text_for_auto_lang)

        self._output_panel = ScriptOutputPanel(
            script_type=options.script_type,
            host_kind=options.host_kind,
        )

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(editor_pane)
        self._splitter.addWidget(self._output_panel)
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 5)
        self._splitter.setObjectName("scriptEditorOutputSplitter")
        root.addWidget(self._splitter, 1)

        self._output_panel.bind_script_editor(self._editor)
        self._editor.document().contentsChanged.connect(
            self._output_panel.clear_inline_log_annotations
        )
        self._output_panel.rerun_test_requested.connect(self._rerun_single_test_from_panel)
        if options.script_type == "test":
            self._output_panel.bind_data_run_callback(self._run_data_iterations)
            self._output_panel.set_data_rerun_callback(self._run_data_iterations)
        self._script_split_full_width_line: QFrame | None = None
        if options.host_kind == "local_script":
            self._init_script_split_full_width_line()
            self._splitter.splitterMoved.connect(
                self._schedule_refresh_script_split_full_width_line
            )
        self._schedule_splitter_sizes()

        if options.enable_test_gutter:
            self._editor.set_test_gutter_enabled(True)
            self._editor.textChanged.connect(self._refresh_pm_test_gutter_markers)
            self._editor.run_single_test_requested.connect(self._run_single_test)
            self._editor.debug_single_test_requested.connect(
                lambda n: self._run_single_test(n, debug=True)
            )
            self._refresh_pm_test_gutter_markers()

        self._lang_auto_timer = QTimer(self._editor)
        self._lang_auto_timer.setSingleShot(True)
        self._lang_auto_timer.setInterval(400)
        self._lang_auto_timer.timeout.connect(self._apply_auto_script_language)

        if not options.use_host_version_timer:
            self._version_capture_timer = QTimer(self)
            self._version_capture_timer.setSingleShot(True)
            self._version_capture_timer.setInterval(_AUTO_SAVE_CAPTURE_MS)
            self._version_capture_timer.timeout.connect(self.capture_version)

        self._banner_check_timer = QTimer(self)
        self._banner_check_timer.setSingleShot(True)
        self._banner_check_timer.setInterval(_BANNER_CHECK_MS)
        self._banner_check_timer.timeout.connect(self._update_runtime_banner)

        self._refresh_snippets_button()

    @property
    def editor(self) -> CodeEditorWidget:
        """The code editor widget."""
        return self._editor

    @property
    def output_panel(self) -> ScriptOutputPanel:
        """The inline run output panel."""
        return self._output_panel

    @property
    def search_bar(self) -> SearchReplaceBar:
        """Find/replace bar for this pane."""
        return self._search_bar

    @property
    def splitter(self) -> QSplitter:
        """Editor/output splitter."""
        return self._splitter

    @property
    def runtime_banner(self) -> RuntimeBanner:
        """Deno install prompt banner."""
        return self._runtime_banner

    @property
    def debug_controls(self) -> DebugControls:
        """Step controls shown during inline debug."""
        return self._debug_controls

    def set_loading(self, loading: bool) -> None:
        """Suppress dirty/content signals while loading persisted data."""
        self._loading = loading

    def set_version_owner(
        self,
        *,
        request_id: int | None = None,
        collection_id: int | None = None,
        local_script_id: int | None = None,
    ) -> None:
        """Set which entity version snapshots belong to."""
        self._request_id = request_id
        self._collection_id = collection_id
        self._local_script_id = local_script_id
        self._editor.set_snippet_capture_context(
            script_type=self._script_type,
            collection_id=collection_id,
            local_script_id=local_script_id,
        )

    def load_content(
        self,
        text: str,
        language: str,
        *,
        module_format: str = "esm",
    ) -> None:
        """Replace buffer content and reset dirty state."""
        self._loading = True
        try:
            self._editor.set_language(normalise_script_code(language))
            if self._options.host_kind == "local_script":
                self._editor.set_script_module_format(module_format)
            self._editor.setPlainText(text)
            self._editor.document().setModified(False)
            self._sync_lang_menu_button_text()
            if self._options.enable_test_gutter:
                self._refresh_pm_test_gutter_markers()
        finally:
            self._loading = False
        self.dirty_changed.emit(False)

    def get_content(self) -> tuple[str, str]:
        """Return ``(text, language_code)``."""
        return self._editor.toPlainText(), self._editor.language

    def is_dirty(self) -> bool:
        """Return whether the document is modified."""
        return self._editor.document().isModified()

    def schedule_version_capture(self) -> None:
        """Restart debounced version capture (host or internal timer)."""
        if self._loading:
            return
        if self._options.use_host_version_timer:
            return
        self._version_capture_timer.start()

    def capture_version(self) -> None:
        """Persist a version snapshot when content changed."""
        owner_set = (
            self._request_id is not None
            or self._collection_id is not None
            or self._local_script_id is not None
        )
        if not owner_set:
            return
        content = self._editor.toPlainText()
        if not content.strip():
            return
        ScriptVersionService.capture(
            request_id=self._request_id,
            collection_id=self._collection_id,
            local_script_id=self._local_script_id,
            script_type=self._version_script_type,
            content=content,
            language=self._editor.language,
        )
        if self._auto_save_enabled and self.persist_content_callback is not None:
            self.persist_content_callback()

    def capture_version_now(self) -> None:
        """Force immediate version capture."""
        if not self._options.use_host_version_timer:
            self._version_capture_timer.stop()
        self.capture_version()

    def set_auto_save_enabled(self, enabled: bool) -> None:
        """Sync auto-save checkbox and timer interval."""
        self._auto_save_enabled = enabled
        if hasattr(self, "_auto_save_cb"):
            self._auto_save_cb.blockSignals(True)
            self._auto_save_cb.setChecked(enabled)
            self._auto_save_cb.blockSignals(False)
        if not self._options.use_host_version_timer:
            interval = _AUTO_SAVE_CAPTURE_MS if enabled else _VERSION_CAPTURE_MS
            self._version_capture_timer.setInterval(interval)
        self._sync_save_button_for_auto_save()

    def sync_auto_save_from_host(self, enabled: bool) -> None:
        """Update auto-save state when the host owns the global toggle."""
        self._auto_save_enabled = enabled
        if hasattr(self, "_auto_save_cb"):
            self._auto_save_cb.blockSignals(True)
            self._auto_save_cb.setChecked(enabled)
            self._auto_save_cb.blockSignals(False)
        self._sync_save_button_for_auto_save()

    def _rerun_single_test_from_panel(self, test_name: str) -> None:
        """Rerun one ``pm.test`` via the output panel Rerun button."""
        self.run(test_name_filter=test_name)

    def _run_data_iterations(
        self,
        iteration_data: list[dict[str, Any]],
        iteration_count: int,
    ) -> None:
        """Run the current script once per data row (inline data-driven runner)."""
        from ui.request.request_editor.scripts.script_run_worker import build_inline_context

        self.ensure_output_pane_open()
        script = self._editor.toPlainText().strip()
        if not script:
            return
        language = self._editor.language
        response_data = (
            self._output_panel.get_response_data() if self._script_type == "test" else None
        )
        context = build_inline_context(
            script_type=self._script_type,
            response_data=response_data,
        )
        self._output_panel.run_script_iterations(
            script=script,
            language=language,
            context=context,
            iteration_data=iteration_data,
            iteration_count=iteration_count,
            run_btn=self._run_btn,
            debug_btn=self._debug_btn,
        )

    def run(
        self,
        *,
        script_text: str | None = None,
        test_name_filter: str | None = None,
    ) -> None:
        """Run the current script inline."""
        from ui.request.request_editor.scripts.script_run_worker import build_inline_context

        self.ensure_output_pane_open()
        script = (script_text if script_text is not None else self._editor.toPlainText()).strip()
        if not script:
            return
        language = self._editor.language
        if (
            self._script_type == "test"
            and hasattr(self._output_panel, "response_source_mode")
            and self.live_response_run_callback is not None
        ):
            mode = self._output_panel.response_source_mode()
            if mode == "live":
                self.live_response_run_callback(
                    panel=self._output_panel,
                    script=script,
                    language=language,
                    run_btn=self._run_btn,
                    debug_btn=self._debug_btn,
                )
                return
        response_data = (
            self._output_panel.get_response_data() if self._script_type == "test" else None
        )
        context = build_inline_context(
            script_type=self._script_type,
            response_data=response_data,
            test_name_filter=test_name_filter,
        )
        self._output_panel.run_script(
            script=script,
            language=language,
            context=context,
            run_btn=self._run_btn,
            debug_btn=self._debug_btn,
            test_name_filter=test_name_filter,
        )

    def _script_host_for_debug(self) -> QWidget | None:
        """Walk parents to the widget that owns this pane for debug pause UI."""
        from ui.local_scripts.local_script_editor_widget import LocalScriptEditorWidget

        w: QWidget | None = self
        while w is not None:
            if isinstance(w, LocalScriptEditorWidget):
                return w
            if hasattr(w, "_ensure_scripts_editors"):
                return w
            w = w.parentWidget()
        return None

    def debug(self, *, script_text: str | None = None) -> None:
        """Start inline debug for the current script."""
        from services.scripting.debug import DebugProtocol
        from ui.request.request_editor.scripts.script_run_worker import build_inline_context

        self.ensure_output_pane_open()
        script = script_text if script_text is not None else self._editor.toPlainText()
        if not script.strip():
            return
        language = self._editor.language
        response_data = (
            self._output_panel.get_response_data() if self._script_type == "test" else None
        )
        context = build_inline_context(script_type=self._script_type, response_data=response_data)
        protocol = DebugProtocol()
        protocol.set_breakpoints(dict(self._editor.breakpoints))
        main: Any = self.window()
        if hasattr(main, "_debug_protocol"):
            old = main._debug_protocol
            if old is not None:
                with contextlib.suppress(Exception):
                    old.stop()
            main._debug_protocol = protocol
        if hasattr(main, "_clear_debug_breakpoint_listeners"):
            main._clear_debug_breakpoint_listeners()
        self.hide_debug_toolbar()

        def _push_inline() -> None:
            p = getattr(main, "_debug_protocol", None)
            if p is not None and p is protocol:
                p.update_breakpoints(dict(self._editor.breakpoints))

        main._debug_breakpoint_connections = []
        self._editor.breakpoints_changed.connect(_push_inline)
        main._debug_breakpoint_connections.append((self._editor, _push_inline))
        debug_host = self._script_host_for_debug()
        if debug_host is not None:
            main._debug_script_host = debug_host
        self._output_panel.run_script_debug(
            script=script,
            language=language,
            context=context,
            protocol=protocol,
            script_type=self._script_type,
            run_btn=self._run_btn,
            debug_btn=self._debug_btn,
        )

    def open_version_history(self) -> None:
        """Open version history for this pane's owner."""
        if not self._options.show_version_history:
            return
        from ui.request.request_editor.scripts.version_history import VersionHistoryDialog

        if self._local_script_id is not None:
            dlg = VersionHistoryDialog(
                local_script_id=self._local_script_id,
                current_content=self._editor.toPlainText(),
                language=self._editor.language,
                parent=self._editor,
            )
        else:
            if self._request_id is None and self._collection_id is None:
                return
            dlg = VersionHistoryDialog(
                request_id=self._request_id,
                collection_id=self._collection_id,
                current_pre=self._editor.toPlainText()
                if self._script_type == "pre_request"
                else "",
                current_test=self._editor.toPlainText() if self._script_type == "test" else "",
                language=self._editor.language,
                initial_tab=0 if self._script_type == "pre_request" else 1,
                parent=self._editor,
            )
        if dlg.exec():
            restored = dlg.restored_content()
            if restored:
                _stype, content = restored
                self._editor.selectAll()
                self._editor.insertPlainText(content)
                self.content_changed.emit()
                self.dirty_changed.emit(self.is_dirty())

    def ensure_output_pane_open(self) -> None:
        """Expand the output splitter if collapsed."""
        sizes = self._splitter.sizes()
        if len(sizes) == 2 and sizes[1] <= 4:
            self._schedule_splitter_sizes()

    def _schedule_splitter_sizes(self) -> None:
        """Set initial editor/output heights after layout."""
        if self._splitter.count() != 2:
            return

        def try_apply(attempt: int = 0) -> None:
            h = self._splitter.height()
            if h < 30 and attempt < 30:
                QTimer.singleShot(40, partial(try_apply, attempt + 1))
                return
            if h < 50:
                return
            handles = (self._splitter.count() - 1) * self._splitter.handleWidth()
            avail = h - handles
            if avail < 100:
                return
            out_h = max(200, int(avail * 0.56))
            ed_h = max(120, avail - out_h)
            self._splitter.setSizes([ed_h, out_h])
            self._schedule_refresh_script_split_full_width_line()

        QTimer.singleShot(0, partial(try_apply, 0))

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep the editor/output divider line aligned on resize."""
        super().resizeEvent(event)
        self._schedule_refresh_script_split_full_width_line()

    def _script_split_full_width_line_host(self) -> QWidget:
        """Widget that owns the overlay (full tab width for local scripts)."""
        if self._options.host_kind == "local_script":
            from ui.local_scripts.local_script_editor_widget import LocalScriptEditorWidget

            w: QWidget | None = self
            while w is not None:
                if isinstance(w, LocalScriptEditorWidget):
                    return w
                w = w.parentWidget()
        return self

    def _init_script_split_full_width_line(self) -> None:
        """Create a full-width divider overlay on the editor/output seam."""
        host = self._script_split_full_width_line_host()
        line = QFrame(host)
        line.setObjectName("scriptSplitFullWidthLine")
        line.setFixedHeight(_SPLIT_FULL_WIDTH_LINE_HEIGHT)
        line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        line.hide()
        self._script_split_full_width_line = line

    def _schedule_refresh_script_split_full_width_line(self) -> None:
        """Reposition the overlay after layout (debug bar, output inspector, sub-tabs)."""
        if self._script_split_full_width_line is None:
            return
        QTimer.singleShot(0, self._refresh_script_split_full_width_line)
        QTimer.singleShot(50, self._refresh_script_split_full_width_line)
        QTimer.singleShot(120, self._refresh_script_split_full_width_line)

    def _refresh_script_split_full_width_line(self, *_args: object) -> None:
        """Show or hide the overlay and align it to the editor/output seam."""
        line = self._script_split_full_width_line
        if line is None or not self.isVisible():
            return
        if self._splitter.count() < 2:
            line.hide()
            return
        if not self._splitter.isVisible():
            line.hide()
            return
        top_pane = self._splitter.widget(0)
        if top_pane is None or not top_pane.isVisible():
            line.hide()
            return
        host = self._script_split_full_width_line_host()
        host_w = host.width()
        if host_w < 2:
            line.hide()
            return
        seam = top_pane.mapTo(host, QPoint(top_pane.width() // 2, top_pane.height()))
        lh = line.height()
        y = seam.y() + _SPLIT_FULL_WIDTH_LINE_TOP_MARGIN
        split_top = self._splitter.mapTo(host, QPoint(0, 0)).y()
        if y < split_top + 24:
            line.hide()
            return
        line.setGeometry(0, y, host_w, lh)
        line.show()
        line.raise_()

    def hide_debug_toolbar(self) -> None:
        """Hide the debug step row (shown only while a debug session is paused)."""
        self._debug_controls.set_idle()
        self._debug_controls.hide()
        self._debug_bar.hide()
        self._schedule_refresh_script_split_full_width_line()

    def _build_toolbar(
        self,
        parent_layout: QVBoxLayout,
        *,
        inherited_banner: InheritedScriptsBanner | None,
    ) -> None:
        """Build editor toolbar row and debug step bar."""
        chrome = QWidget()
        chrome.setObjectName("scriptEditorToolbarChrome")
        chrome_layout = QVBoxLayout(chrome)
        chrome_layout.setContentsMargins(0, 6, 0, 8)
        chrome_layout.setSpacing(0)

        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_row.setSpacing(4)

        def _make_icon_btn(icon: str, tip: str, slot: Any, *, enabled: bool = True) -> QPushButton:
            b = QPushButton()
            b.setIcon(phi(icon))
            b.setFixedSize(28, 28)
            b.setObjectName("iconButton")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setEnabled(enabled)
            b.clicked.connect(slot)
            return b

        def _add_separator() -> None:
            sep = QFrame()
            sep.setObjectName("scriptToolbarSeparator")
            sep.setFrameShape(QFrame.Shape.NoFrame)
            sep.setFixedWidth(1)
            sep.setFixedHeight(20)
            lang_row.addSpacing(8)
            lang_row.addWidget(sep)
            lang_row.addSpacing(8)

        find_hint = QKeySequence(QKeySequence.StandardKey.Find).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        replace_hint = QKeySequence(QKeySequence.StandardKey.Replace).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        for icon, tip, slot in (
            ("magnifying-glass", f"Find ({find_hint})", self._search_bar.toggle_search),
            ("swap", f"Find & Replace ({replace_hint})", self._search_bar.toggle_replace),
            ("list-numbers", "Go to Line (Ctrl+G)", self._search_bar.goto_line),
        ):
            lang_row.addWidget(_make_icon_btn(icon, tip, slot))

        _add_separator()

        undo_hint = QKeySequence(QKeySequence.StandardKey.Undo).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        redo_hint = QKeySequence(QKeySequence.StandardKey.Redo).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        redo_btn = _make_icon_btn(
            "arrow-clockwise", f"Redo ({redo_hint})", self._editor.redo, enabled=False
        )
        self._editor.redoAvailable.connect(redo_btn.setEnabled)
        lang_row.addWidget(redo_btn)
        undo_btn = _make_icon_btn(
            "arrow-counter-clockwise", f"Undo ({undo_hint})", self._editor.undo, enabled=False
        )
        self._editor.undoAvailable.connect(undo_btn.setEnabled)
        lang_row.addWidget(undo_btn)

        _add_separator()

        self._run_btn = _make_icon_btn(
            "play",
            "Run current script (Ctrl+Enter)",
            lambda: self.run(),
        )
        lang_row.addWidget(self._run_btn)

        self._run_all_btn = _make_icon_btn(
            "stack-simple",
            "Run all (inherited + current)",
            lambda: self.run_all_callback() if self.run_all_callback else None,
        )
        if not self._options.show_run_all:
            self._run_all_btn.hide()
        lang_row.addWidget(self._run_all_btn)

        self._debug_btn = _make_icon_btn(
            "bug",
            "Debug script (breakpoints)",
            lambda: self.debug(),
        )
        lang_row.addWidget(self._debug_btn)

        _add_separator()

        self._save_btn = _make_icon_btn(
            "floppy-disk",
            "Save script (Ctrl+S)",
            self.save_requested.emit,
        )
        lang_row.addWidget(self._save_btn)

        if self._options.show_auto_save:
            self._auto_save_cb = QCheckBox("Auto-save")
            self._auto_save_cb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._auto_save_cb.setToolTip("Capture script versions continuously")
            self._auto_save_cb.setChecked(self._auto_save_enabled)
            self._auto_save_cb.toggled.connect(self._on_auto_save_toggled)
            lang_row.addWidget(self._auto_save_cb)
            self._sync_save_button_for_auto_save()

        lang_row.addStretch()
        if inherited_banner is not None:
            lang_row.addWidget(inherited_banner)

        chrome_layout.addLayout(lang_row)

        debug_bar = QWidget()
        debug_bar.setObjectName("scriptDebugBar")
        db_layout = QVBoxLayout(debug_bar)
        db_layout.setContentsMargins(0, 8, 0, 4)
        db_layout.setSpacing(8)
        row_sep = QFrame()
        row_sep.setObjectName("scriptDebugToolbarSep")
        row_sep.setFrameShape(QFrame.Shape.NoFrame)
        row_sep.setFixedHeight(1)
        row_sep.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        db_layout.addWidget(row_sep)
        self._debug_controls = DebugControls()
        self._debug_controls.hide()
        self._debug_controls.step_requested.connect(self.debug_step_requested.emit)
        db_layout.addWidget(self._debug_controls)
        chrome_layout.addWidget(debug_bar)
        debug_bar.hide()
        self._debug_bar = debug_bar

        parent_layout.addWidget(chrome)

    def _build_status_bar(self, parent_layout: QVBoxLayout) -> None:
        """Build Ln/Col, language picker, history, snippets, char count."""
        row = QWidget()
        row.setObjectName("scriptEditorStatusBar")
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)

        self._status_ln_lbl = QLabel()
        self._status_ln_lbl.setObjectName("mutedLabel")
        sep1 = QLabel("\u2502")
        sep1.setObjectName("mutedLabel")
        self._lang_menu_btn = self._create_script_lang_toolbutton()
        sep_hist = QLabel("\u2502")
        sep_hist.setObjectName("mutedLabel")
        self._history_btn = QToolButton()
        self._history_btn.setObjectName("scriptHistoryLinkButton")
        self._history_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._history_btn.setText("History")
        self._history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if not self._options.show_version_history:
            self._history_btn.hide()
            sep_hist.hide()
        sep_snip = QLabel("\u2502")
        sep_snip.setObjectName("mutedLabel")
        self._snippets_btn = QToolButton()
        self._snippets_btn.setObjectName("scriptHistoryLinkButton")
        self._snippets_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._snippets_btn.setText("Snippets")
        self._snippets_btn.clicked.connect(self._open_snippets)
        self._status_chars_lbl = QLabel()
        self._status_chars_lbl.setObjectName("mutedLabel")
        sep2 = QLabel("\u2502")
        sep2.setObjectName("mutedLabel")

        h.addWidget(self._status_ln_lbl)
        h.addWidget(sep1)
        h.addWidget(self._lang_menu_btn)
        h.addWidget(sep_hist)
        h.addWidget(self._history_btn)
        h.addWidget(sep_snip)
        h.addWidget(self._snippets_btn)
        h.addWidget(sep2)
        h.addWidget(self._status_chars_lbl)
        h.addStretch()
        parent_layout.addWidget(row)

        def _update(_line: int = 0, _col: int = 0) -> None:
            cur = self._editor.textCursor()
            ln = cur.blockNumber() + 1
            col = cur.positionInBlock() + 1
            self._status_ln_lbl.setText(f"Ln {ln}, Col {col}")
            self._status_chars_lbl.setText(f"{len(self._editor.toPlainText())} chars")
            self._sync_lang_menu_button_text()

        self._editor.cursor_position_changed.connect(_update)
        self._editor.textChanged.connect(_update)
        _update()

    def _create_script_lang_toolbutton(self) -> QToolButton:
        """Build language picker on the status bar."""
        btn = QToolButton()
        btn.setObjectName("scriptLanguageLinkButton")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        menu = QMenu(btn)
        act_js = QAction("JavaScript", menu)
        act_js.setCheckable(True)
        act_ts = QAction("TypeScript", menu)
        act_ts.setCheckable(True)
        act_py = QAction("Python", menu)
        act_py.setCheckable(True)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for act in (act_js, act_ts, act_py):
            group.addAction(act)
            menu.addAction(act)
        menu.addSeparator()
        act_auto = QAction("Auto", menu)
        menu.addAction(act_auto)

        def sync_checks() -> None:
            lang = self._editor.language
            act_js.setChecked(lang == "javascript")
            act_ts.setChecked(lang == "typescript")
            act_py.setChecked(lang == "python")

        menu.aboutToShow.connect(sync_checks)

        def pick_lang(code: str) -> None:
            self._lang_auto = False
            self._editor.set_language(code)
            self._sync_lang_menu_button_text()
            if self._options.enable_test_gutter:
                self._refresh_pm_test_gutter_markers()
            self._schedule_banner_check()
            if not self._loading:
                self.content_changed.emit()
            self._refresh_snippets_button()

        act_js.triggered.connect(lambda: pick_lang("javascript"))
        act_ts.triggered.connect(lambda: pick_lang("typescript"))
        act_py.triggered.connect(lambda: pick_lang("python"))
        act_auto.triggered.connect(self._apply_auto_script_language)
        btn.setMenu(menu)
        return btn

    def _sync_lang_menu_button_text(self) -> None:
        """Refresh language button label."""
        self._lang_menu_btn.setText(code_to_display(self._editor.language))

    def _on_editor_text_changed(self) -> None:
        if self._loading:
            return
        self.content_changed.emit()
        self.dirty_changed.emit(self.is_dirty())
        if not self._options.use_host_version_timer:
            self.schedule_version_capture()

    def _on_script_text_for_auto_lang(self) -> None:
        if self._loading or not self._lang_auto:
            return
        self._lang_auto_timer.start()

    def _apply_auto_script_language(self) -> None:
        if not self._lang_auto:
            return
        text = self._editor.toPlainText()
        want = detect_script_language(text, default=self._editor.language)
        if want != self._editor.language:
            self._editor.set_language(want)
        self._sync_lang_menu_button_text()
        if self._options.enable_test_gutter:
            self._refresh_pm_test_gutter_markers()
        self._schedule_banner_check()
        if not self._loading:
            self.content_changed.emit()
        self._refresh_snippets_button()

    def _on_auto_save_toggled(self, checked: bool) -> None:
        self._auto_save_enabled = checked
        self._sync_save_button_for_auto_save()
        if not self._options.use_host_version_timer:
            interval = _AUTO_SAVE_CAPTURE_MS if checked else _VERSION_CAPTURE_MS
            self._version_capture_timer.setInterval(interval)
            if checked:
                self.capture_version_now()

    def _sync_save_button_for_auto_save(self) -> None:
        if not hasattr(self, "_save_btn"):
            return
        if self._auto_save_enabled and self._options.show_auto_save:
            tip = "Save disabled — Auto-save is on (versions captured automatically)"
            self._save_btn.setEnabled(False)
        else:
            tip = "Save script (Ctrl+S)"
            self._save_btn.setEnabled(True)
        self._save_btn.setToolTip(tip)

    def _schedule_banner_check(self) -> None:
        if self._loading:
            return
        self._banner_check_timer.start()

    def _update_runtime_banner(self) -> None:
        lang = self._editor.language
        if lang != "javascript":
            self._runtime_banner.setVisible(False)
            return
        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        self._runtime_banner.setVisible(not st["available"])

    def _refresh_snippets_button(self) -> None:
        from ui.widgets.snippets.loader import has_snippets

        enabled = has_snippets(self._editor.language)
        self._snippets_btn.setEnabled(enabled)
        self._snippets_btn.setToolTip(
            "Insert a code snippet" if enabled else f"No snippets for {self._editor.language}"
        )
        self._snippets_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    def _open_snippets(self) -> None:
        from ui.widgets.snippets.loader import has_snippets
        from ui.widgets.snippets.popup import SnippetsPopup

        language = self._editor.language
        if not has_snippets(language):
            return

        def _insert(body: str) -> None:
            cur = self._editor.textCursor()
            cur.insertText(body)
            self._editor.setFocus()

        SnippetsPopup.instance().show_for(
            self._snippets_btn,
            language,
            self._script_type,
            _insert,
            collection_id=self._collection_id,
            local_script_id=self._local_script_id,
        )

    def _refresh_pm_test_gutter_markers(self) -> None:
        from services.scripting.engine import find_pm_tests, find_top_level_statement_lines

        lang = self._editor.language
        self._editor.set_pm_tests(find_pm_tests(self._editor.toPlainText(), lang))
        self._editor.set_top_level_lines(
            find_top_level_statement_lines(self._editor.toPlainText(), lang)
        )

    def _run_single_test(self, name: str, *, debug: bool = False) -> None:
        user_src = self._editor.toPlainText()
        lang = self._editor.language
        if lang == "python":
            wrapper = (
                f"__target = {name!r}\n"
                "import pm\n"
                "_orig = pm.test\n"
                "def _scoped(n, fn=None):\n"
                "    if n == __target:\n"
                "        return _orig(n, fn)\n"
                "    return _orig(n, fn)\n"
                "pm.test = _scoped\n"
            )
        else:
            wrapper = (
                f"__target = {name!r}\n"
                "__orig_test = pm.test\n"
                "def __scoped_test(n, fn=None):\n"
                "    if n == __target:\n"
                "        return __orig_test(n, fn)\n"
                "pm.test = __scoped_test\n"
            )
        full_script = wrapper + user_src
        if debug:
            self.debug(script_text=full_script)
        else:
            self.run(script_text=full_script)
