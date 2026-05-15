"""Scripts tab mixin — dual pre-request / test script editors."""

from __future__ import annotations

import contextlib
import json
from functools import partial
from typing import Any, Literal, cast

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QSplitter, QToolButton,
                               QVBoxLayout, QWidget)

from database.models.collections.collection_query_repository import \
    get_script_chain
from services.script_service import normalize_disabled_inherited
from services.script_version_service import ScriptVersionService
from services.scripting.context import normalize_events as _normalize_events
from services.scripting.runtime_settings import RuntimeSettings
from ui.request.request_editor.scripts.inherited_banner import \
    InheritedScriptsBanner
from ui.request.request_editor.scripts.script_language import (
    code_to_display, detect_script_language, normalise_script_code)
from ui.sidebar.debug_panel import DebugControls
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.runtime_banner import RuntimeBanner
from ui.widgets.search_replace_bar import SearchReplaceBar

_VERSION_CAPTURE_MS = 2000  # Debounce delay (ms) for version capture.
_AUTO_SAVE_CAPTURE_MS = 500  # Aggressive capture interval when auto-save enabled.
_BANNER_CHECK_MS = 800  # Debounce delay (ms) for runtime banner re-check.

# QSettings keys.
_SETTINGS_KEY_AUTO_SAVE_OVERRIDES = "scripts/auto_save_overrides"
_SETTINGS_KEY_AUTO_SAVE_DEFAULT = "scripting/auto_save_default"

# Full-width divider overlay (see ``_refresh_script_split_full_width_line``).
_SCRIPT_SPLIT_FULL_WIDTH_LINE_HEIGHT = 1
_SCRIPT_SPLIT_FULL_WIDTH_LINE_TOP_MARGIN = 5


class _ScriptsMixin:
    """Mixin building and managing pre-request / test script editors."""

    # Host flag: request editors want the inherited-scripts banner; folder
    # editors do not (folders *are* the inherited chain for their descendants).
    _inherited_banners_supported: bool = True
    # "request" | "folder" — folder script panels omit live-response controls.
    _script_output_host_kind: str = "request"

    # -- Individual tab builders ---------------------------------------

    def _build_pre_request_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Pre-request Script tab contents."""
        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.set_breakpoint_gutter_visible(True)
        self._pre_request_edit.setMinimumHeight(80)
        self._pre_request_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._pre_request_edit.textChanged.connect(self._schedule_version_capture)

        self._ensure_script_language_timers()
        self._pre_script_lang_auto = True

        # Runtime banner (hidden by default).
        self._pre_runtime_banner = RuntimeBanner()
        self._pre_runtime_banner.setVisible(False)
        self._pre_runtime_banner.download_completed.connect(self._on_deno_installed)
        self._pre_runtime_banner.open_settings_clicked.connect(self._emit_open_scripting_settings)

        if not hasattr(self, "_disabled_inherited"):
            self._disabled_inherited: list[dict[str, int | str]] = []

        if self._inherited_banners_supported:
            self._pre_inherited_banner = InheritedScriptsBanner(script_type="pre_request")
            self._pre_inherited_banner.setVisible(False)
            self._pre_inherited_banner.view_chain_requested.connect(
                partial(self._open_inherited_chain_drawer, "pre_request")
            )
        else:
            self._pre_inherited_banner = None  # type: ignore[assignment]

        # Editor pane (runtime banner + search bar + editor + status bar).
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._pre_runtime_banner)

        self._pre_search_bar = SearchReplaceBar(self._pre_request_edit, editor_pane)
        editor_layout.addWidget(self._pre_search_bar)
        editor_layout.addWidget(self._pre_request_edit, 1)

        self._build_script_header(
            parent_layout,
            history_type="pre_request",
            search_bar=self._pre_search_bar,
            editor=self._pre_request_edit,
            inherited_banner=self._pre_inherited_banner,
        )
        self._build_script_status_bar(
            editor_layout,
            self._pre_request_edit,
            "pre_request",
        )

        # Connect text and language changes to banner re-check.
        self._pre_request_edit.textChanged.connect(self._schedule_banner_check)
        self._pre_request_edit.textChanged.connect(
            lambda: self._on_script_text_for_auto_lang("pre_request"),
        )

        # Output panel for inline script execution results.
        from ui.request.request_editor.scripts.output_panel import \
            ScriptOutputPanel

        self._pre_output_panel = ScriptOutputPanel(
            script_type="pre_request",
            host_kind=self._script_output_host_kind,
        )

        # Resizable splitter between editor and output.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_pane)
        splitter.addWidget(self._pre_output_panel)
        # Extra space favours output; initial handle position is set by
        # :meth:`_schedule_script_splitter_sizes` (stretch alone is not enough).
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)
        splitter.setObjectName("scriptEditorOutputSplitter")
        self._pre_script_splitter = splitter
        self._connect_script_splitter_vis_hooks()
        self._schedule_script_splitter_sizes(splitter)
        parent_layout.addWidget(splitter, 1)

        self._pre_output_panel.bind_script_editor(self._pre_request_edit)
        self._refresh_snippets_button("pre_request")

    def _build_test_script_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Post-response Script tab contents."""
        self._test_script_edit = CodeEditorWidget()
        self._test_script_edit.set_language("javascript")
        self._test_script_edit.setPlaceholderText(
            "Script to run after the response is received\u2026"
        )
        self._test_script_edit.set_breakpoint_gutter_visible(True)
        self._test_script_edit.setMinimumHeight(80)
        self._test_script_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._test_script_edit.textChanged.connect(self._schedule_version_capture)

        self._test_script_lang_auto = True

        # Runtime banner (hidden by default).
        self._test_runtime_banner = RuntimeBanner()
        self._test_runtime_banner.setVisible(False)
        self._test_runtime_banner.download_completed.connect(self._on_deno_installed)
        self._test_runtime_banner.open_settings_clicked.connect(self._emit_open_scripting_settings)

        if self._inherited_banners_supported:
            self._test_inherited_banner = InheritedScriptsBanner(script_type="test")
            self._test_inherited_banner.setVisible(False)
            self._test_inherited_banner.view_chain_requested.connect(
                partial(self._open_inherited_chain_drawer, "test")
            )
        else:
            self._test_inherited_banner = None  # type: ignore[assignment]

        # Editor pane (runtime banner + search bar + editor + status bar).
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._test_runtime_banner)

        self._test_search_bar = SearchReplaceBar(self._test_script_edit, editor_pane)
        editor_layout.addWidget(self._test_search_bar)
        editor_layout.addWidget(self._test_script_edit, 1)

        self._build_script_header(
            parent_layout,
            history_type="test",
            search_bar=self._test_search_bar,
            editor=self._test_script_edit,
            inherited_banner=self._test_inherited_banner,
        )
        self._build_script_status_bar(
            editor_layout,
            self._test_script_edit,
            "test",
        )

        # Connect text and language changes to banner re-check.
        self._test_script_edit.textChanged.connect(self._schedule_banner_check)
        self._test_script_edit.textChanged.connect(
            lambda: self._on_script_text_for_auto_lang("test"),
        )

        # Output panel for inline script execution results.
        from ui.request.request_editor.scripts.output_panel import \
            ScriptOutputPanel

        self._test_output_panel = ScriptOutputPanel(
            script_type="test",
            host_kind=self._script_output_host_kind,
        )

        # Resizable splitter between editor and output.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_pane)
        splitter.addWidget(self._test_output_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)
        splitter.setObjectName("scriptEditorOutputSplitter")
        self._test_script_splitter = splitter
        self._connect_script_splitter_vis_hooks()
        self._schedule_script_splitter_sizes(splitter)
        parent_layout.addWidget(splitter, 1)

        self._test_output_panel.bind_script_editor(self._test_script_edit)

        self._test_script_edit.set_test_gutter_enabled(True)
        self._test_script_edit.textChanged.connect(self._refresh_pm_test_gutter_markers)
        self._test_script_edit.run_single_test_requested.connect(self._run_single_test)
        self._test_script_edit.debug_single_test_requested.connect(
            lambda n: self._run_single_test(n, debug=True)
        )
        self._refresh_pm_test_gutter_markers()
        self._refresh_snippets_button("test")

    def _refresh_pm_test_gutter_markers(self) -> None:
        """Update per-line ``pm.test`` markers in the post-response editor gutter."""
        if not getattr(self, "_scripts_editor_materialized", True):
            return
        from services.scripting.engine import (find_pm_tests,
                                               find_top_level_statement_lines)

        lang = self._test_script_edit.language
        self._test_script_edit.set_pm_tests(
            find_pm_tests(self._test_script_edit.toPlainText(), lang)
        )
        self._test_script_edit.set_top_level_lines(
            find_top_level_statement_lines(self._test_script_edit.toPlainText(), lang)
        )

    def _connect_script_splitter_vis_hooks(self) -> None:
        """Re-apply default split when the scripts UI becomes visible (tab has real height)."""
        if getattr(self, "_script_splitter_vis_hooks", False):
            return
        self._script_splitter_vis_hooks = True
        if hasattr(self, "_scripts_sub_tabs"):
            self._scripts_sub_tabs.currentChanged.connect(self._on_script_splitter_context_shown)
        if hasattr(self, "_tabs") and hasattr(self, "_scripts_tab"):
            self._tabs.currentChanged.connect(self._on_script_splitter_context_shown)

    def _on_script_splitter_context_shown(self, *_args: object) -> None:
        """Sub-tab or top-level section changed; refresh split when Scripts is shown."""
        for sp in (
            getattr(self, "_pre_script_splitter", None),
            getattr(self, "_test_script_splitter", None),
        ):
            if isinstance(sp, QSplitter):
                self._schedule_script_splitter_sizes(sp)
        # Sub-tab swap: layout and ``setSizes`` are deferred — immediate handle
        # geometry can sit inside the editor until the stack repaints.
        self._schedule_refresh_script_split_full_width_line()

    def _ensure_output_pane_open(self, script_type: str) -> None:
        """Restore the default editor/output split if the user has the output collapsed.

        Called before Run / Run-all / Debug so the user sees output instead of
        having to drag the splitter handle back up themselves.
        """
        if script_type == "pre_request":
            splitter = getattr(self, "_pre_script_splitter", None)
        else:
            splitter = getattr(self, "_test_script_splitter", None)
        if not isinstance(splitter, QSplitter):
            return
        sizes = splitter.sizes()
        # Output pane is the second child; treat anything ≤ 4 px as collapsed.
        if len(sizes) == 2 and sizes[1] <= 4:
            self._schedule_script_splitter_sizes(splitter)

    def _schedule_script_splitter_sizes(self, splitter: QSplitter) -> None:
        """Set initial editor/output heights — QSplitter needs explicit ``setSizes``."""
        if splitter.count() != 2:
            return

        def try_apply(attempt: int = 0) -> None:
            h = splitter.height()
            if h < 30 and attempt < 30:
                QTimer.singleShot(40, partial(try_apply, attempt + 1))
                return
            if h < 50:
                return
            handles = (splitter.count() - 1) * splitter.handleWidth()
            avail = h - handles
            if avail < 100:
                return
            # Default slightly over half to output so Run / debug output is usable
            # without dragging the handle every time.
            out_h = max(200, int(avail * 0.56))
            ed_h = max(120, avail - out_h)
            splitter.setSizes([ed_h, out_h])
            self._refresh_script_split_full_width_line()

        QTimer.singleShot(0, partial(try_apply, 0))

    # -- Full-width script split line (editor chrome margins unchanged) --------

    def _init_script_split_full_width_line(self) -> None:
        """Create a non-layout child frame drawn across the host widget width."""
        if getattr(self, "_script_split_full_width_line", None) is not None:
            return
        host = cast(QWidget, self)
        line = QFrame(host)
        line.setObjectName("scriptSplitFullWidthLine")
        line.setFixedHeight(_SCRIPT_SPLIT_FULL_WIDTH_LINE_HEIGHT)
        line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        line.hide()
        self._script_split_full_width_line = line

    def _schedule_refresh_script_split_full_width_line(self) -> None:
        """Reposition the overlay after the active splitter has a stable geometry."""
        QTimer.singleShot(0, self._refresh_script_split_full_width_line)
        QTimer.singleShot(50, self._refresh_script_split_full_width_line)

    def _wire_script_split_full_width_line(self) -> None:
        """Connect splitters once script UI exists (lazy request editor)."""
        if getattr(self, "_script_split_full_width_line_wired", False):
            return
        self._script_split_full_width_line_wired = True
        self._init_script_split_full_width_line()
        for sp in (
            getattr(self, "_pre_script_splitter", None),
            getattr(self, "_test_script_splitter", None),
        ):
            if isinstance(sp, QSplitter):
                sp.splitterMoved.connect(self._refresh_script_split_full_width_line)

    def _script_split_full_width_line_should_show(self) -> bool:
        """True when the Scripts section tab is active and editors exist."""
        tabs = getattr(self, "_tabs", None)
        scripts_tab = getattr(self, "_scripts_tab", None)
        if tabs is None or scripts_tab is None:
            return False
        if tabs.currentIndex() != tabs.indexOf(scripts_tab):
            return False
        if not getattr(self, "_scripts_editor_materialized", True):
            return False
        sub = getattr(self, "_scripts_sub_tabs", None)
        if sub is None:
            return False
        splitter = self._active_script_editor_output_splitter()
        return splitter is not None and splitter.count() >= 2

    def _active_script_editor_output_splitter(self) -> QSplitter | None:
        """Return the visible Pre-request or Post-response editor/output splitter."""
        sub = getattr(self, "_scripts_sub_tabs", None)
        if sub is None:
            return None
        if sub.currentIndex() == 0:
            sp = getattr(self, "_pre_script_splitter", None)
        else:
            sp = getattr(self, "_test_script_splitter", None)
        return sp if isinstance(sp, QSplitter) else None

    def _refresh_script_split_full_width_line(self, *_args: object) -> None:
        """Show or hide the overlay and align it to the editor/output seam."""
        line = getattr(self, "_script_split_full_width_line", None)
        if line is None:
            return
        if not self._script_split_full_width_line_should_show():
            line.hide()
            return
        splitter = self._active_script_editor_output_splitter()
        if splitter is None or splitter.count() < 2:
            line.hide()
            return
        if not splitter.isVisible():
            line.hide()
            return
        top_pane = splitter.widget(0)
        if top_pane is None or not top_pane.isVisible():
            line.hide()
            return
        host = cast(QWidget, self)
        host_w = host.width()
        if host_w < 2:
            line.hide()
            return
        # Seam: local point (w/2, height()) lies on the lower edge of the top
        # pane (first row of the splitter handle band).  Avoid mapping the
        # QSplitterHandle — its rect can lag QTabWidget sub-tab switches.
        seam = top_pane.mapTo(host, QPoint(top_pane.width() // 2, top_pane.height()))
        lh = line.height()
        y = seam.y() - lh // 2 + _SCRIPT_SPLIT_FULL_WIDTH_LINE_TOP_MARGIN
        line.setGeometry(0, y, host_w, lh)
        line.show()
        line.raise_()

    def _ensure_script_language_timers(self) -> None:
        """Create debounce timers for automatic script language detection (once)."""
        if hasattr(self, "_pre_lang_auto_timer"):
            return
        timer_parent = self._pre_request_edit
        self._pre_lang_auto_timer = QTimer(timer_parent)
        self._pre_lang_auto_timer.setSingleShot(True)
        self._pre_lang_auto_timer.setInterval(400)
        self._pre_lang_auto_timer.timeout.connect(
            lambda: self._apply_auto_script_language("pre_request")
        )
        self._test_lang_auto_timer = QTimer(timer_parent)
        self._test_lang_auto_timer.setSingleShot(True)
        self._test_lang_auto_timer.setInterval(400)
        self._test_lang_auto_timer.timeout.connect(lambda: self._apply_auto_script_language("test"))

    def _script_lang_auto(self, script_type: Literal["pre_request", "test"]) -> bool:
        """Return whether *script_type* uses automatic language detection."""
        return (
            self._pre_script_lang_auto
            if script_type == "pre_request"
            else self._test_script_lang_auto
        )

    def _set_script_lang_auto(
        self, script_type: Literal["pre_request", "test"], value: bool
    ) -> None:
        """Enable or disable automatic language detection for *script_type*."""
        if script_type == "pre_request":
            self._pre_script_lang_auto = value
        else:
            self._test_script_lang_auto = value

    def _sync_lang_menu_button_text(self, editor: CodeEditorWidget, btn: QToolButton) -> None:
        """Refresh the status-bar language button label from *editor*."""
        btn.setText(code_to_display(editor.language))

    def _create_script_lang_toolbutton(
        self,
        editor: CodeEditorWidget,
        script_type: Literal["pre_request", "test"],
    ) -> QToolButton:
        """Build a VS Code-style language picker (popup menu on the status bar)."""
        btn = QToolButton()
        btn.setObjectName("scriptLanguageLinkButton")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Select language mode")
        self._sync_lang_menu_button_text(editor, btn)

        menu = QMenu(btn)
        act_js = QAction("JavaScript", menu)
        act_js.setCheckable(True)
        act_ts = QAction("TypeScript", menu)
        act_ts.setCheckable(True)
        act_py = QAction("Python", menu)
        act_py.setCheckable(True)
        group = QActionGroup(menu)
        group.setExclusive(True)
        group.addAction(act_js)
        group.addAction(act_ts)
        group.addAction(act_py)
        menu.addAction(act_js)
        menu.addAction(act_ts)
        menu.addAction(act_py)
        menu.addSeparator()
        act_auto = QAction("Auto", menu)
        menu.addAction(act_auto)

        def sync_checks() -> None:
            lang = editor.language
            act_js.setChecked(lang == "javascript")
            act_ts.setChecked(lang == "typescript")
            act_py.setChecked(lang == "python")

        menu.aboutToShow.connect(sync_checks)

        def pick_js() -> None:
            self._set_script_lang_auto(script_type, False)
            editor.set_language("javascript")
            self._sync_lang_menu_button_text(editor, btn)
            if script_type == "test":
                self._refresh_pm_test_gutter_markers()
            self._schedule_banner_check()
            if not getattr(self, "_loading", False):
                self._on_field_changed()  # type: ignore[attr-defined]
            self._refresh_snippets_button(script_type)

        def pick_ts() -> None:
            self._set_script_lang_auto(script_type, False)
            editor.set_language("typescript")
            self._sync_lang_menu_button_text(editor, btn)
            if script_type == "test":
                self._refresh_pm_test_gutter_markers()
            self._schedule_banner_check()
            if not getattr(self, "_loading", False):
                self._on_field_changed()  # type: ignore[attr-defined]
            self._refresh_snippets_button(script_type)

        def pick_py() -> None:
            self._set_script_lang_auto(script_type, False)
            editor.set_language("python")
            self._sync_lang_menu_button_text(editor, btn)
            if script_type == "test":
                self._refresh_pm_test_gutter_markers()
            self._schedule_banner_check()
            if not getattr(self, "_loading", False):
                self._on_field_changed()  # type: ignore[attr-defined]
            self._refresh_snippets_button(script_type)

        def pick_auto() -> None:
            self._set_script_lang_auto(script_type, True)
            self._apply_auto_script_language(script_type)

        act_js.triggered.connect(pick_js)
        act_ts.triggered.connect(pick_ts)
        act_py.triggered.connect(pick_py)
        act_auto.triggered.connect(pick_auto)
        btn.setMenu(menu)
        return btn

    def _on_script_text_for_auto_lang(self, script_type: Literal["pre_request", "test"]) -> None:
        """Restart debounced auto language detection when script text changes."""
        if getattr(self, "_loading", False):
            return
        if not self._script_lang_auto(script_type):
            return
        timer = (
            self._pre_lang_auto_timer
            if script_type == "pre_request"
            else self._test_lang_auto_timer
        )
        timer.start()

    def _apply_auto_script_language(self, script_type: Literal["pre_request", "test"]) -> None:
        """Apply heuristics to *editor* when in automatic language mode."""
        editor = self._pre_request_edit if script_type == "pre_request" else self._test_script_edit
        btn = self._pre_lang_menu_btn if script_type == "pre_request" else self._test_lang_menu_btn
        if not self._script_lang_auto(script_type):
            return
        text = editor.toPlainText()
        want = detect_script_language(text, default=editor.language)
        if want != editor.language:
            editor.set_language(want)
        self._sync_lang_menu_button_text(editor, btn)
        if script_type == "test":
            self._refresh_pm_test_gutter_markers()
        self._schedule_banner_check()
        if not getattr(self, "_loading", False):
            self._on_field_changed()  # type: ignore[attr-defined]
        self._refresh_snippets_button(script_type)

    def _build_script_header(
        self,
        parent_layout: QVBoxLayout,
        *,
        history_type: str,
        search_bar: SearchReplaceBar,
        editor: CodeEditorWidget,
        inherited_banner: InheritedScriptsBanner | None = None,
    ) -> None:
        """Build editor toolbar (find/replace, redo/undo, run current/all, debug, save)."""
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)

        def _make_icon_btn(
            icon: str, tip: str, slot: Any, *, enabled: bool = True
        ) -> QPushButton:
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
            # Plain (non-VLine) frame so the colour comes from QSS
            # (``background: {p["border"]}``) instead of Qt's hard-coded
            # palette mid-tone (which paints VLine near-black in light themes).
            sep = QFrame()
            sep.setObjectName("scriptToolbarSeparator")
            sep.setFrameShape(QFrame.Shape.NoFrame)
            sep.setFixedWidth(1)
            sep.setMinimumHeight(18)
            lang_row.addSpacing(4)
            lang_row.addWidget(sep)
            lang_row.addSpacing(4)

        # -- Group 1: Find / Replace / Go to Line -----------------------
        find_hint = QKeySequence(QKeySequence.StandardKey.Find).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        replace_hint = QKeySequence(QKeySequence.StandardKey.Replace).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        for icon, tip, slot in (
            ("magnifying-glass", f"Find ({find_hint})", search_bar.toggle_search),
            ("swap", f"Find & Replace ({replace_hint})", search_bar.toggle_replace),
            ("list-numbers", "Go to Line (Ctrl+G)", search_bar.goto_line),
        ):
            lang_row.addWidget(_make_icon_btn(icon, tip, slot))

        _add_separator()

        # -- Group 2: Redo / Undo (order per UX spec) -------------------
        undo_hint = QKeySequence(QKeySequence.StandardKey.Undo).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        redo_hint = QKeySequence(QKeySequence.StandardKey.Redo).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        redo_btn = _make_icon_btn(
            "arrow-clockwise", f"Redo ({redo_hint})", editor.redo, enabled=False
        )
        editor.redoAvailable.connect(redo_btn.setEnabled)
        lang_row.addWidget(redo_btn)

        undo_btn = _make_icon_btn(
            "arrow-counter-clockwise", f"Undo ({undo_hint})", editor.undo, enabled=False
        )
        editor.undoAvailable.connect(undo_btn.setEnabled)
        lang_row.addWidget(undo_btn)

        _add_separator()

        # -- Group 3: Run current / Run all (inherited) / Debug ---------
        run_btn = _make_icon_btn(
            "play",
            "Run current script (Ctrl+Enter)",
            lambda _checked=False, ht=history_type: self._run_inline_script(ht),
        )
        lang_row.addWidget(run_btn)
        if not hasattr(self, "_run_buttons"):
            self._run_buttons: dict[str, QPushButton] = {}
        self._run_buttons[history_type] = run_btn

        run_all_btn = _make_icon_btn(
            "stack-simple",
            "Run all (inherited + current)",
            lambda _checked=False, ht=history_type: self._run_all_inline_script(ht),
        )
        run_all_btn.hide()  # shown by ``_refresh_run_all_buttons`` when inheritance exists
        lang_row.addWidget(run_all_btn)
        if not hasattr(self, "_run_all_buttons"):
            self._run_all_buttons: dict[str, QPushButton] = {}
        self._run_all_buttons[history_type] = run_all_btn

        debug_btn = _make_icon_btn(
            "bug",
            "Debug script (breakpoints)",
            lambda _checked=False, ht=history_type: self._debug_inline_script(ht),
        )
        lang_row.addWidget(debug_btn)
        if not hasattr(self, "_debug_buttons"):
            self._debug_buttons: dict[str, QPushButton] = {}
        self._debug_buttons[history_type] = debug_btn

        _add_separator()

        # -- Group 4: Save + Auto-save toggle ---------------------------
        if not hasattr(self, "_auto_save_checkboxes"):
            self._auto_save_checkboxes: list[QCheckBox] = []
            self._auto_save_enabled = True
        if not hasattr(self, "_save_buttons"):
            self._save_buttons: dict[str, QPushButton] = {}

        save_btn = _make_icon_btn(
            "floppy-disk",
            "Save script (Ctrl+S)",
            lambda: cast(Any, self).save_requested.emit(),  # type: ignore[attr-defined]
        )
        self._save_buttons[history_type] = save_btn
        lang_row.addWidget(save_btn)

        auto_save_cb = QCheckBox("Auto-save")
        auto_save_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        auto_save_cb.setToolTip("Capture script versions continuously")
        auto_save_cb.setChecked(self._auto_save_enabled)
        auto_save_cb.toggled.connect(self._on_auto_save_toggled)
        self._auto_save_checkboxes.append(auto_save_cb)
        lang_row.addWidget(auto_save_cb)

        self._sync_save_buttons_for_auto_save()

        lang_row.addStretch()

        if inherited_banner is not None:
            lang_row.addWidget(inherited_banner)

        parent_layout.addLayout(lang_row)

        # -- Debug step bar: full width under the toolbar row, hidden until
        #    a pause (same band / margins as :class:`SearchReplaceBar`).
        debug_bar = QWidget()
        debug_bar.setObjectName("scriptDebugBar")
        db_layout = QVBoxLayout(debug_bar)
        db_layout.setContentsMargins(0, 4, 0, 4)
        db_layout.setSpacing(0)
        debug_controls = DebugControls()
        debug_controls.hide()
        debug_controls.step_requested.connect(
            self.debug_step_requested.emit  # type: ignore[attr-defined, call-overload]
        )
        db_layout.addWidget(debug_controls)
        if not hasattr(self, "_debug_controls"):
            self._debug_controls: dict[str, DebugControls] = {}
        self._debug_controls[history_type] = debug_controls
        parent_layout.addWidget(debug_bar)
        # While ``DebugControls`` is hidden, layout margins on this host still reserved ~8px.
        # Hide the whole host until a send-pipeline pause shows the controls (and parent bar).
        debug_bar.hide()

        # Shared debounce timer (created once)
        if not hasattr(self, "_version_capture_timer"):
            initial_ms = _AUTO_SAVE_CAPTURE_MS if self._auto_save_enabled else _VERSION_CAPTURE_MS
            self._version_capture_timer = QTimer()
            self._version_capture_timer.setSingleShot(True)
            self._version_capture_timer.setInterval(initial_ms)
            self._version_capture_timer.timeout.connect(self._capture_script_versions)

    def _build_script_status_bar(
        self,
        parent_layout: QVBoxLayout,
        editor: CodeEditorWidget,
        script_type: Literal["pre_request", "test"],
    ) -> None:
        """Build a status strip: Ln/Col, language picker, char count."""
        row = QWidget()
        row.setObjectName("scriptEditorStatusBar")
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)

        ln_lbl = QLabel()
        ln_lbl.setObjectName("mutedLabel")
        sep1 = QLabel("\u2502")
        sep1.setObjectName("mutedLabel")
        lang_btn = self._create_script_lang_toolbutton(editor, script_type)
        sep_hist = QLabel("\u2502")
        sep_hist.setObjectName("mutedLabel")
        hist_btn = QToolButton()
        hist_btn.setObjectName("scriptHistoryLinkButton")
        hist_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        hist_btn.setText("History")
        hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hist_btn.setToolTip("View script version history")
        hist_btn.clicked.connect(
            lambda _checked=False, ht=script_type: self._open_version_history(ht),
        )
        # Snippets sits after History (Postman-style). Gated by has_snippets so
        # languages without a JSON file stay disabled with a clear tooltip.
        sep_snip = QLabel("\u2502")
        sep_snip.setObjectName("mutedLabel")
        snip_btn = QToolButton()
        snip_btn.setObjectName("scriptHistoryLinkButton")
        snip_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        snip_btn.setText("Snippets")
        snip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        snip_btn.setToolTip("Insert a code snippet")
        snip_btn.clicked.connect(
            lambda _checked=False, ht=script_type: self._open_snippets(ht),
        )
        sep2 = QLabel("\u2502")
        sep2.setObjectName("mutedLabel")
        chars_lbl = QLabel()
        chars_lbl.setObjectName("mutedLabel")

        h.addWidget(ln_lbl)
        h.addWidget(sep1)
        h.addWidget(lang_btn)
        h.addWidget(sep_hist)
        h.addWidget(hist_btn)
        h.addWidget(sep_snip)
        h.addWidget(snip_btn)
        h.addWidget(sep2)
        h.addWidget(chars_lbl)
        h.addStretch()
        parent_layout.addWidget(row)

        if script_type == "pre_request":
            self._pre_status_ln_lbl = ln_lbl
            self._pre_status_chars_lbl = chars_lbl
            self._pre_lang_menu_btn = lang_btn
            self._pre_history_btn = hist_btn
            self._pre_snippets_btn = snip_btn
        else:
            self._test_status_ln_lbl = ln_lbl
            self._test_status_chars_lbl = chars_lbl
            self._test_lang_menu_btn = lang_btn
            self._test_history_btn = hist_btn
            self._test_snippets_btn = snip_btn

        def _update(_line: int = 0, _col: int = 0) -> None:
            cur = editor.textCursor()
            ln = cur.blockNumber() + 1
            col = cur.positionInBlock() + 1
            ln_lbl.setText(f"Ln {ln}, Col {col}")
            chars_lbl.setText(f"{len(editor.toPlainText())} chars")
            self._sync_lang_menu_button_text(editor, lang_btn)

        editor.cursor_position_changed.connect(_update)
        editor.textChanged.connect(_update)
        _update()

    @property
    def _history_btn(self) -> QToolButton:
        """Return the pre-request history control for legacy callers."""
        return self._pre_history_btn

    def _load_scripts(self, scripts: Any) -> None:
        """Populate script editors from stored data (dict, events list, JSON, or None)."""
        if isinstance(scripts, str) and scripts.strip():
            # Legacy raw string — try to parse as JSON dict
            import json

            try:
                scripts = json.loads(scripts)
            except (json.JSONDecodeError, TypeError):
                # Treat entire string as pre-request script
                self._pre_request_edit.setPlainText(scripts)
                self._test_script_edit.setPlainText("")
                self._pre_request_edit.set_language("javascript")
                self._test_script_edit.set_language("javascript")
                self._set_script_lang_auto("pre_request", True)
                self._set_script_lang_auto("test", True)
                self._sync_lang_menu_button_text(self._pre_request_edit, self._pre_lang_menu_btn)
                self._sync_lang_menu_button_text(self._test_script_edit, self._test_lang_menu_btn)
                self._disabled_inherited = []
                self._refresh_snippets_button("pre_request")
                self._refresh_snippets_button("test")
                return

        if getattr(self, "_request_id", None) is not None and isinstance(scripts, dict):
            self._disabled_inherited = normalize_disabled_inherited(
                scripts.get("disabled_inherited")
            )
        else:
            self._disabled_inherited = []

        events = _normalize_events(scripts)

        self._pre_request_edit.setPlainText(events.get("pre_request") or "")
        self._test_script_edit.setPlainText(events.get("test") or "")

        # Languages (per-tab, with fallback to shared 'language' key) — stored codes win on load.
        shared_code = "javascript"
        if isinstance(scripts, dict):
            shared_code = normalise_script_code(str(scripts.get("language", "") or ""))
        pre_code = shared_code
        test_code = shared_code
        if isinstance(scripts, dict):
            pr = str(scripts.get("pre_language", "") or "").lower()
            if pr:
                pre_code = normalise_script_code(pr)
            tr = str(scripts.get("test_language", "") or "").lower()
            if tr:
                test_code = normalise_script_code(tr)
        self._pre_request_edit.set_language(pre_code)
        self._test_script_edit.set_language(test_code)
        self._set_script_lang_auto("pre_request", False)
        self._set_script_lang_auto("test", False)
        self._sync_lang_menu_button_text(self._pre_request_edit, self._pre_lang_menu_btn)
        self._sync_lang_menu_button_text(self._test_script_edit, self._test_lang_menu_btn)
        self._refresh_snippets_button("pre_request")
        self._refresh_snippets_button("test")

        # Restore per-entity auto-save preference
        self._restore_auto_save_state()
        self._refresh_inherited_banners()
        self._refresh_pm_test_gutter_markers()

    def _get_scripts_data(self) -> dict[str, str | int | list | bool | None] | None:
        """Build the scripts dict from the editor contents."""
        pre = self._pre_request_edit.toPlainText()
        test = self._test_script_edit.toPlainText()
        has_body = bool(pre or test)
        rid = getattr(self, "_request_id", None)
        disabled: list[dict[str, int | str]] = []
        if rid is not None:
            disabled = normalize_disabled_inherited(self._disabled_inherited)

        if not has_body and not disabled:
            return None
        if not has_body and disabled:
            return {"disabled_inherited": disabled}

        pre_lang = self._pre_request_edit.language
        test_lang = self._test_script_edit.language
        data: dict[str, str | int | list | bool | None] = {
            "pre_request": pre or None,
            "test": test or None,
            "pre_language": pre_lang,
            "test_language": test_lang,
            "language": pre_lang,  # backward compat
        }
        if disabled:
            data["disabled_inherited"] = disabled
        return data

    def _clear_scripts(self) -> None:
        """Reset both script editors and language selectors."""
        self._disabled_inherited = []
        self._pre_request_edit.clear()
        self._test_script_edit.clear()
        self._test_script_edit.set_pm_tests([])
        self._pre_request_edit.set_language("javascript")
        self._test_script_edit.set_language("javascript")
        self._set_script_lang_auto("pre_request", True)
        self._set_script_lang_auto("test", True)
        self._sync_lang_menu_button_text(self._pre_request_edit, self._pre_lang_menu_btn)
        self._sync_lang_menu_button_text(self._test_script_edit, self._test_lang_menu_btn)
        self._refresh_snippets_button("pre_request")
        self._refresh_snippets_button("test")
        # Reset auto-save to global default
        default_on = self._read_auto_save_global_default()
        self._auto_save_enabled = default_on
        for cb in self._auto_save_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(default_on)
            cb.blockSignals(False)
        self._version_capture_timer.setInterval(
            _AUTO_SAVE_CAPTURE_MS if default_on else _VERSION_CAPTURE_MS,
        )
        if getattr(self, "_pre_inherited_banner", None) is not None:
            self._pre_inherited_banner.set_inherited_info(0, "")
        if getattr(self, "_test_inherited_banner", None) is not None:
            self._test_inherited_banner.set_inherited_info(0, "")

    @staticmethod
    def _inherited_name_snippet(blocks: list[dict[str, object]], *, max_names: int = 4) -> str:
        names: list[str] = []
        for b in blocks:
            n = str(b.get("name", "") or "")
            if n and n not in names:
                names.append(n)
        if not names:
            return ""
        if len(names) <= max_names:
            return ", ".join(names)
        return ", ".join(names[: max_names - 1]) + f", and {len(names) - (max_names - 1)} more"

    @staticmethod
    def _inherited_blocks_for_type(
        chain: list[dict[str, Any]], script_type: str
    ) -> list[dict[str, Any]]:
        """Build UI blocks: pre uses root\u2192leaf, test uses nearest\u2192root (execution order for inherited)."""
        if not chain or len(chain) < 2:
            return []
        layers = list(chain[:-1])  # collections only
        if script_type == "test":
            layers.reverse()
        st_key = "test" if script_type == "test" else "pre_request"
        out: list[dict[str, Any]] = []
        for c in layers:
            ev = _normalize_events(c.get("scripts"))
            code = (ev.get(st_key) or "").strip()
            if not code:
                continue
            lang = str(ev.get("language", "javascript") or "javascript")
            out.append(
                {
                    "collection_id": c["id"],
                    "name": c.get("name", ""),
                    "code": code,
                    "language": lang,
                }
            )
        return out

    def _refresh_inherited_banners(self) -> None:
        """Show or hide inherited-script banners for the current request (request tabs only)."""
        pre_bnr = getattr(self, "_pre_inherited_banner", None)
        test_bnr = getattr(self, "_test_inherited_banner", None)
        if pre_bnr is None or test_bnr is None:
            return
        rid = getattr(self, "_request_id", None)
        if rid is None:
            pre_bnr.set_inherited_info(0, "")
            test_bnr.set_inherited_info(0, "")
            self._sync_run_all_buttons(pre_count=0, test_count=0)
            return
        try:
            chain = get_script_chain(rid)
        except (TypeError, ValueError):
            chain = []
        pre_b = self._inherited_blocks_for_type(chain, "pre_request")
        te_b = self._inherited_blocks_for_type(chain, "test")
        pre_bnr.set_inherited_info(
            len(pre_b),
            self._inherited_name_snippet(pre_b),
        )
        test_bnr.set_inherited_info(
            len(te_b),
            self._inherited_name_snippet(te_b),
        )
        self._sync_run_all_buttons(pre_count=len(pre_b), test_count=len(te_b))

    def _sync_run_all_buttons(self, *, pre_count: int, test_count: int) -> None:
        """Show the Run-all toolbar button only when inherited scripts exist."""
        run_all = getattr(self, "_run_all_buttons", None)
        if not run_all:
            return
        pre_btn = run_all.get("pre_request")
        if pre_btn is not None:
            pre_btn.setVisible(pre_count > 0)
        test_btn = run_all.get("test")
        if test_btn is not None:
            test_btn.setVisible(test_count > 0)

    def _open_inherited_chain_drawer(self, script_type: str) -> None:
        """Open the read-only chain dialog for the given script kind."""
        rid = getattr(self, "_request_id", None)
        if rid is None:
            return
        from ui.request.request_editor.scripts.inherited_chain_drawer import \
            InheritedChainDrawer

        try:
            chain = get_script_chain(rid)
        except (TypeError, ValueError):
            return
        blocks = self._inherited_blocks_for_type(chain, script_type)
        if not blocks:
            return
        self._pending_inherited_source_open: tuple[int, str] | None = None

        def _capture_edit_collection_source(collection_id: int) -> None:
            self._pending_inherited_source_open = (collection_id, script_type)

        dlg = InheritedChainDrawer(
            cast(Any, cast(Any, self).window() or self),
            script_type=script_type,
            blocks=blocks,
            disabled_inherited=list(self._disabled_inherited),
            on_edit_collection_source=_capture_edit_collection_source,
        )
        dlg.disabled_inherited_changed.connect(self._on_inherited_disabled_list_changed)
        dlg.exec()
        pending = self._pending_inherited_source_open
        self._pending_inherited_source_open = None
        if pending is None:
            return
        pending_raw, script_kind = pending
        try:
            collection_id = int(pending_raw)
        except (TypeError, ValueError):
            return
        if script_kind not in ("pre_request", "test"):
            script_kind = None
        # Prefer the dialog parent chain: ``self.window()`` on the request editor
        # can be wrong in some WM / embedded layouts while the dialog was parented
        # to the real main window explicitly.
        host = self._folder_open_host_from_dialog(dlg)
        # Defer one tick: opening / switching tabs immediately in the same call stack
        # as ``QDialog.exec()`` returning is unreliable on some platforms.
        if host is not None:
            QTimer.singleShot(
                0,
                lambda h=host,
                cid=collection_id,
                sk=script_kind: _ScriptsMixin._call_open_folder_on_host(
                    h, cid, focus_scripts_kind=sk
                ),
            )
        else:
            QTimer.singleShot(
                0,
                lambda ed=self,
                cid=collection_id,
                sk=script_kind: ed._open_inherited_source_collection_tab(
                    cid, focus_scripts_kind=sk
                ),
            )

    @staticmethod
    def _folder_open_host_from_dialog(dialog: QWidget) -> QWidget | None:
        """Find MainWindow (or any host) that implements ``_open_folder``."""
        w = dialog.parentWidget()
        while w is not None:
            fn = getattr(w, "_open_folder", None)
            if callable(fn):
                return w
            w = w.parentWidget()
        return None

    @staticmethod
    def _call_open_folder_on_host(
        host: QWidget,
        collection_id: int,
        *,
        focus_scripts_kind: str | None = None,
    ) -> None:
        open_fn = getattr(host, "_open_folder", None)
        if callable(open_fn):
            open_fn(collection_id, focus_scripts_kind=focus_scripts_kind)  # type: ignore[misc]

    def _open_inherited_source_collection_tab(
        self,
        collection_id: int,
        *,
        focus_scripts_kind: str | None = None,
    ) -> None:
        """Open the source collection folder tab (modal is already closed)."""
        w = cast(Any, self).window()
        if w is not None and hasattr(w, "_open_folder"):
            w._open_folder(  # type: ignore[union-attr]
                collection_id,
                focus_scripts_kind=focus_scripts_kind,
            )
        else:
            self.open_collection_requested.emit(collection_id)  # type: ignore[attr-defined]

    def _on_inherited_disabled_list_changed(
        self,
        new_list: list[dict[str, int | str]] | list[object],
    ) -> None:
        """Persist locally and mark dirty; chain execution uses the same list on next send."""
        self._disabled_inherited = normalize_disabled_inherited(new_list)  # type: ignore[arg-type]
        if not self._loading:  # type: ignore[attr-defined]
            self._on_field_changed()  # type: ignore[attr-defined]
        self._refresh_inherited_banners()

    def _has_scripts_content(self) -> bool:
        """Return whether either script editor has text or per-request disable entries."""
        return bool(
            self._pre_request_edit.toPlainText().strip()
            or self._test_script_edit.toPlainText().strip()
            or (getattr(self, "_request_id", None) is not None and self._disabled_inherited)
        )

    # -- Inline script execution ----------------------------------------

    def _run_inline_script(self, script_type: str, *, script_text: str | None = None) -> None:
        """Run the current script inline and display results."""
        from ui.request.request_editor.scripts.script_run_worker import \
            build_inline_context

        ensure_scripts = getattr(self, "_ensure_scripts_editors", None)
        if callable(ensure_scripts):
            ensure_scripts()
        self._ensure_output_pane_open(script_type)

        if script_type == "pre_request":
            editor = self._pre_request_edit
            panel = self._pre_output_panel
        else:
            editor = self._test_script_edit
            panel = self._test_output_panel

        script = (script_text if script_text is not None else editor.toPlainText()).strip()
        if not script:
            return

        language = editor.language
        if script_type == "test" and hasattr(panel, "response_source_mode"):
            mode = panel.response_source_mode()
            if mode == "live":
                main = cast(Any, self).window()
                start_live = getattr(main, "run_post_response_script_with_live_response", None)
                if callable(start_live):
                    run_btn = self._run_buttons.get(script_type)
                    debug_btn = (
                        self._debug_buttons.get(script_type)
                        if hasattr(self, "_debug_buttons")
                        else None
                    )
                    start_live(
                        editor=cast(Any, self),
                        panel=panel,
                        script=script,
                        language=language,
                        run_btn=run_btn,
                        debug_btn=debug_btn,
                    )
                    return
                panel.show_error("Could not run with live response in this context.")
                return

        response_data = panel.get_response_data() if script_type == "test" else None
        context = build_inline_context(
            script_type=script_type,
            response_data=response_data,
        )
        run_btn = self._run_buttons.get(script_type)
        debug_btn = (
            self._debug_buttons.get(script_type) if hasattr(self, "_debug_buttons") else None
        )
        panel.run_script(
            script=script,
            language=language,
            context=context,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

    def _run_all_inline_script(self, script_type: str) -> None:
        """Run the inherited chain plus the current editor inline.

        Order matches the runtime pipeline: pre-request top-down
        (collection → folder → request), test bottom-up (request →
        folder → collection). When no inheritance exists (draft tab or
        request without parents), falls back to :meth:`_run_inline_script`.
        """
        from services.scripting import ScriptEntry
        from ui.request.request_editor.scripts.script_run_worker import \
            build_inline_context

        ensure_scripts = getattr(self, "_ensure_scripts_editors", None)
        if callable(ensure_scripts):
            ensure_scripts()
        self._ensure_output_pane_open(script_type)

        if script_type == "pre_request":
            editor = self._pre_request_edit
            panel = self._pre_output_panel
        else:
            editor = self._test_script_edit
            panel = self._test_output_panel

        rid = getattr(self, "_request_id", None)
        blocks: list[dict[str, Any]] = []
        if rid is not None:
            try:
                chain = get_script_chain(rid)
            except (TypeError, ValueError):
                chain = []
            blocks = self._inherited_blocks_for_type(chain, script_type)

        current_code = editor.toPlainText()
        current_lang = editor.language
        current_entry: ScriptEntry | None = None
        if current_code.strip():
            current_entry = {
                "code": current_code,
                "language": current_lang,
                "source_name": "(current)",
            }

        entries: list[ScriptEntry] = []
        if script_type == "test":
            # Test execution order: request → nearest folder → … → collection.
            if current_entry is not None:
                entries.append(current_entry)
            entries.extend(
                {
                    "code": b["code"],
                    "language": b["language"],
                    "source_name": b["name"],
                }
                for b in blocks
            )
        else:
            entries.extend(
                {
                    "code": b["code"],
                    "language": b["language"],
                    "source_name": b["name"],
                }
                for b in blocks
            )
            if current_entry is not None:
                entries.append(current_entry)

        if not entries:
            return

        response_data = panel.get_response_data() if script_type == "test" else None
        context = build_inline_context(
            script_type=script_type,
            response_data=response_data,
        )
        run_btn = self._run_buttons.get(script_type)
        debug_btn = (
            self._debug_buttons.get(script_type) if hasattr(self, "_debug_buttons") else None
        )
        panel.run_script_chain(
            chain=entries,
            script_type=script_type,
            context=context,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

    def _debug_inline_script(self, script_type: str, *, script_text: str | None = None) -> None:
        """Start an inline script debug session for the current editor."""
        from services.scripting.debug import DebugProtocol
        from ui.request.request_editor.scripts.script_run_worker import \
            build_inline_context

        ensure_scripts = getattr(self, "_ensure_scripts_editors", None)
        if callable(ensure_scripts):
            ensure_scripts()
        self._ensure_output_pane_open(script_type)

        if script_type == "pre_request":
            editor = self._pre_request_edit
            panel = self._pre_output_panel
        else:
            editor = self._test_script_edit
            panel = self._test_output_panel

        # Do NOT ``.strip()`` here: editor breakpoints are 0-based block
        # indices on the *unmodified* document, and the bundle's debug
        # ``setBreakpointByUrl`` mapping is ``u0 + editor_line``. Stripping
        # leading blank/comment lines shifts every line in the bundle and
        # breakpoints land on the wrong source positions.
        script = script_text if script_text is not None else editor.toPlainText()
        if not script.strip():
            return

        language = editor.language
        response_data = panel.get_response_data() if script_type == "test" else None
        context = build_inline_context(
            script_type=script_type,
            response_data=response_data,
        )
        protocol = DebugProtocol()
        protocol.set_breakpoints(set(editor.breakpoints))

        main: Any = cast(Any, self).window()
        if hasattr(main, "_debug_protocol"):
            old = main._debug_protocol
            if old is not None:
                with contextlib.suppress(Exception):
                    old.stop()
            main._debug_protocol = protocol
        if hasattr(main, "_clear_debug_breakpoint_listeners"):
            main._clear_debug_breakpoint_listeners()

        def _push_inline() -> None:
            p = getattr(main, "_debug_protocol", None)
            if p is not None and p is protocol:
                p.update_breakpoints(set(editor.breakpoints))

        main._debug_breakpoint_connections = []
        editor.breakpoints_changed.connect(_push_inline)
        main._debug_breakpoint_connections.append((editor, _push_inline))
        run_btn = self._run_buttons.get(script_type)
        debug_btn = (
            self._debug_buttons.get(script_type) if hasattr(self, "_debug_buttons") else None
        )
        panel.run_script_debug(
            script=script,
            language=language,
            context=context,
            protocol=protocol,
            script_type=script_type,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

    def _run_single_test(self, name: str, *, debug: bool = False) -> None:
        """Run or debug only the named ``pm.test(…)`` block."""
        ensure_scripts = getattr(self, "_ensure_scripts_editors", None)
        if callable(ensure_scripts):
            ensure_scripts()

        user_src = self._test_script_edit.toPlainText()
        language = self._test_script_edit.language
        if language in ("javascript", "typescript"):
            wrapper = (
                "(function(){\n"
                f"  var __target={json.dumps(name)};\n"
                "  var __orig=pm.test;\n"
                "  pm.test = function(n, fn){ if (n===__target) return __orig.call(pm, n, fn); };\n"
                "})();\n"
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
            self._debug_inline_script("test", script_text=full_script)
        else:
            self._run_inline_script("test", script_text=full_script)

    # -- Auto-save toggle -----------------------------------------------

    def _auto_save_entity_key(self) -> str | None:
        """Return a unique key for the current request or collection."""
        rid = getattr(self, "_request_id", None)
        if rid is not None:
            return f"r:{rid}"
        cid = getattr(self, "_collection_id", None)
        if cid is not None:
            return f"c:{cid}"
        return None

    @staticmethod
    def _read_auto_save_global_default() -> bool:
        """Read the global auto-save default from QSettings."""
        from ui.styling.theme_manager import _APP, _ORG

        raw = QSettings(_ORG, _APP).value(_SETTINGS_KEY_AUTO_SAVE_DEFAULT, True)
        if isinstance(raw, str):
            return raw.lower() not in {"0", "false", "no", "off", ""}
        return bool(raw)

    @staticmethod
    def _read_auto_save_overrides() -> dict[str, bool]:
        """Read per-entity auto-save overrides from QSettings."""
        import json

        from ui.styling.theme_manager import _APP, _ORG

        raw = QSettings(_ORG, _APP).value(_SETTINGS_KEY_AUTO_SAVE_OVERRIDES, "")
        if not raw or not isinstance(raw, str):
            return {}
        try:
            items = json.loads(raw)
            return items if isinstance(items, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _write_auto_save_overrides(self, overrides: dict[str, bool]) -> None:
        """Persist the per-entity auto-save overrides."""
        import json

        from ui.styling.theme_manager import _APP, _ORG

        QSettings(_ORG, _APP).setValue(
            _SETTINGS_KEY_AUTO_SAVE_OVERRIDES,
            json.dumps(overrides, sort_keys=True),
        )

    def _restore_auto_save_state(self) -> None:
        """Restore the auto-save checkbox from per-entity override or global default."""
        key = self._auto_save_entity_key()
        overrides = self._read_auto_save_overrides()
        if key and key in overrides:
            enabled = overrides[key]
        else:
            enabled = self._read_auto_save_global_default()
        self._auto_save_enabled = enabled
        for cb in self._auto_save_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        interval = _AUTO_SAVE_CAPTURE_MS if enabled else _VERSION_CAPTURE_MS
        self._version_capture_timer.setInterval(interval)

    def _on_auto_save_toggled(self, checked: bool) -> None:
        """Sync all auto-save checkboxes, persist per entity, and adjust interval."""
        self._auto_save_enabled = checked
        for cb in self._auto_save_checkboxes:
            if cb.isChecked() != checked:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        self._sync_save_buttons_for_auto_save()
        interval = _AUTO_SAVE_CAPTURE_MS if checked else _VERSION_CAPTURE_MS
        self._version_capture_timer.setInterval(interval)
        if checked:
            self.capture_scripts_now()
        key = self._auto_save_entity_key()
        if key:
            global_default = self._read_auto_save_global_default()
            overrides = self._read_auto_save_overrides()
            if checked == global_default:
                overrides.pop(key, None)
            else:
                overrides[key] = checked
            self._write_auto_save_overrides(overrides)

    def _sync_save_buttons_for_auto_save(self) -> None:
        """Reflect the auto-save state on every Save toolbar button.

        Save is disabled while Auto-save is on (the auto-save timer is the
        actual persistence path); tooltip explains the disabled state.
        """
        save_buttons = getattr(self, "_save_buttons", None)
        if not save_buttons:
            return
        if self._auto_save_enabled:
            tip = "Save disabled — Auto-save is on (versions captured automatically)"
        else:
            tip = "Save script (Ctrl+S)"
        for btn in save_buttons.values():
            btn.setEnabled(not self._auto_save_enabled)
            btn.setToolTip(tip)

    # -- Version capture -----------------------------------------------

    def _schedule_version_capture(self) -> None:
        """Restart the debounce timer on any script text change."""
        if self._loading:  # type: ignore[attr-defined]
            return
        self._version_capture_timer.start()

    def _capture_script_versions(self) -> None:
        """Capture current script content as version snapshots."""
        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return

        pre = self._pre_request_edit.toPlainText()
        if pre.strip():
            pre_lang = self._pre_request_edit.language
            ScriptVersionService.capture(
                request_id=request_id,
                collection_id=collection_id,
                script_type="pre_request",
                content=pre,
                language=pre_lang,
            )

        test = self._test_script_edit.toPlainText()
        if test.strip():
            test_lang = self._test_script_edit.language
            ScriptVersionService.capture(
                request_id=request_id,
                collection_id=collection_id,
                script_type="test",
                content=test,
                language=test_lang,
            )

    def capture_scripts_now(self) -> None:
        """Force an immediate version snapshot (called on Send / Save)."""
        self._version_capture_timer.stop()
        self._capture_script_versions()

    # -- Cross-session undo --------------------------------------------

    def _script_cross_session_undo(self, editor: CodeEditorWidget, script_type: str) -> bool:
        """Attempt cross-session undo for *editor*.

        Returns ``True`` if a previous version was restored, ``False``
        if no earlier version exists.
        """
        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return False

        current = editor.toPlainText()
        previous = ScriptVersionService.get_previous_content(
            request_id=request_id,
            collection_id=collection_id,
            script_type=script_type,
            current_content=current,
        )
        if previous is None:
            return False

        # Replace content — this counts as a new Qt undo entry.
        editor.selectAll()
        editor.insertPlainText(previous)
        return True

    # -- Version history dialog ----------------------------------------

    def _refresh_snippets_button(self, script_type: Literal["pre_request", "test"]) -> None:
        """Enable Snippets when a JSON file exists for the editor language."""
        from ui.widgets.snippets.loader import has_snippets

        if script_type == "pre_request":
            editor = self._pre_request_edit
            btn = getattr(self, "_pre_snippets_btn", None)
        else:
            editor = self._test_script_edit
            btn = getattr(self, "_test_snippets_btn", None)
        if btn is None:
            return
        enabled = has_snippets(editor.language)
        btn.setEnabled(enabled)
        btn.setToolTip("Insert a code snippet" if enabled else f"No snippets for {editor.language}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)

    def _open_snippets(self, script_type: str) -> None:
        """Show the snippets popover under the per-tab Snippets control.

        ``QTextCursor.insertText`` replaces any selection when inserting.
        """
        from ui.widgets.snippets.loader import has_snippets
        from ui.widgets.snippets.popup import SnippetsPopup

        if script_type == "pre_request":
            editor = self._pre_request_edit
            anchor = self._pre_snippets_btn
        else:
            editor = self._test_script_edit
            anchor = self._test_snippets_btn
        language = editor.language
        if not has_snippets(language):
            return

        def _insert(body: str) -> None:
            cur = editor.textCursor()
            cur.insertText(body)
            editor.setFocus()

        SnippetsPopup.instance().show_for(anchor, language, script_type, _insert)

    def _open_version_history(self, script_type: str = "pre_request") -> None:
        """Open the version history dialog for the current request."""
        from ui.request.request_editor.scripts.version_history import \
            VersionHistoryDialog

        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return

        editor = self._pre_request_edit if script_type == "pre_request" else self._test_script_edit
        dlg = VersionHistoryDialog(
            request_id=request_id,
            collection_id=collection_id,
            current_pre=self._pre_request_edit.toPlainText(),
            current_test=self._test_script_edit.toPlainText(),
            language=editor.language,
            initial_tab=0 if script_type == "pre_request" else 1,
            parent=self._pre_request_edit,
        )
        if dlg.exec():
            restored = dlg.restored_content()
            if restored:
                script_type, content = restored
                editor = (
                    self._pre_request_edit
                    if script_type == "pre_request"
                    else self._test_script_edit
                )
                editor.selectAll()
                editor.insertPlainText(content)

    # -- Runtime banner ------------------------------------------------

    def _schedule_banner_check(self) -> None:
        """Restart the debounce timer for runtime banner re-check."""
        if getattr(self, "_loading", False):
            return
        if not hasattr(self, "_banner_check_timer"):
            self._banner_check_timer = QTimer()
            self._banner_check_timer.setSingleShot(True)
            self._banner_check_timer.setInterval(_BANNER_CHECK_MS)
            self._banner_check_timer.timeout.connect(self._update_runtime_banners)
        self._banner_check_timer.start()

    def _update_runtime_banners(self) -> None:
        """Show or hide the runtime banner for each script editor.

        JavaScript always runs in Deno; the banner is shown when no valid
        Deno binary is available (PATH, managed download, or custom path).
        Python editors are never given this Deno prompt.
        """
        if not getattr(self, "_scripts_editor_materialized", True):
            return
        for editor, banner in (
            (self._pre_request_edit, self._pre_runtime_banner),
            (self._test_script_edit, self._test_runtime_banner),
        ):
            lang = editor.language
            if lang != "javascript":
                banner.setVisible(False)
                continue
            dp = RuntimeSettings.deno_path()
            st = RuntimeSettings.validate_deno(dp)
            banner.setVisible(not st["available"])

    def _emit_open_scripting_settings(self) -> None:
        """Ask the main window to open Settings on the Scripting page."""
        self.open_scripting_settings_requested.emit()  # type: ignore[attr-defined]

    def _on_deno_installed(self) -> None:
        """Re-check Deno and hide the banners if the install succeeded."""
        self._update_runtime_banners()
