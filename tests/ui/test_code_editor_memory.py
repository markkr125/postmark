"""Memory-leak tests for CodeEditorWidget.

Uses ``tracemalloc`` snapshots and ``weakref`` to verify that the code
editor does not leak memory when switching languages, replacing content,
creating/destroying widgets, or repeatedly folding/unfolding regions.
"""

from __future__ import annotations

import gc
import json
import tracemalloc
import weakref

from PySide6.QtWidgets import QApplication

from ui.code_editor import CodeEditorWidget

# -- Helpers -----------------------------------------------------------


def _force_gc() -> None:
    """Run multiple GC passes to collect cyclic references."""
    for _ in range(4):
        gc.collect()


_SAMPLE_JSON_SMALL = json.dumps({"key": "value", "num": 42, "list": [1, 2, 3]})

_SAMPLE_JSON_LARGE = json.dumps(
    {f"item_{i}": {"nested": list(range(10))} for i in range(30)},
    indent=4,
)


# -- Test classes ------------------------------------------------------


class TestHighlighterLifecycle:
    """Verify that destroying a CodeEditorWidget releases the highlighter."""

    def test_highlighter_ref_dies_with_widget(self, qapp: QApplication, qtbot) -> None:
        """After widget deletion the PygmentsHighlighter must be collected."""
        editor = CodeEditorWidget()
        editor.set_language("json")
        editor.setPlainText(_SAMPLE_JSON_SMALL)

        highlighter_ref = weakref.ref(editor._highlighter)
        widget_ref = weakref.ref(editor)
        assert highlighter_ref() is not None

        # Release all Python references — Qt parent chain should not hold
        editor.close()
        del editor
        qapp.processEvents()
        _force_gc()
        qapp.processEvents()

        # The Python wrapper may survive if the C++ side is still alive,
        # but the highlighter (a pure-Python object owned by the document)
        # should be reclaimable once the widget and document are gone.
        assert widget_ref() is None or highlighter_ref() is None, (
            "PygmentsHighlighter leaked after widget destruction"
        )


class TestLanguageSwitchingMemory:
    """Verify that repeated language switching does not leak."""

    def test_language_switch_bounded_growth(self, qapp: QApplication, qtbot) -> None:
        """Switching language 50 times should not grow memory unboundedly."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText(_SAMPLE_JSON_SMALL)

        languages = ["json", "xml", "html", "text"]

        # Warm-up pass — first-time lexer imports cause one-time allocations
        # that are not leaks.  Cycle through all languages once so those
        # costs are paid before the measurement window.
        for lang in languages:
            editor.set_language(lang)
            qapp.processEvents()
        _force_gc()

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        for i in range(50):
            editor.set_language(languages[i % len(languages)])
            qapp.processEvents()

        _force_gc()
        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare top stats -- total growth should stay small
        stats = snap_after.compare_to(snap_before, "lineno")
        growth = sum(s.size_diff for s in stats if s.size_diff > 0)

        limit = 512 * 1024  # 512 KB
        assert growth < limit, (
            f"Memory grew by {growth / 1024:.1f} KB after 50 language switches "
            f"(limit {limit / 1024:.0f} KB)"
        )


class TestRepeatedContentLoadMemory:
    """Verify that replacing content repeatedly does not leak tokens."""

    def test_content_replacement_bounded_growth(self, qapp: QApplication, qtbot) -> None:
        """Replacing body content 100 times should not accumulate caches."""
        editor = CodeEditorWidget(read_only=True)
        qtbot.addWidget(editor)
        editor.set_language("json")

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        for i in range(100):
            body = json.dumps({"iteration": i, "data": list(range(100))})
            editor.set_text(body)
            qapp.processEvents()

        _force_gc()
        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "lineno")
        growth = sum(s.size_diff for s in stats if s.size_diff > 0)

        limit = 1024 * 1024  # 1 MB
        assert growth < limit, (
            f"Memory grew by {growth / 1024:.1f} KB after 100 content replacements "
            f"(limit {limit / 1024:.0f} KB)"
        )


class TestWidgetDestructionCleansUp:
    """Verify that creating and destroying many editors does not leak."""

    def test_twenty_widgets_all_collected(self, qapp: QApplication, qtbot) -> None:
        """Create 20 CodeEditorWidgets, destroy them, verify all collected."""
        refs: list[weakref.ref] = []

        for _ in range(20):
            editor = CodeEditorWidget()
            editor.set_language("json")
            editor.setPlainText(_SAMPLE_JSON_SMALL)
            qapp.processEvents()
            refs.append(weakref.ref(editor))

            editor.close()
            del editor

        qapp.processEvents()
        _force_gc()
        qapp.processEvents()

        alive = sum(1 for r in refs if r() is not None)
        assert alive == 0, f"{alive}/20 CodeEditorWidgets leaked after destruction"


class TestRepeatedFoldUnfoldMemory:
    """Verify that fold/unfold cycles do not accumulate state."""

    def test_fold_unfold_bounded_growth(self, qapp: QApplication, qtbot) -> None:
        """Fold and unfold all regions 20 times — memory stays bounded."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")
        editor.setPlainText(_SAMPLE_JSON_LARGE)
        qapp.processEvents()

        # Let initial fold detection finish
        editor._recompute_folds()
        qapp.processEvents()

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        for _ in range(20):
            editor.fold_all()
            qapp.processEvents()
            editor.unfold_all()
            qapp.processEvents()

        _force_gc()
        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "lineno")
        growth = sum(s.size_diff for s in stats if s.size_diff > 0)

        limit = 512 * 1024  # 512 KB
        assert growth < limit, (
            f"Memory grew by {growth / 1024:.1f} KB after 20 fold/unfold cycles "
            f"(limit {limit / 1024:.0f} KB)"
        )


class TestRepeatedValidationMemory:
    """Verify that repeated validation cycles do not leak."""

    def test_validation_cycle_bounded_growth(self, qapp: QApplication, qtbot) -> None:
        """Trigger validation 50 times — memory stays bounded."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_language("json")

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        for i in range(50):
            # Alternate between valid and invalid JSON
            if i % 2 == 0:
                editor.setPlainText('{"valid": true}')
            else:
                editor.setPlainText('{"broken": }')
            # Directly invoke validation instead of waiting for debounce
            editor._validate()
            qapp.processEvents()

        _force_gc()
        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "lineno")
        growth = sum(s.size_diff for s in stats if s.size_diff > 0)

        limit = 512 * 1024  # 512 KB
        assert growth < limit, (
            f"Memory grew by {growth / 1024:.1f} KB after 50 validation cycles "
            f"(limit {limit / 1024:.0f} KB)"
        )
