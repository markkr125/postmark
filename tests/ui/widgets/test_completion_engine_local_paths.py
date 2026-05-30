"""CompletionEngine tests: pm.require('local:…') and ESM relative import paths."""

from __future__ import annotations

from unittest.mock import patch

from ui.widgets.code_editor.completion.engine import CompletionEngine
from ui.widgets.code_editor.completion.path_completions import is_esm_import_context


class TestLocalRequireCompletions:
    """Autocomplete for ``pm.require('local:…')`` paths."""

    def test_js_local_require_lists_matching_paths(self) -> None:
        """Typing inside a local require string offers virtual paths."""
        from database.models.local_scripts.local_script_repository import (
            create_folder,
            create_script,
        )

        root = create_folder("auth")
        create_script(root.id, "helper", language="javascript")

        engine = CompletionEngine("javascript")
        items = engine.complete('const x = pm.require("local:auth/h')
        labels = {item.label for item in items}
        assert "auth/helper.js" in labels

    def test_open_require_string_offers_local_paths(self) -> None:
        """Right after ``pm.require('`` suggest paths with a ``local:`` insert prefix."""
        from database.models.local_scripts.local_script_repository import (
            create_folder,
            create_script,
        )

        root = create_folder("auth")
        create_script(root.id, "helper", language="javascript")

        engine = CompletionEngine("javascript")
        assert engine.is_local_require_completion_context("pm.require('")
        items = engine.complete("pm.require('")
        helper = next(i for i in items if i.label == "auth/helper.js")
        assert helper.insert_text == "local:auth/helper.js"

    def test_npm_require_string_is_not_local_context(self) -> None:
        """``pm.require('npm:`` must not offer local script paths."""
        engine = CompletionEngine("javascript")
        assert not engine.is_local_require_completion_context("pm.require('npm:lodash")

    def test_local_require_works_with_document_text_multiline(self) -> None:
        """``pm.require`` on a prior line still completes on the string line."""
        from database.models.local_scripts.local_script_repository import (
            create_folder,
            create_script,
        )

        root = create_folder("lib")
        create_script(root.id, "helper", language="javascript")

        engine = CompletionEngine("javascript")
        doc = "const x = pm.require(\n  'local:lib/h"
        assert engine.is_local_require_completion_context(doc)
        items = engine.complete(doc)
        assert any(item.label == "lib/helper.js" for item in items)

    def test_local_require_does_not_fall_back_to_keywords(self) -> None:
        """Inside ``local:`` with no scripts, completions stay empty (not ``const``)."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.require('local:")
        assert items == []

    def test_python_local_require_lists_py_paths(self) -> None:
        """Python editor only suggests ``.py`` local scripts."""
        from database.models.local_scripts.local_script_repository import (
            create_folder,
            create_script,
        )

        root = create_folder("pkg")
        create_script(root.id, "mod", language="python")
        create_script(root.id, "util", language="javascript")

        engine = CompletionEngine("python")
        items = engine.complete("pm.require('local:")
        labels = {item.label for item in items}
        assert labels == {"pkg/mod.py"}


class TestEsmImportCompletions:
    """Autocomplete for relative ESM import specifiers in local scripts."""

    def test_is_esm_import_context_javascript(self) -> None:
        assert is_esm_import_context("import x from './", "javascript") is True
        assert is_esm_import_context("import x from './", "python") is False

    def test_complete_esm_import_sibling_paths(self) -> None:
        paths = [
            "home2/test.js",
            "home2/mapper.js",
            "home2/sub/deep.ts",
        ]

        with (
            patch(
                "services.scripting.local_scripts_project.mirror.rel_path_for_script_id",
                return_value="home2/test.js",
            ),
            patch(
                "services.local_script_service.LocalScriptService.list_virtual_paths",
                return_value=paths,
            ),
        ):
            engine = CompletionEngine("javascript")
            engine._local_script_id = 1
            items = engine.complete("import x from './ma")
        assert items
        assert all(it.insert_text.startswith("./") for it in items)
        labels = {it.label for it in items}
        assert "./mapper.js" in labels
