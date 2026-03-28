"""Completion engine that resolves dot-path context to completions.

The engine maintains a reference to the appropriate language schema
(JS or Python) and resolves the text before the cursor to produce a
list of :class:`CompletionItem` results.  It also handles ``{{``
variable completions from the editor's variable map.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from ui.widgets.code_editor.completion.schema import (
    JS_GLOBALS,
    JS_SCHEMA,
    PY_GLOBALS,
    PY_SCHEMA,
    SchemaNode,
)

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

# Regex to extract the receiver path before the cursor.
# e.g. "pm.response." → ["pm", "response"]
_DOT_PATH_RE = re.compile(r"([\w.]+)\.\s*$")

# Regex to detect {{ trigger for variable completions.
_VAR_TRIGGER_RE = re.compile(r"\{\{\s*([\w]*)$")

# Regex to detect pm.variables.get(" or pm.environment.get(" patterns.
_VAR_STRING_RE = re.compile(
    r"pm\.(?:variables|environment|collectionVariables|globals"
    r"|collection_variables)"
    r'\.get\(\s*["\'](\w*)$'
)

# Regex for JS variable assignments:  let/const/var x = pm.something
_JS_ASSIGN_RE = re.compile(r"(?:let|const|var)\s+(\w+)\s*=\s*([\w.]+(?:\(\))?)\s*;?")

# Regex for Python variable assignments:  x = pm.something
_PY_ASSIGN_RE = re.compile(r"^(\w+)\s*=\s*([\w.]+(?:\(\))?)\s*$", re.MULTILINE)


class CompletionItem(NamedTuple):
    """A single completion suggestion."""

    label: str  # display text (e.g. "response")
    kind: str  # "property" | "method" | "object" | "variable"
    type_str: str  # short type/return label (e.g. "number")
    doc: str  # one-line description
    signature: str  # parameter signature for methods
    insert_text: str  # text to insert (usually same as label)


class CompletionEngine:
    """Resolve text context to a list of completion items.

    Parameters:
        language: The script language (``"javascript"`` or ``"python"``).
    """

    def __init__(self, language: str = "javascript") -> None:
        """Initialise the engine with a language schema."""
        self._language = language.lower()
        self._schema = JS_SCHEMA if self._language == "javascript" else PY_SCHEMA
        self._variable_map: dict[str, VariableDetail] = {}
        self._inferred_types: dict[str, str] = {}  # var_name → dot-path

    @property
    def language(self) -> str:
        """Return the active language."""
        return self._language

    def set_language(self, language: str) -> None:
        """Switch to a different language schema."""
        lang = language.lower()
        if lang == self._language:
            return
        self._language = lang
        self._schema = JS_SCHEMA if lang == "javascript" else PY_SCHEMA

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable map for ``{{`` completions."""
        self._variable_map = variables

    def scan_assignments(self, full_text: str) -> None:
        """Scan the full editor text for variable assignments.

        Extracts ``let x = pm.response.json()`` style assignments and
        maps the variable name to the dot-path of the right-hand side.
        This enables dot completions on user-defined variables.
        """
        pattern = _JS_ASSIGN_RE if self._language == "javascript" else _PY_ASSIGN_RE
        self._inferred_types.clear()
        for m in pattern.finditer(full_text):
            var_name = m.group(1)
            rhs = m.group(2)
            # Strip trailing () — we want the path, not the call.
            if rhs.endswith("()"):
                rhs = rhs[:-2]
            self._inferred_types[var_name] = rhs

    def complete(self, text_before_cursor: str) -> list[CompletionItem]:
        """Return completions for the text preceding the cursor.

        Checks, in order:
        1. ``{{`` variable trigger.
        2. ``pm.variables.get("`` string argument trigger.
        3. Dot-path API completions.

        Returns an empty list if no completions match.
        """
        # 1. Variable completions on {{
        var_match = _VAR_TRIGGER_RE.search(text_before_cursor)
        if var_match:
            return self._variable_completions(var_match.group(1))

        # 2. Variable string argument in .get("
        str_match = _VAR_STRING_RE.search(text_before_cursor)
        if str_match:
            return self._variable_completions(str_match.group(1))

        # 3. Dot-path completions
        dot_match = _DOT_PATH_RE.search(text_before_cursor)
        if dot_match:
            return self._resolve_path(dot_match.group(1))

        return []

    def complete_prefix(self, text_before_cursor: str, prefix: str) -> list[CompletionItem]:
        """Return completions filtered by a typed prefix after the dot.

        Called as the user types more characters after the initial
        dot trigger.  *prefix* is the text typed after the dot.
        """
        items = self.complete(text_before_cursor)
        if not prefix:
            return items
        lower = prefix.lower()
        return [item for item in items if item.label.lower().startswith(lower)]

    def top_level_completions(self) -> list[CompletionItem]:
        """Return top-level completions (pm, console, and language globals)."""
        items = self._schema_to_items(self._schema)
        if self._language == "javascript":
            items.extend(self._schema_to_items(JS_GLOBALS))
        else:
            items.extend(self._schema_to_items(PY_GLOBALS))
        return items

    # -- Private helpers ------------------------------------------------

    def _resolve_path(self, path: str) -> list[CompletionItem]:
        """Walk the schema tree along *path* and return child completions.

        If the first segment is a user-defined variable with an inferred
        type, the inferred dot-path is prepended so the schema can be
        resolved correctly.
        """
        parts = path.split(".")

        # Check if the first part is an inferred variable.
        if parts[0] in self._inferred_types:
            inferred_path = self._inferred_types[parts[0]]
            expanded = inferred_path.split(".") + parts[1:]
            parts = expanded

        node: dict[str, SchemaNode] = self._schema

        for part in parts:
            if part not in node:
                return []
            entry = node[part]
            children = entry.get("children")
            if children is None:
                return []
            node = children

        return self._schema_to_items(node)

    def _variable_completions(self, prefix: str) -> list[CompletionItem]:
        """Return variable name completions filtered by *prefix*."""
        lower = prefix.lower()
        items: list[CompletionItem] = []
        for name, detail in sorted(self._variable_map.items()):
            if lower and not name.lower().startswith(lower):
                continue
            source = detail.get("source", "") if detail else ""
            value = detail.get("value", "") if detail else ""
            doc = f"{source}: {value}" if source else value
            items.append(
                CompletionItem(
                    label=name,
                    kind="variable",
                    type_str="string",
                    doc=doc,
                    signature="",
                    insert_text=name,
                )
            )
        return items

    @staticmethod
    def _schema_to_items(schema: dict[str, SchemaNode]) -> list[CompletionItem]:
        """Convert a schema dict level to a list of CompletionItems."""
        items: list[CompletionItem] = []
        for name, node in sorted(schema.items()):
            items.append(
                CompletionItem(
                    label=name,
                    kind=node.get("kind", "property"),
                    type_str=node.get("type_str", ""),
                    doc=node.get("doc", ""),
                    signature=node.get("signature", ""),
                    insert_text=name,
                )
            )
        return items
