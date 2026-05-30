"""Python-specific API schemas for pm/console scripting autocomplete.

Defines ``PY_SCHEMA`` (pm + console) and ``PY_GLOBALS`` (utility
functions injected as builtins) for the Python script variant.
"""

from __future__ import annotations

from ui.widgets.code_editor.completion.schema.core import _EXPECTATION_CHAIN_PY, SchemaNode

# -- Python-specific helpers -------------------------------------------


def _header_list_children_py(*, mutable: bool = False) -> dict[str, SchemaNode]:
    """Python variant of HeaderList with to_dict."""
    children: dict[str, SchemaNode] = {
        "get": {
            "kind": "method",
            "type_str": "str | None",
            "doc": "Get header value by name (case-insensitive)",
            "signature": "(name: str)",
        },
        "has": {
            "kind": "method",
            "type_str": "bool",
            "doc": "Check if header exists (case-insensitive)",
            "signature": "(name: str)",
        },
        "to_dict": {
            "kind": "method",
            "type_str": "dict",
            "doc": "Convert headers to dict",
            "signature": "()",
        },
    }
    if mutable:
        children["add"] = {
            "kind": "method",
            "type_str": "None",
            "doc": "Append a new header",
            "signature": "(header: dict)",
        }
        children["remove"] = {
            "kind": "method",
            "type_str": "None",
            "doc": "Remove headers matching name",
            "signature": "(name: str)",
        }
        children["upsert"] = {
            "kind": "method",
            "type_str": "None",
            "doc": "Update existing header or append",
            "signature": "(header: dict)",
        }
    return children


def _variable_scope_children_py() -> dict[str, SchemaNode]:
    """Python variant of VariableScope (to_dict, replace_in)."""
    return {
        "get": {
            "kind": "method",
            "type_str": "str | None",
            "doc": "Get variable value by key",
            "signature": "(key: str)",
        },
        "set": {
            "kind": "method",
            "type_str": "None",
            "doc": "Set variable value (recorded in changes)",
            "signature": "(key: str, value: Any)",
        },
        "has": {
            "kind": "method",
            "type_str": "bool",
            "doc": "Check if variable key exists",
            "signature": "(key: str)",
        },
        "unset": {
            "kind": "method",
            "type_str": "None",
            "doc": "Remove variable from local store",
            "signature": "(key: str)",
        },
        "to_dict": {
            "kind": "method",
            "type_str": "dict",
            "doc": "Return copy of all variables as dict",
            "signature": "()",
        },
        "replace_in": {
            "kind": "method",
            "type_str": "str",
            "doc": "Replace {{key}} placeholders in template string",
            "signature": "(template: str)",
        },
    }


# -- Python schema ------------------------------------------------------

PY_SCHEMA: dict[str, SchemaNode] = {
    "pm": {
        "kind": "object",
        "type_str": "pm",
        "doc": "Postmark scripting API root",
        "children": {
            "info": {
                "kind": "object",
                "type_str": "PmInfo",
                "doc": "Request execution metadata",
                "children": {
                    "request_name": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "Name of the current request",
                    },
                    "request_id": {
                        "kind": "property",
                        "type_str": "str | int",
                        "doc": "Database ID of the current request",
                    },
                    "iteration": {
                        "kind": "property",
                        "type_str": "int",
                        "doc": "Current iteration index (0-based)",
                    },
                    "iteration_count": {
                        "kind": "property",
                        "type_str": "int",
                        "doc": "Total iteration count",
                    },
                },
            },
            "request": {
                "kind": "object",
                "type_str": "PmRequest",
                "doc": "Current request data (mutable in pre-request)",
                "children": {
                    "url": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "Request URL",
                    },
                    "method": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "HTTP method (GET, POST, etc.)",
                    },
                    "headers": {
                        "kind": "object",
                        "type_str": "HeaderList",
                        "doc": "Request headers",
                        "children": _header_list_children_py(mutable=True),
                    },
                    "body": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "Request body content",
                    },
                },
            },
            "response": {
                "kind": "object",
                "type_str": "PmResponse | None",
                "doc": "Response data (None in pre-request scripts)",
                "children": {
                    "code": {
                        "kind": "property",
                        "type_str": "int",
                        "doc": "HTTP status code",
                    },
                    "status": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "HTTP status text",
                    },
                    "headers": {
                        "kind": "object",
                        "type_str": "HeaderList",
                        "doc": "Response headers (read-only)",
                        "children": _header_list_children_py(mutable=False),
                    },
                    "response_time": {
                        "kind": "property",
                        "type_str": "float",
                        "doc": "Response time in milliseconds",
                    },
                    "response_size": {
                        "kind": "property",
                        "type_str": "int",
                        "doc": "Response size in bytes",
                    },
                    "body": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "Raw response body",
                    },
                    "json": {
                        "kind": "method",
                        "type_str": "Any",
                        "doc": "Parse body as JSON",
                        "signature": "()",
                    },
                    "text": {
                        "kind": "method",
                        "type_str": "str",
                        "doc": "Return body as string",
                        "signature": "()",
                    },
                    "to": {
                        "kind": "object",
                        "type_str": "Expectation",
                        "doc": "Postman-style assertion chain (pm.response.to.have.status(...))",
                        "children": _EXPECTATION_CHAIN_PY,
                    },
                },
            },
            "variables": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Current-scope variable store",
                "children": _variable_scope_children_py(),
            },
            "environment": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Environment variable store",
                "children": {
                    **_variable_scope_children_py(),
                    "name": {
                        "kind": "property",
                        "type_str": "str",
                        "doc": "Active environment display name",
                    },
                },
            },
            "collection_variables": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Collection-level variable store",
                "children": _variable_scope_children_py(),
            },
            "globals": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Global variable store (persisted to disk)",
                "children": _variable_scope_children_py(),
            },
            "test": {
                "kind": "method",
                "type_str": "None",
                "doc": "Register a named test",
                "signature": "(name: str, fn: Callable)",
            },
            "expect": {
                "kind": "method",
                "type_str": "Expectation",
                "doc": "Create assertion chain",
                "signature": "(value: Any)",
                "children": _EXPECTATION_CHAIN_PY,
            },
            "require": {
                "kind": "method",
                "type_str": "ModuleType",
                "doc": ("Import PyPI (micropip) or a Local script (e.g. 'local:auth/helper.py')"),
                "signature": "(spec: str)",
            },
            "send_request": {
                "kind": "method",
                "type_str": "None",
                "doc": "Queue an HTTP sub-request (max 10 per script)",
                "signature": "(spec: str | dict, callback: Callable = None)",
            },
            "cookies": {
                "kind": "object",
                "type_str": "CookieJar",
                "doc": "Parsed Set-Cookie headers from response",
                "children": {
                    "get": {
                        "kind": "method",
                        "type_str": "str | None",
                        "doc": "Get cookie value by name",
                        "signature": "(name: str)",
                    },
                    "get_all": {
                        "kind": "method",
                        "type_str": "list[dict]",
                        "doc": "Get all cookies as [{name, value}]",
                        "signature": "()",
                    },
                    "has": {
                        "kind": "method",
                        "type_str": "bool",
                        "doc": "Return whether a cookie name exists",
                        "signature": "(name: str)",
                    },
                },
            },
            "execution": {
                "kind": "object",
                "type_str": "Execution",
                "doc": "Flow control for collection runner",
                "children": {
                    "set_next_request": {
                        "kind": "method",
                        "type_str": "None",
                        "doc": "Set next request to execute; None stops",
                        "signature": "(name: str | None)",
                    },
                    "skip_request": {
                        "kind": "method",
                        "type_str": "None",
                        "doc": "Skip the current request",
                        "signature": "()",
                    },
                },
            },
            "iteration_data": {
                "kind": "object",
                "type_str": "IterationData",
                "doc": "Collection runner iteration data",
                "children": {
                    "get": {
                        "kind": "method",
                        "type_str": "Any",
                        "doc": "Get iteration data value by key",
                        "signature": "(key: str)",
                    },
                    "to_object": {
                        "kind": "method",
                        "type_str": "dict",
                        "doc": "Return copy of all iteration data",
                        "signature": "()",
                    },
                    "has": {
                        "kind": "method",
                        "type_str": "bool",
                        "doc": "Check if key exists",
                        "signature": "(key: str)",
                    },
                },
            },
        },
    },
    "console": {
        "kind": "object",
        "type_str": "Console",
        "doc": "Logging output (rate-limited to 200 messages)",
        "children": {
            "log": {
                "kind": "method",
                "type_str": "None",
                "doc": "Log message at 'log' level",
                "signature": "(*args)",
            },
            "warn": {
                "kind": "method",
                "type_str": "None",
                "doc": "Log message at 'warn' level",
                "signature": "(*args)",
            },
            "error": {
                "kind": "method",
                "type_str": "None",
                "doc": "Log message at 'error' level",
                "signature": "(*args)",
            },
            "info": {
                "kind": "method",
                "type_str": "None",
                "doc": "Log message at 'info' level",
                "signature": "(*args)",
            },
        },
    },
}

# Python-only global utility functions (injected as builtins, no prefix).
PY_GLOBALS: dict[str, SchemaNode] = {
    "json_loads": {
        "kind": "method",
        "type_str": "Any",
        "doc": "Parse JSON string",
        "signature": "(s: str)",
    },
    "json_dumps": {
        "kind": "method",
        "type_str": "str",
        "doc": "Serialize to JSON string",
        "signature": "(obj: Any)",
    },
    "re_match": {
        "kind": "method",
        "type_str": "Match | None",
        "doc": "Match regex at start of string",
        "signature": "(pattern: str, string: str)",
    },
    "re_search": {
        "kind": "method",
        "type_str": "Match | None",
        "doc": "Search for regex in string",
        "signature": "(pattern: str, string: str)",
    },
    "re_findall": {
        "kind": "method",
        "type_str": "list[str]",
        "doc": "Find all regex matches",
        "signature": "(pattern: str, string: str)",
    },
    "re_sub": {
        "kind": "method",
        "type_str": "str",
        "doc": "Replace regex matches",
        "signature": "(pattern: str, repl: str, string: str)",
    },
    "math_ceil": {
        "kind": "method",
        "type_str": "int",
        "doc": "Ceiling of x",
        "signature": "(x: float)",
    },
    "math_floor": {
        "kind": "method",
        "type_str": "int",
        "doc": "Floor of x",
        "signature": "(x: float)",
    },
    "math_sqrt": {
        "kind": "method",
        "type_str": "float",
        "doc": "Square root of x",
        "signature": "(x: float)",
    },
    "math_pow": {
        "kind": "method",
        "type_str": "float",
        "doc": "x raised to power y",
        "signature": "(x: float, y: float)",
    },
    "math_log": {
        "kind": "method",
        "type_str": "float",
        "doc": "Natural logarithm of x",
        "signature": "(x: float)",
    },
    "math_pi": {
        "kind": "property",
        "type_str": "float",
        "doc": "Mathematical constant pi",
    },
    "math_e": {
        "kind": "property",
        "type_str": "float",
        "doc": "Mathematical constant e",
    },
    "b64encode": {
        "kind": "method",
        "type_str": "str",
        "doc": "Base64 encode string",
        "signature": "(s: str)",
    },
    "b64decode": {
        "kind": "method",
        "type_str": "str",
        "doc": "Base64 decode string",
        "signature": "(s: str)",
    },
    "hashlib_md5": {
        "kind": "method",
        "type_str": "str",
        "doc": "MD5 hex digest",
        "signature": "(s: str)",
    },
    "hashlib_sha256": {
        "kind": "method",
        "type_str": "str",
        "doc": "SHA-256 hex digest",
        "signature": "(s: str)",
    },
    "hashlib_hmac_sha256": {
        "kind": "method",
        "type_str": "str",
        "doc": "HMAC-SHA256 hex digest",
        "signature": "(data: str, key: str)",
    },
    "uuid_v4": {
        "kind": "method",
        "type_str": "str",
        "doc": "Generate a random UUID v4 string",
        "signature": "()",
    },
    "datetime_now": {
        "kind": "method",
        "type_str": "datetime",
        "doc": "Current local datetime",
        "signature": "()",
    },
    "datetime_utcnow": {
        "kind": "method",
        "type_str": "datetime",
        "doc": "Current UTC datetime",
        "signature": "()",
    },
    "url_quote": {
        "kind": "method",
        "type_str": "str",
        "doc": "URL-encode a string",
        "signature": "(s: str)",
    },
    "url_urlencode": {
        "kind": "method",
        "type_str": "str",
        "doc": "URL-encode query parameters",
        "signature": "(params: dict)",
    },
}

# -- Language keywords (top-level completion) --------------------------

PY_KEYWORDS: dict[str, SchemaNode] = {
    kw: {"kind": "keyword", "type_str": "keyword", "doc": "", "signature": ""}
    for kw in (
        "def",
        "class",
        "return",
        "yield",
        "lambda",
        "pass",
        "if",
        "elif",
        "else",
        "for",
        "while",
        "break",
        "continue",
        "try",
        "except",
        "finally",
        "raise",
        "with",
        "as",
        "import",
        "from",
        "global",
        "nonlocal",
        "and",
        "or",
        "not",
        "is",
        "in",
        "async",
        "await",
        "True",
        "False",
        "None",
    )
}
