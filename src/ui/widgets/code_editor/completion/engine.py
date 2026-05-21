"""Completion engine that resolves dot-path context to completions.

The engine maintains a reference to the appropriate language schema
(JS or Python) and resolves the text before the cursor to produce a
list of :class:`CompletionItem` results.  It also handles ``{{``
variable completions from the editor's variable map.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDoc
from ui.widgets.code_editor.completion.schema import (
    JS_GLOBALS,
    JS_KEYWORDS,
    JS_SCHEMA,
    PY_GLOBALS,
    PY_KEYWORDS,
    PY_SCHEMA,
    SchemaNode,
)

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

# Regex to extract the receiver path before the cursor.
# e.g. "pm.response." → ["pm", "response"]
_DOT_PATH_RE = re.compile(r"([\w.]+)\.\s*$")

# "new ClassName(...).foo" — captures ClassName for instance-children lookup.
_NEW_INSTANCE_DOT_RE = re.compile(r"new\s+(\w+)\s*\([^()]*\)\s*\.\s*$")
_NEW_INSTANCE_PREFIX_RE = re.compile(r"new\s+(\w+)\s*\([^()]*\)\s*\.(\w+)$")

# Dot-path mid-word: "pm.v" -> base "pm", prefix "v"; "pm.variables.s" -> base "pm.variables", prefix "s"
_DOT_PATH_PREFIX_RE = re.compile(r"([\w.]+)\.(\w+)$")

# Regex to detect {{ trigger for variable completions.
_VAR_TRIGGER_RE = re.compile(r"\{\{\s*([\w]*)$")

# Regex to detect pm.variables.get(" or pm.environment.get(" patterns.
_VAR_STRING_RE = re.compile(
    r"pm\.(?:variables|environment|collectionVariables|globals"
    r"|collection_variables)"
    r'\.get\(\s*["\'](\w*)$'
)

# Cursor inside an unclosed pm.require("…") / pm.require('…') string argument.
_PM_REQUIRE_STRING_AT_CURSOR_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*(?P<q>['"])(?P<tail>[^'"]*)$""",
)

# Regex for JS variable assignments:  let/const/var x = pm.something
_JS_ASSIGN_RE = re.compile(r"(?:let|const|var)\s+(\w+)\s*=\s*([\w.]+(?:\(\))?)\s*;?")

# Regex for Python variable assignments:  x = pm.something
_PY_ASSIGN_RE = re.compile(r"^(\w+)\s*=\s*([\w.]+(?:\(\))?)\s*$", re.MULTILINE)

# Identifier being typed before the cursor (e.g. ``con`` for ``const``),
# but not after a dot (so ``pm.con`` still uses dot-path logic).
_IDENT_PREFIX_RE = re.compile(r"(?:^|[^\w.])(\w+)$")


def _find_call_open_paren(text: str) -> int | None:
    """Return the index of the ``(`` that opens the innermost unclosed call, or ``None``."""
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        c = text[i]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                return i
            depth -= 1
    return None


def _strip_simple_paren_groups(s: str) -> str:
    """Remove non-nested ``(...)`` groups (e.g. ``(value)`` in ``pm.expect(value).to``)."""
    prev = ""
    while prev != s:
        prev = s
        s = re.sub(r"\([^()]*\)", "", s)
    return s


def _split_receiver_parent_method(receiver: str) -> tuple[str, str] | None:
    """Split ``receiver`` into ``(parent_dot_path, method_name)``.

    Only the trailing dot-path identifier is considered, so leading content
    (other lines, statements, comments) is ignored.
    """
    s = _strip_simple_paren_groups(receiver.rstrip())
    m = re.search(r"([\w.]+)\.(\w+)\s*$", s)
    if not m:
        return None
    return m.group(1), m.group(2)


def _active_parameter_index(args_fragment: str) -> int:
    """Count top-level commas in *args_fragment* (cursor at end of fragment)."""
    depth = 0
    in_string: str | None = None
    escape = False
    commas = 0
    for c in args_fragment:
        if in_string:
            if escape:
                escape = False
                continue
            if c == "\\" and in_string != "`":
                escape = True
                continue
            if c == in_string:
                in_string = None
            continue
        if c in "\"'`":
            in_string = c
            continue
        if c in "([{":
            depth += 1
            continue
        if c in ")]}":
            if depth > 0:
                depth -= 1
            continue
        if c == "," and depth == 0:
            commas += 1
    return commas


class CompletionItem(NamedTuple):
    """A single completion suggestion."""

    label: str  # display text (e.g. "response")
    kind: str  # "property" | "method" | "object" | "variable" | "keyword"
    type_str: str  # short type/return label (e.g. "number")
    doc: str  # one-line description
    signature: str  # parameter signature for methods
    insert_text: str  # text to insert (usually same as label)


class CompletionEngine:
    """Resolve text context to a list of completion items.

    Parameters:
        language: The script language (``"javascript"``, ``"typescript"``, or ``"python"``).
    """

    def __init__(self, language: str = "javascript") -> None:
        """Initialise the engine with a language schema."""
        self._language = language.lower()
        self._schema = PY_SCHEMA if self._language == "python" else JS_SCHEMA
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
        self._schema = PY_SCHEMA if lang == "python" else JS_SCHEMA

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable map for ``{{`` completions."""
        self._variable_map = variables

    def scan_assignments(self, full_text: str) -> None:
        """Scan the full editor text for variable assignments.

        Extracts ``let x = pm.response.json()`` style assignments and
        maps the variable name to the dot-path of the right-hand side.
        This enables dot completions on user-defined variables.
        """
        pattern = _PY_ASSIGN_RE if self._language == "python" else _JS_ASSIGN_RE
        self._inferred_types.clear()
        for m in pattern.finditer(full_text):
            var_name = m.group(1)
            rhs = m.group(2)
            # Strip trailing () — we want the path, not the call.
            if rhs.endswith("()"):
                rhs = rhs[:-2]
            self._inferred_types[var_name] = rhs

    def _pm_require_string_tail(self, text_before_cursor: str) -> str | None:
        """Return the unclosed string tail for ``pm.require('…')`` at the cursor, or ``None``."""
        m = _PM_REQUIRE_STRING_AT_CURSOR_RE.search(text_before_cursor)
        return m.group("tail") if m is not None else None

    def is_local_require_completion_context(self, text_before_cursor: str) -> bool:
        """Return whether the cursor is inside ``pm.require`` and may complete ``local:`` paths."""
        tail = self._pm_require_string_tail(text_before_cursor)
        if tail is None:
            return False
        if not tail:
            return True
        return tail.startswith("local:")

    def local_require_path_prefix(self, text_before_cursor: str) -> str | None:
        """Return the typed path segment after ``local:`` (may be empty)."""
        tail = self._pm_require_string_tail(text_before_cursor)
        if tail is None:
            return None
        if tail.startswith("local:"):
            return tail[6:]
        return ""

    def local_require_insert_prefixes_local(self, text_before_cursor: str) -> bool:
        """Return whether accepted items must include the ``local:`` prefix."""
        tail = self._pm_require_string_tail(text_before_cursor)
        return tail is not None and not tail.startswith("local:")

    def complete(self, text_before_cursor: str) -> list[CompletionItem]:
        """Return completions for the text preceding the cursor.

        Checks, in order:
        1. ``{{`` variable trigger.
        2. ``pm.variables.get("`` string argument trigger.
        3. ``pm.require("local:…")`` local script path autocomplete.
        4. Dot-path API completions (trailing dot: full children).
        4. Dot-path with a typed segment after the last dot (e.g. ``pm.v`` narrows
           ``pm`` children; ``pm.variables.s`` narrows scope methods).

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

        # 3. Local script paths in pm.require("local:…") or pm.require('
        if self.is_local_require_completion_context(text_before_cursor):
            path_prefix = self.local_require_path_prefix(text_before_cursor) or ""
            add_local = self.local_require_insert_prefixes_local(text_before_cursor)
            return self._local_require_completions(path_prefix, prefix_local=add_local)

        # 3a. ``new ClassName().`` → instance children of ClassName.
        ni_match = _NEW_INSTANCE_DOT_RE.search(text_before_cursor)
        if ni_match:
            return self._instance_children_items(ni_match.group(1))

        # 3b. ``new ClassName().pre`` → filter instance children by prefix.
        nip_match = _NEW_INSTANCE_PREFIX_RE.search(text_before_cursor)
        if nip_match:
            cls_name = nip_match.group(1)
            prefix = nip_match.group(2).lower()
            items = self._instance_children_items(cls_name)
            if items:
                return [it for it in items if it.label.lower().startswith(prefix)]

        # 3. Dot-path completions (trailing dot: full child list)
        dot_match = _DOT_PATH_RE.search(text_before_cursor)
        if dot_match:
            return self._resolve_path(dot_match.group(1))

        # 4. Dot-path with typed prefix after dot (mid-word; avoids top-level fallback)
        typed_match = _DOT_PATH_PREFIX_RE.search(text_before_cursor)
        if typed_match:
            base = typed_match.group(1)
            prefix = typed_match.group(2).lower()
            items = self._resolve_path(base)
            if items:
                return [it for it in items if it.label.lower().startswith(prefix)]

        return []

    def _instance_children_items(self, class_name: str) -> list[CompletionItem]:
        """Return ``instance_children`` items for *class_name* in the active schema."""
        node = self._schema.get(class_name)
        if not node:
            return []
        ic = node.get("instance_children")
        if not ic:
            return []
        return self._schema_to_items(ic)

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

    def resolve_symbol(self, dot_path: str, full_source: str) -> SymbolDoc | None:
        """Return :class:`SymbolDoc` for *dot_path*, or ``None`` if unknown.

        Lookup order:

        1. Walk *dot_path* through the active schema; the last segment must
           match a child of the resolved parent.
        2. Treat the head of *dot_path* as a user-defined variable whose
           type was inferred from a ``let|const|var x = ...`` (JS) or
           ``x = ...`` (Python) assignment.
        3. Treat the head as an undeclared local — return a minimal
           :class:`SymbolDoc` so the popup can still display the name.
        """
        self.scan_assignments(full_source)
        parts = dot_path.split(".")
        if len(parts) == 1:
            head = parts[0]
            if head in self._inferred_types:
                inferred = self._inferred_types[head]
                inferred_parts = inferred.split(".")
                node = self._schema
                for p in inferred_parts:
                    if p not in node:
                        return None
                    entry = node[p]
                    children = entry.get("children")
                    if children is None:
                        return None
                    node = children
                return SymbolDoc(
                    label=head,
                    kind="variable",
                    type_str=inferred,
                    doc=f"Inferred from assignment: {inferred}",
                    signature="",
                    origin="user variable",
                )
            if head in self._schema:
                entry = self._schema[head]
                return SymbolDoc(
                    label=head,
                    kind=entry.get("kind", "object"),
                    type_str=entry.get("type_str", ""),
                    doc=entry.get("doc", ""),
                    signature=entry.get("signature", ""),
                    origin="pm API",
                )
            return SymbolDoc(
                label=head,
                kind="variable",
                type_str="",
                doc="",
                signature="",
                origin="local",
            )
        parent_path = ".".join(parts[:-1])
        leaf = parts[-1]
        items = self._resolve_path(parent_path)
        for it in items:
            if it.label == leaf:
                origin = "pm API"
                if parts[0] in self._inferred_types:
                    origin = "user variable"
                return SymbolDoc(
                    label=leaf,
                    kind=it.kind,
                    type_str=it.type_str,
                    doc=it.doc,
                    signature=it.signature,
                    origin=origin,
                )
        return None

    def find_definition_pos(self, var_name: str, full_source: str) -> int | None:
        """Return the start offset of a user binding for *var_name*.

        JavaScript: ``let|const|var var_name = ...``.  Python: ``var_name = ...``
        at the beginning of a line.  Returns ``None`` when not found.
        """
        if self._language != "python":
            pattern = re.compile(r"(?:let|const|var)\s+" + re.escape(var_name) + r"\b")
        else:
            pattern = re.compile(r"^" + re.escape(var_name) + r"\s*=", re.MULTILINE)
        m = pattern.search(full_source)
        return m.start() if m else None

    def is_linkable_symbol(self, dot_path: str, full_source: str) -> bool:
        """Return True when *dot_path* should display as a Ctrl+hover link.

        Excludes language keywords and unresolved local identifiers.  A path
        is linkable when it resolves through the active schema, has a known
        user-variable type, or its head has a discoverable definition site.
        """
        if not dot_path:
            return False
        head = dot_path.split(".", 1)[0]
        keywords = JS_KEYWORDS if self._language != "python" else PY_KEYWORDS
        if head in keywords:
            return False
        if self.find_definition_pos(head, full_source) is not None:
            return True
        sym = self.resolve_symbol(dot_path, full_source)
        if sym is None:
            return False
        return sym.origin in ("pm API", "user variable")

    def top_level_completions(self) -> list[CompletionItem]:
        """Return top-level completions (pm, console, language globals, keywords)."""
        items = self._schema_to_items(self._schema)
        if self._language != "python":
            items.extend(self._schema_to_items(JS_GLOBALS))
            items.extend(self._schema_to_items(JS_KEYWORDS))
        else:
            items.extend(self._schema_to_items(PY_GLOBALS))
            items.extend(self._schema_to_items(PY_KEYWORDS))
        return items

    def identifier_prefix(self, text_before_cursor: str) -> str:
        """Return the word being typed before the cursor, or empty string."""
        match = _IDENT_PREFIX_RE.search(text_before_cursor)
        return match.group(1) if match else ""

    def top_level_filtered(self, prefix: str) -> list[CompletionItem]:
        """Return top-level items whose label starts with *prefix* (case-insensitive)."""
        items = self.top_level_completions()
        if not prefix:
            return items
        lower = prefix.lower()
        return [i for i in items if i.label.lower().startswith(lower)]

    def resolve_call_signature(self, text_before_cursor: str) -> tuple[str, int] | None:
        """Return ``(signature, active_param_index)`` for the innermost open call, or ``None``."""
        open_idx = _find_call_open_paren(text_before_cursor)
        if open_idx is None:
            return None
        receiver = text_before_cursor[:open_idx]
        # Special case: ``new ClassName(...).method`` — look up instance_children.
        ni = re.search(r"new\s+(\w+)\s*\([^()]*\)\s*\.(\w+)\s*$", receiver)
        items: list[CompletionItem] = []
        method_name = ""
        if ni:
            items = self._instance_children_items(ni.group(1))
            method_name = ni.group(2)
        else:
            split = _split_receiver_parent_method(receiver)
            if split is None:
                return None
            parent_path, method_name = split
            items = self._resolve_path(parent_path)
        signature = ""
        for it in items:
            if it.label == method_name:
                signature = it.signature or ""
                break
        if not signature:
            return None
        args_fragment = text_before_cursor[open_idx + 1 :]
        idx = _active_parameter_index(args_fragment)
        return (signature, idx)

    def resolve_nearest_call_signature(self, text_before_cursor: str) -> tuple[str, int] | None:
        """Resolve like :meth:`resolve_call_signature`, or the last closed call on this line.

        When the cursor is not inside an unclosed ``(``, scans the current
        visual line from the right for the innermost balanced ``(...)`` and
        resolves the call as if the cursor sat just inside that ``(``,
        using the full argument text to pick the active parameter (typically
        the last argument when the cursor is past the closing ``)``).
        """
        direct = self.resolve_call_signature(text_before_cursor)
        if direct is not None:
            return direct
        line_start = text_before_cursor.rfind("\n") + 1
        line = text_before_cursor[line_start:]
        if not line:
            return None
        depth = 0
        close_idx: int | None = None
        for i in range(len(line) - 1, -1, -1):
            c = line[i]
            if c == ")":
                if depth == 0:
                    close_idx = i
                depth += 1
            elif c == "(":
                depth -= 1
                if depth == 0 and close_idx is not None:
                    synthetic = text_before_cursor[: line_start + i + 1]
                    inner = self.resolve_call_signature(synthetic)
                    if inner is None:
                        return None
                    sig, _ = inner
                    args_text = line[i + 1 : close_idx]
                    idx = _active_parameter_index(args_text)
                    return (sig, idx)
        return None

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

    def _local_require_completions(
        self,
        path_prefix: str,
        *,
        prefix_local: bool = False,
    ) -> list[CompletionItem]:
        """Return virtual path completions for ``pm.require('local:…')``."""
        from services.local_script_service import LocalScriptService

        paths = LocalScriptService.list_virtual_paths(language=self._language)
        lower = path_prefix.lower()
        items: list[CompletionItem] = []
        seen_labels: set[str] = set()

        def _insert_text(rel: str) -> str:
            return f"local:{rel}" if prefix_local else rel

        # Offer folder prefixes (e.g. ``auth/``) when typing a partial path.
        if path_prefix and not path_prefix.endswith("/"):
            dir_prefix = lower
            if "/" in dir_prefix:
                dir_prefix = dir_prefix.rsplit("/", 1)[0] + "/"
            else:
                dir_prefix = f"{dir_prefix}/" if dir_prefix else ""
            folder_hints: set[str] = set()
            for rel in paths:
                rl = rel.lower()
                if dir_prefix and rl.startswith(dir_prefix):
                    rest = rl[len(dir_prefix) :]
                    if "/" in rest:
                        folder_hints.add(rel[: len(dir_prefix) + rest.index("/") + 1])
            for hint in sorted(folder_hints):
                if hint.lower() in seen_labels:
                    continue
                seen_labels.add(hint.lower())
                items.append(
                    CompletionItem(
                        label=hint,
                        kind="folder",
                        type_str="local folder",
                        doc=f"Local scripts under {hint}",
                        signature="",
                        insert_text=_insert_text(hint),
                    )
                )

        for rel in paths:
            if lower and not rel.lower().startswith(lower):
                continue
            if rel.lower() in seen_labels:
                continue
            seen_labels.add(rel.lower())
            items.append(
                CompletionItem(
                    label=rel,
                    kind="module",
                    type_str="local script",
                    doc=f"Local script: local:{rel}",
                    signature="",
                    insert_text=_insert_text(rel),
                )
            )
        return items

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
