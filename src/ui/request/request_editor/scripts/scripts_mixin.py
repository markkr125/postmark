"""Scripts tab mixin — dual pre-request / test script editors."""

from __future__ import annotations

import json
from functools import partial
from typing import Any, Literal, cast

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtWidgets import QFrame, QSplitter, QToolButton, QVBoxLayout, QWidget
from shiboken6 import Shiboken

from database.models.collections.collection_query_repository import get_script_chain
from services.script_service import normalize_disabled_inherited
from services.script_version_service import ScriptVersionService
from services.scripting.context import normalize_events as _normalize_events
from ui.request.request_editor.scripts.debug_metadata_persist import _DebugMetadataPersistMixin
from ui.request.request_editor.scripts.inherited_banner import InheritedScriptsBanner
from ui.request.request_editor.scripts.script_editor_pane import (
    ScriptEditorPane,
    ScriptEditorPaneOptions,
)
from ui.request.request_editor.scripts.script_language import code_to_display, normalise_script_code
from ui.widgets.code_editor import CodeEditorWidget

_VERSION_CAPTURE_MS = 2000  # Debounce delay (ms) for version capture.
_AUTO_SAVE_CAPTURE_MS = 500  # Aggressive capture interval when auto-save enabled.
_BANNER_CHECK_MS = 800  # Debounce delay (ms) for runtime banner re-check.

# QSettings keys.
_SETTINGS_KEY_AUTO_SAVE_OVERRIDES = "scripts/auto_save_overrides"
_SETTINGS_KEY_AUTO_SAVE_DEFAULT = "scripting/auto_save_default"

# Full-width divider overlay (see ``_refresh_script_split_full_width_line``).
_SCRIPT_SPLIT_FULL_WIDTH_LINE_HEIGHT = 1
_SCRIPT_SPLIT_FULL_WIDTH_LINE_TOP_MARGIN = 5


class _ScriptsMixin(_DebugMetadataPersistMixin):
    """Mixin building and managing pre-request / test script editors."""

    # Host flag: request editors want the inherited-scripts banner; folder
    # editors do not (folders *are* the inherited chain for their descendants).
    _inherited_banners_supported: bool = True
    # "request" | "folder" — folder script panels omit live-response controls.
    _script_output_host_kind: str = "request"

    # -- Individual tab builders ---------------------------------------

    def _build_pre_request_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Pre-request Script tab contents."""
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

        self._pre_script_lang_auto = True
        if not hasattr(self, "_run_buttons"):
            self._run_buttons = {}
        if not hasattr(self, "_run_all_buttons"):
            self._run_all_buttons = {}
        if not hasattr(self, "_debug_buttons"):
            self._debug_buttons = {}
        if not hasattr(self, "_debug_controls"):
            self._debug_controls = {}
        if not hasattr(self, "_auto_save_checkboxes"):
            self._auto_save_checkboxes = []
            self._auto_save_enabled = True
        if not hasattr(self, "_save_buttons"):
            self._save_buttons = {}

        opts = ScriptEditorPaneOptions(
            script_type="pre_request",
            host_kind=cast(
                Literal["request", "folder", "local_script"], self._script_output_host_kind
            ),
            placeholder="Script to run before the request is sent\u2026",
            show_inherited_banner=self._inherited_banners_supported,
            show_run_all=True,
            use_host_version_timer=True,
        )
        self._pre_pane = ScriptEditorPane(
            opts,
            inherited_banner=self._pre_inherited_banner,
            parent=cast(QWidget, self),
        )
        self._pre_pane.content_changed.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._pre_pane.content_changed.connect(self._schedule_version_capture)
        host = cast(Any, self)
        if hasattr(host, "save_requested"):
            self._pre_pane.save_requested.connect(host.save_requested.emit)
        self._pre_pane.open_scripting_settings_requested.connect(self._emit_open_scripting_settings)
        if hasattr(host, "debug_step_requested"):
            self._pre_pane.debug_step_requested.connect(host.debug_step_requested.emit)
        self._pre_pane.run_all_callback = partial(self._run_all_inline_script, "pre_request")
        self._pre_pane._history_btn.clicked.connect(
            partial(self._open_version_history, "pre_request")
        )
        self._pre_pane._auto_save_cb.toggled.connect(self._on_auto_save_toggled)
        self._auto_save_checkboxes.append(self._pre_pane._auto_save_cb)

        self._pre_request_edit = self._pre_pane.editor
        self._pre_search_bar = self._pre_pane.search_bar
        self._pre_runtime_banner = self._pre_pane.runtime_banner
        self._pre_output_panel = self._pre_pane.output_panel
        self._pre_script_splitter = self._pre_pane.splitter
        self._pre_lang_menu_btn = self._pre_pane._lang_menu_btn
        self._pre_history_btn = self._pre_pane._history_btn
        self._pre_snippets_btn = self._pre_pane._snippets_btn
        self._pre_status_ln_lbl = self._pre_pane._status_ln_lbl
        self._pre_status_chars_lbl = self._pre_pane._status_chars_lbl
        self._run_buttons["pre_request"] = self._pre_pane._run_btn
        self._run_all_buttons["pre_request"] = self._pre_pane._run_all_btn
        self._debug_buttons["pre_request"] = self._pre_pane._debug_btn
        self._debug_controls["pre_request"] = self._pre_pane.debug_controls
        self._save_buttons["pre_request"] = self._pre_pane._save_btn

        self._pre_runtime_banner.download_completed.connect(self._on_deno_installed)
        self._ensure_version_capture_timer()
        self._connect_script_splitter_vis_hooks()
        parent_layout.addWidget(self._pre_pane, 1)

    def _build_test_script_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Post-response Script tab contents."""
        if self._inherited_banners_supported:
            self._test_inherited_banner = InheritedScriptsBanner(script_type="test")
            self._test_inherited_banner.setVisible(False)
            self._test_inherited_banner.view_chain_requested.connect(
                partial(self._open_inherited_chain_drawer, "test")
            )
        else:
            self._test_inherited_banner = None  # type: ignore[assignment]

        self._test_script_lang_auto = True
        opts = ScriptEditorPaneOptions(
            script_type="test",
            host_kind=cast(
                Literal["request", "folder", "local_script"], self._script_output_host_kind
            ),
            placeholder="Script to run after the response is received\u2026",
            show_inherited_banner=self._inherited_banners_supported,
            show_run_all=True,
            enable_test_gutter=True,
            use_host_version_timer=True,
        )
        self._test_pane = ScriptEditorPane(
            opts,
            inherited_banner=self._test_inherited_banner,
            parent=cast(QWidget, self),
        )
        self._test_pane.content_changed.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._test_pane.content_changed.connect(self._schedule_version_capture)
        host = cast(Any, self)
        if hasattr(host, "save_requested"):
            self._test_pane.save_requested.connect(host.save_requested.emit)
        self._test_pane.open_scripting_settings_requested.connect(
            self._emit_open_scripting_settings
        )
        if hasattr(host, "debug_step_requested"):
            self._test_pane.debug_step_requested.connect(host.debug_step_requested.emit)
        self._test_pane.run_all_callback = partial(self._run_all_inline_script, "test")
        self._test_pane._history_btn.clicked.connect(partial(self._open_version_history, "test"))
        self._test_pane._auto_save_cb.toggled.connect(self._on_auto_save_toggled)
        self._auto_save_checkboxes.append(self._test_pane._auto_save_cb)

        def _live_run(**kwargs: Any) -> None:
            main = cast(Any, self).window()
            start_live = getattr(main, "run_post_response_script_with_live_response", None)
            if callable(start_live):
                start_live(editor=cast(Any, self), **kwargs)
            else:
                kwargs["panel"].show_error("Could not run with live response in this context.")

        self._test_pane.live_response_run_callback = _live_run

        self._test_script_edit = self._test_pane.editor
        self._test_search_bar = self._test_pane.search_bar
        self._test_runtime_banner = self._test_pane.runtime_banner
        self._test_output_panel = self._test_pane.output_panel
        self._test_script_splitter = self._test_pane.splitter
        self._test_lang_menu_btn = self._test_pane._lang_menu_btn
        self._test_history_btn = self._test_pane._history_btn
        self._test_snippets_btn = self._test_pane._snippets_btn
        self._test_status_ln_lbl = self._test_pane._status_ln_lbl
        self._test_status_chars_lbl = self._test_pane._status_chars_lbl
        self._run_buttons["test"] = self._test_pane._run_btn
        self._run_all_buttons["test"] = self._test_pane._run_all_btn
        self._debug_buttons["test"] = self._test_pane._debug_btn
        self._debug_controls["test"] = self._test_pane.debug_controls
        self._save_buttons["test"] = self._test_pane._save_btn

        self._test_runtime_banner.download_completed.connect(self._on_deno_installed)
        self._connect_script_splitter_vis_hooks()
        parent_layout.addWidget(self._test_pane, 1)

    def _refresh_pm_test_gutter_markers(self) -> None:
        """Update per-line ``pm.test`` markers in the post-response editor gutter."""
        if not getattr(self, "_scripts_editor_materialized", True):
            return
        from services.scripting.engine import find_pm_tests, find_top_level_statement_lines

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
        self._wire_deferred_script_lsp()

    def _wire_deferred_script_lsp(self) -> None:
        """Connect sub-tab LSP deferral once both script editors exist (request + folder)."""
        if getattr(self, "_deferred_script_lsp_wired", False):
            return
        if not hasattr(self, "_pre_request_edit") or not hasattr(self, "_test_script_edit"):
            return
        sub_tabs = getattr(self, "_scripts_sub_tabs", None)
        if sub_tabs is None:
            return
        self._deferred_script_lsp_wired = True
        sub_tabs.currentChanged.connect(self._on_scripts_sub_tab_lsp)
        self._pre_request_edit.set_lsp_attach_deferred(True)
        self._test_script_edit.set_lsp_attach_deferred(True)
        self._sync_active_script_pane_lsp()

    def _is_scripts_section_active(self) -> bool:
        """True when the host's top-level Scripts section tab is selected."""
        tabs = getattr(self, "_tabs", None)
        scripts_tab = getattr(self, "_scripts_tab", None)
        if tabs is None or scripts_tab is None:
            return True
        return bool(tabs.currentIndex() == tabs.indexOf(scripts_tab))

    def _on_scripts_sub_tab_lsp(self, index: int) -> None:
        """Attach LSP only to the visible pre-request / post-response script editor."""
        _ = index
        self._sync_active_script_pane_lsp()

    def _sync_active_script_pane_lsp(self) -> None:
        """Defer LSP on the hidden script sub-pane; warm only the visible language bucket."""
        if not getattr(self, "_scripts_editor_materialized", False):
            return
        sub = getattr(self, "_scripts_sub_tabs", None)
        if sub is None or not hasattr(self, "_pre_request_edit"):
            return
        if not self._is_scripts_section_active():
            self._pre_request_edit.set_lsp_attach_deferred(True)
            self._test_script_edit.set_lsp_attach_deferred(True)
            return
        idx = sub.currentIndex()
        self._pre_request_edit.set_lsp_attach_deferred(idx != 0)
        self._test_script_edit.set_lsp_attach_deferred(idx != 1)

    def _on_script_splitter_context_shown(self, *_args: object) -> None:
        """Sub-tab or top-level section changed; refresh split when Scripts is shown."""
        self._sync_active_script_pane_lsp()
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
        """Restore the default editor/output split if the output pane is collapsed."""
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane.ensure_output_pane_open()

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
        # Debug bar + variable inspector reflow the scripts tab one frame later.
        QTimer.singleShot(120, self._refresh_script_split_full_width_line)

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
        if not Shiboken.isValid(self):
            return False
        tabs = getattr(self, "_tabs", None)
        scripts_tab = getattr(self, "_scripts_tab", None)
        if tabs is None or scripts_tab is None:
            return False
        if not Shiboken.isValid(tabs) or not Shiboken.isValid(scripts_tab):
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
        if not Shiboken.isValid(self):
            return
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
        y = seam.y() + _SCRIPT_SPLIT_FULL_WIDTH_LINE_TOP_MARGIN
        split_top = splitter.mapTo(host, QPoint(0, 0)).y()
        if y < split_top + 24:
            line.hide()
            return
        # Span the host's full width so the seam matches the request/response
        # splitter line; splitter.geometry() is inset by tab chrome + root margins.
        line.setGeometry(0, y, host_w, lh)
        line.show()
        line.raise_()

    def _ensure_version_capture_timer(self) -> None:
        """Create the shared debounce timer for request/folder script versions."""
        if hasattr(self, "_version_capture_timer"):
            return
        initial_ms = _AUTO_SAVE_CAPTURE_MS if self._auto_save_enabled else _VERSION_CAPTURE_MS
        self._version_capture_timer = QTimer()
        self._version_capture_timer.setSingleShot(True)
        self._version_capture_timer.setInterval(initial_ms)
        self._version_capture_timer.timeout.connect(self._capture_script_versions)

    def _script_lang_auto(self, script_type: Literal["pre_request", "test"]) -> bool:
        """Return whether *script_type* uses automatic language detection."""
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        return pane._lang_auto

    def _set_script_lang_auto(
        self, script_type: Literal["pre_request", "test"], value: bool
    ) -> None:
        """Enable or disable automatic language detection for *script_type*."""
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane._lang_auto = value
        if script_type == "pre_request":
            self._pre_script_lang_auto = value
        else:
            self._test_script_lang_auto = value

    def _sync_lang_menu_button_text(self, editor: CodeEditorWidget, btn: QToolButton) -> None:
        """Refresh the status-bar language button label from *editor*."""
        btn.setText(code_to_display(editor.language))

    def _on_script_text_for_auto_lang(self, script_type: Literal["pre_request", "test"]) -> None:
        """Restart debounced auto language detection when script text changes."""
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane._on_script_text_for_auto_lang()

    def _apply_auto_script_language(self, script_type: Literal["pre_request", "test"]) -> None:
        """Apply heuristics to *editor* when in automatic language mode."""
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane._apply_auto_script_language()

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
                self._pre_pane._sync_lang_menu_button_text()
                self._test_pane._sync_lang_menu_button_text()
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
        self._pre_pane._sync_lang_menu_button_text()
        self._test_pane._sync_lang_menu_button_text()
        self._refresh_snippets_button("pre_request")
        self._refresh_snippets_button("test")

        # Restore per-entity auto-save preference
        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if hasattr(self, "_pre_pane"):
            self._pre_pane.set_version_owner(
                request_id=request_id,
                collection_id=collection_id,
            )
            self._test_pane.set_version_owner(
                request_id=request_id,
                collection_id=collection_id,
            )
        self._restore_auto_save_state()
        self._refresh_inherited_banners()
        self._refresh_pm_test_gutter_markers()
        if isinstance(scripts, dict):
            self._apply_debug_from_scripts_raw(scripts)

    def _get_scripts_data(self) -> dict[str, str | int | list | bool | None] | None:
        """Build the scripts dict from the editor contents."""
        pre = self._pre_request_edit.toPlainText()
        test = self._test_script_edit.toPlainText()
        has_body = bool(pre or test)
        rid = getattr(self, "_request_id", None)
        disabled: list[dict[str, int | str]] = []
        if rid is not None:
            disabled = normalize_disabled_inherited(self._disabled_inherited)

        data: dict[str, str | int | list | bool | None] | None = None
        if not has_body and not disabled:
            data = None
        elif not has_body and disabled:
            data = {"disabled_inherited": disabled}
        else:
            pre_lang = self._pre_request_edit.language
            test_lang = self._test_script_edit.language
            data = {
                "pre_request": pre or None,
                "test": test or None,
                "pre_language": pre_lang,
                "test_language": test_lang,
                "language": pre_lang,  # backward compat
            }
            if disabled:
                data["disabled_inherited"] = disabled
        return self.merge_debug_into_scripts_output(data)

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
        self._pre_pane._sync_lang_menu_button_text()
        self._test_pane._sync_lang_menu_button_text()
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
        from ui.request.request_editor.scripts.inherited_chain_drawer import InheritedChainDrawer

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
        """Return whether scripts tab has text, disable entries, or persisted debug."""
        if self._get_scripts_data() is not None:
            return True
        return bool(
            self._pre_request_edit.toPlainText().strip()
            or self._test_script_edit.toPlainText().strip()
            or (getattr(self, "_request_id", None) is not None and self._disabled_inherited)
        )

    # -- Inline script execution ----------------------------------------

    def _run_inline_script(self, script_type: str, *, script_text: str | None = None) -> None:
        """Run the current script inline and display results."""
        ensure_scripts = getattr(self, "_ensure_scripts_editors", None)
        if callable(ensure_scripts):
            ensure_scripts()
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane.run(script_text=script_text)

    def _run_all_inline_script(self, script_type: str) -> None:
        """Run the inherited chain plus the current editor inline.

        Order matches the runtime pipeline: pre-request top-down
        (collection → folder → request), test bottom-up (request →
        folder → collection). When no inheritance exists (draft tab or
        request without parents), falls back to :meth:`_run_inline_script`.
        """
        from services.scripting import ScriptEntry
        from ui.request.request_editor.scripts.script_run_worker import build_inline_context

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
        ensure_scripts = getattr(self, "_ensure_scripts_editors", None)
        if callable(ensure_scripts):
            ensure_scripts()
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane.debug(script_text=script_text)

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
        self._pre_pane.sync_auto_save_from_host(checked)
        self._test_pane.sync_auto_save_from_host(checked)
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
        import database.database as db_mod

        if db_mod._SessionLocal is None:
            return
        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return
        self._pre_pane.set_version_owner(request_id=request_id, collection_id=collection_id)
        self._test_pane.set_version_owner(request_id=request_id, collection_id=collection_id)
        self._pre_pane.capture_version()
        self._test_pane.capture_version()

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
        pane = self._pre_pane if script_type == "pre_request" else self._test_pane
        pane._refresh_snippets_button()

    def _open_version_history(self, script_type: str = "pre_request") -> None:
        """Open the version history dialog for the current request."""
        from ui.request.request_editor.scripts.version_history import VersionHistoryDialog

        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return

        editor = self._pre_request_edit if script_type == "pre_request" else self._test_script_edit
        dlg = VersionHistoryDialog(
            request_id=request_id,
            collection_id=collection_id,
            current_pre=self._pre_pane.editor.toPlainText(),
            current_test=self._test_pane.editor.toPlainText(),
            language=editor.language,
            initial_tab=0 if script_type == "pre_request" else 1,
            parent=editor,
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
        self._pre_pane._schedule_banner_check()
        self._test_pane._schedule_banner_check()

    def _update_runtime_banners(self) -> None:
        """Show or hide the runtime banner for each script editor."""
        if not getattr(self, "_scripts_editor_materialized", True):
            return
        self._pre_pane._update_runtime_banner()
        self._test_pane._update_runtime_banner()

    def _emit_open_scripting_settings(self) -> None:
        """Ask the main window to open Settings on the Scripting page."""
        self.open_scripting_settings_requested.emit()  # type: ignore[attr-defined]

    def _on_deno_installed(self) -> None:
        """Re-check Deno and hide the banners if the install succeeded."""
        self._update_runtime_banners()
