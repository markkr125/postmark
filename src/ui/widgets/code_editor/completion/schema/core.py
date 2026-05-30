"""Core types and shared sub-trees for scripting autocomplete schemas.

Defines :class:`SchemaNode`, the Chai-like expectation chain, and
reusable header/variable-scope builders used by both JavaScript and
Python schema modules.
"""

from __future__ import annotations

from typing import TypedDict


class SchemaNode(TypedDict, total=False):
    """A single entry in the API schema tree."""

    kind: str  # "property" | "method" | "object"
    type_str: str  # short return/value type
    doc: str  # one-line description
    signature: str  # e.g. "(name: string, fn: () => void)"
    children: dict[str, SchemaNode]
    instance_children: dict[str, SchemaNode]  # for "new ClassName()." resolution


# -- Shared sub-trees (reused across scopes) ---------------------------


def _header_list_children(*, mutable: bool = False) -> dict[str, SchemaNode]:
    """Build a HeaderList schema with optional mutation methods."""
    children: dict[str, SchemaNode] = {
        "get": {
            "kind": "method",
            "type_str": "string | undefined",
            "doc": "Get header value by name (case-insensitive)",
            "signature": "(name: string)",
        },
        "has": {
            "kind": "method",
            "type_str": "boolean",
            "doc": "Check if header exists (case-insensitive)",
            "signature": "(name: string)",
        },
        "toObject": {
            "kind": "method",
            "type_str": "object",
            "doc": "Convert headers to plain {key: value} object",
            "signature": "()",
        },
    }
    if mutable:
        children["add"] = {
            "kind": "method",
            "type_str": "void",
            "doc": "Append a new header",
            "signature": "(header: {key, value})",
        }
        children["remove"] = {
            "kind": "method",
            "type_str": "void",
            "doc": "Remove headers matching name (case-insensitive)",
            "signature": "(name: string)",
        }
        children["upsert"] = {
            "kind": "method",
            "type_str": "void",
            "doc": "Update existing header or append if missing",
            "signature": "(header: {key, value})",
        }
    return children


def _variable_scope_children() -> dict[str, SchemaNode]:
    """Build a VariableScope schema (get/set/has/unset/toObject/replaceIn)."""
    return {
        "get": {
            "kind": "method",
            "type_str": "string | undefined",
            "doc": "Get variable value by key",
            "signature": "(key: string)",
        },
        "set": {
            "kind": "method",
            "type_str": "void",
            "doc": "Set variable value (recorded in changes)",
            "signature": "(key: string, value: any)",
        },
        "has": {
            "kind": "method",
            "type_str": "boolean",
            "doc": "Check if variable key exists",
            "signature": "(key: string)",
        },
        "unset": {
            "kind": "method",
            "type_str": "void",
            "doc": "Remove variable from local store",
            "signature": "(key: string)",
        },
        "toObject": {
            "kind": "method",
            "type_str": "object",
            "doc": "Return copy of all variables as plain object",
            "signature": "()",
        },
        "replaceIn": {
            "kind": "method",
            "type_str": "string",
            "doc": "Replace {{key}} placeholders in template string",
            "signature": "(template: string)",
        },
    }


# -- Expectation chain -------------------------------------------------

_EXPECTATION_CHAIN_JS: dict[str, SchemaNode] = {
    # Language chain getters (return self)
    "to": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "be": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "been": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "is": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "that": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "which": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "and": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "has": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "have": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "with": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "at": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "of": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "same": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "but": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "does": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "deep": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    # Negation
    "not": {"kind": "property", "type_str": "Expectation", "doc": "Toggle negation"},
    # Boolean/existence
    "true": {"kind": "property", "type_str": "void", "doc": "Assert value === true"},
    "false": {"kind": "property", "type_str": "void", "doc": "Assert value === false"},
    "null": {"kind": "property", "type_str": "void", "doc": "Assert value === null"},
    "undefined": {"kind": "property", "type_str": "void", "doc": "Assert value === undefined"},
    "NaN": {"kind": "property", "type_str": "void", "doc": "Assert value is NaN"},
    "exist": {"kind": "property", "type_str": "void", "doc": "Assert not null/undefined"},
    "empty": {"kind": "property", "type_str": "void", "doc": "Assert length 0 or no keys"},
    # Methods
    "equal": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Strict equality (===)",
        "signature": "(expected: any)",
    },
    "equals": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for equal()",
        "signature": "(expected: any)",
    },
    "eq": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for equal()",
        "signature": "(expected: any)",
    },
    "eql": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Deep equality via JSON comparison",
        "signature": "(expected: any)",
    },
    "a": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Type check (typeof / 'array')",
        "signature": "(type: string)",
    },
    "an": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for a()",
        "signature": "(type: string)",
    },
    "include": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "String/array contains or object has key",
        "signature": "(val: any)",
    },
    "includes": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for include()",
        "signature": "(val: any)",
    },
    "contain": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for include()",
        "signature": "(val: any)",
    },
    "contains": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for include()",
        "signature": "(val: any)",
    },
    "property": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert object has property",
        "signature": "(name: string, val?: any)",
    },
    "lengthOf": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert .length === n",
        "signature": "(n: number)",
    },
    "length": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for lengthOf()",
        "signature": "(n: number)",
    },
    "above": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value > n",
        "signature": "(n: number)",
    },
    "greaterThan": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for above()",
        "signature": "(n: number)",
    },
    "gt": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for above()",
        "signature": "(n: number)",
    },
    "below": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value < n",
        "signature": "(n: number)",
    },
    "lessThan": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for below()",
        "signature": "(n: number)",
    },
    "lt": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for below()",
        "signature": "(n: number)",
    },
    "least": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value >= n",
        "signature": "(n: number)",
    },
    "gte": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for least()",
        "signature": "(n: number)",
    },
    "most": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value <= n",
        "signature": "(n: number)",
    },
    "lte": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for most()",
        "signature": "(n: number)",
    },
    "match": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value matches regex",
        "signature": "(re: RegExp)",
    },
    "matches": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for match()",
        "signature": "(re: RegExp)",
    },
    "status": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert HTTP status code",
        "signature": "(code: number)",
    },
    "header": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert response has header",
        "signature": "(name: string, value?: string)",
    },
    "jsonBody": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert JSON body at dot-path",
        "signature": "(path: string, value?: any)",
    },
    "jsonSchema": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value matches JSON Schema subset",
        "signature": "(schema: object)",
    },
}

# Fluent chain: every node without explicit ``children`` lists the full chain so
# ``pm.expect.to.have.status`` resolves past single-hop roots.
for _node in _EXPECTATION_CHAIN_JS.values():
    if "children" not in _node:
        _node["children"] = _EXPECTATION_CHAIN_JS


# -- Python expectation chain (mirrors src/services/scripting/_py_sandbox.py) ----

_EXPECTATION_CHAIN_PY: dict[str, SchemaNode] = {
    # Language chain getters (return self)
    "to": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "be": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    "have": {"kind": "property", "type_str": "Expectation", "doc": "Chain connector"},
    # Negation (Python uses ``not_`` since ``not`` is a keyword)
    "not_": {"kind": "property", "type_str": "Expectation", "doc": "Toggle negation"},
    # Boolean / existence
    "true": {"kind": "property", "type_str": "None", "doc": "Assert value is True"},
    "false": {"kind": "property", "type_str": "None", "doc": "Assert value is False"},
    "none": {"kind": "property", "type_str": "None", "doc": "Assert value is None"},
    "exist": {"kind": "property", "type_str": "None", "doc": "Assert value is not None"},
    "empty": {"kind": "property", "type_str": "None", "doc": "Assert len(value) == 0"},
    # Methods
    "equal": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Equality (==)",
        "signature": "(expected: Any)",
    },
    "eql": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Deep equality via JSON comparison",
        "signature": "(expected: Any)",
    },
    "a": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Type check (isinstance / 'list')",
        "signature": "(type: str)",
    },
    "include": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "String/list contains or dict has key",
        "signature": "(val: Any)",
    },
    "has_property": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert dict/object has property",
        "signature": "(name: str, val: Any = None)",
    },
    "length_of": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert len(value) == n",
        "signature": "(n: int)",
    },
    "above": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value > n",
        "signature": "(n: int | float)",
    },
    "below": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value < n",
        "signature": "(n: int | float)",
    },
    "least": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value >= n",
        "signature": "(n: int | float)",
    },
    "most": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value <= n",
        "signature": "(n: int | float)",
    },
    "match": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value matches regex pattern",
        "signature": "(pattern: str)",
    },
    "status": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert HTTP status code",
        "signature": "(code: int)",
    },
    "header": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert response has header",
        "signature": "(name: str, value: str | None = None)",
    },
    "json_body": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert JSON body at dot-path",
        "signature": "(path: str, value: Any = None)",
    },
    "json_schema": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Assert value matches JSON Schema subset",
        "signature": "(schema: dict)",
    },
    "jsonSchema": {
        "kind": "method",
        "type_str": "Expectation",
        "doc": "Alias for json_schema()",
        "signature": "(schema: dict)",
    },
}

for _node in _EXPECTATION_CHAIN_PY.values():
    if "children" not in _node:
        _node["children"] = _EXPECTATION_CHAIN_PY
