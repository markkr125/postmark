"""Language switching mixin for :class:`CodeEditorWidget`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ui.widgets.code_editor import editor_lsp_glue as _lsp

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPlainTextEdit

    _LanguageBase = QPlainTextEdit
else:
    _LanguageBase = object


class _LanguageMixin(_LanguageBase):
    """Syntax mode, highlighter, folding, and LSP attachment on language change."""

    _language: str
    _script_module_format: str
    _read_only: bool
    _fold_regions: dict[int, int]
    _collapsed_folds: set[int]
    _sorted_folds: list[tuple[int, int, int]]
    _active_fold_start: int
    _highlighter: Any
    _completion_engine: Any
    _fold_timer: Any
    _validate_timer: Any

    if TYPE_CHECKING:

        def apply_validation_errors(self, errors: list[Any]) -> None: ...
        def clear_inline_log_annotations(self) -> None: ...
        def _recompute_folds(self) -> None: ...

    @property
    def language(self) -> str:
        """Return the active language."""
        return self._language

    @property
    def script_module_format(self) -> str:
        """Return ``esm`` or ``commonjs`` for local-script editors (default ``esm``)."""
        return self._script_module_format

    def set_script_module_format(self, module_format: str) -> None:
        """Set module format for local CJS scripts (skips ESM lint when ``commonjs``)."""
        self._script_module_format = (module_format or "esm").strip().lower()

    def refresh_script_module_format(self, module_format: str) -> None:
        """Update module format and re-run legacy validation (e.g. after tree rename)."""
        self.set_script_module_format(module_format)
        if not self._read_only and not self.isReadOnly():
            self._validate_timer.start()

    def set_language(self, language: str) -> None:
        """Switch syntax highlighting, folding, and validation language."""
        lang = language.lower()
        if lang == self._language:
            return
        prev_lang = self._language
        self._language = lang
        self._highlighter.set_language(lang)
        self._completion_engine.set_language(lang)
        adapter = getattr(self, "_lsp_adapter", None)
        # Local-script editors fully detach + re-attach on every language change
        # (swap_language is refused for them), so the JS↔TS "same family" swap
        # optimisation does not apply — their stale diagnostics must be cleared,
        # otherwise old problems/squiggles survive a TS→JS switch.
        same_family = (
            adapter is not None
            and getattr(self, "_local_script_id", None) is None
            and prev_lang in ("javascript", "typescript")
            and lang in ("javascript", "typescript")
        )
        if not same_family:
            self.apply_validation_errors([])
        self.clear_inline_log_annotations()
        self._fold_regions = {}
        self._collapsed_folds = set()
        self._sorted_folds = []
        self._active_fold_start = -1
        if not self._read_only:
            self._fold_timer.start()
            self._validate_timer.start()
        else:
            self._recompute_folds()
        _lsp.sync_script_lsp_attachment(cast(Any, self))
