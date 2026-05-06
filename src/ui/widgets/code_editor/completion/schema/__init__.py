"""Schema sub-package for scripting autocomplete.

Re-exports all public symbols so external code can import from
``schema`` unchanged.
"""

from __future__ import annotations

from ui.widgets.code_editor.completion.schema.core import (
    _EXPECTATION_CHAIN_JS,
    _EXPECTATION_CHAIN_PY,
    SchemaNode,
    _header_list_children,
    _variable_scope_children,
)
from ui.widgets.code_editor.completion.schema.js import JS_GLOBALS, JS_KEYWORDS, JS_SCHEMA
from ui.widgets.code_editor.completion.schema.py import PY_GLOBALS, PY_KEYWORDS, PY_SCHEMA

__all__ = [
    "JS_GLOBALS",
    "JS_KEYWORDS",
    "JS_SCHEMA",
    "PY_GLOBALS",
    "PY_KEYWORDS",
    "PY_SCHEMA",
    "_EXPECTATION_CHAIN_JS",
    "_EXPECTATION_CHAIN_PY",
    "SchemaNode",
    "_header_list_children",
    "_variable_scope_children",
]
