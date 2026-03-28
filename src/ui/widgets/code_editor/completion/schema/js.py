"""JavaScript API schema and global completions for scripting autocomplete.

Defines ``JS_SCHEMA`` (pm + console + postman + CryptoJS dot-path trees)
and ``JS_GLOBALS`` (top-level globals shown on Ctrl+Space without a dot).
"""

from __future__ import annotations

from ui.widgets.code_editor.completion.schema.core import (
    _EXPECTATION_CHAIN_JS,
    SchemaNode,
    _header_list_children,
    _variable_scope_children,
)

# -- JavaScript pm + console schema ------------------------------------

JS_SCHEMA: dict[str, SchemaNode] = {
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
                    "requestName": {
                        "kind": "property",
                        "type_str": "string",
                        "doc": "Name of the current request",
                    },
                    "requestId": {
                        "kind": "property",
                        "type_str": "string | number",
                        "doc": "Database ID of the current request",
                    },
                    "iteration": {
                        "kind": "property",
                        "type_str": "number",
                        "doc": "Current iteration index (0-based)",
                    },
                    "iterationCount": {
                        "kind": "property",
                        "type_str": "number",
                        "doc": "Total iteration count",
                    },
                    "eventName": {
                        "kind": "property",
                        "type_str": "string",
                        "doc": "Script phase: 'prerequest' or 'test'",
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
                        "type_str": "string",
                        "doc": "Request URL",
                    },
                    "method": {
                        "kind": "property",
                        "type_str": "string",
                        "doc": "HTTP method (GET, POST, etc.)",
                    },
                    "headers": {
                        "kind": "object",
                        "type_str": "HeaderList",
                        "doc": "Request headers",
                        "children": _header_list_children(mutable=True),
                    },
                    "body": {
                        "kind": "property",
                        "type_str": "string",
                        "doc": "Request body content",
                    },
                },
            },
            "response": {
                "kind": "object",
                "type_str": "PmResponse | null",
                "doc": "Response data (null in pre-request scripts)",
                "children": {
                    "code": {
                        "kind": "property",
                        "type_str": "number",
                        "doc": "HTTP status code",
                    },
                    "status": {
                        "kind": "property",
                        "type_str": "string",
                        "doc": "HTTP status text",
                    },
                    "headers": {
                        "kind": "object",
                        "type_str": "HeaderList",
                        "doc": "Response headers (read-only)",
                        "children": _header_list_children(mutable=False),
                    },
                    "responseTime": {
                        "kind": "property",
                        "type_str": "number",
                        "doc": "Response time in milliseconds",
                    },
                    "responseSize": {
                        "kind": "property",
                        "type_str": "number",
                        "doc": "Response size in bytes",
                    },
                    "body": {
                        "kind": "property",
                        "type_str": "string",
                        "doc": "Raw response body",
                    },
                    "json": {
                        "kind": "method",
                        "type_str": "any",
                        "doc": "Parse body as JSON",
                        "signature": "()",
                    },
                    "text": {
                        "kind": "method",
                        "type_str": "string",
                        "doc": "Return body as string",
                        "signature": "()",
                    },
                },
            },
            "variables": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Current-scope variable store",
                "children": _variable_scope_children(),
            },
            "environment": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Environment variable store",
                "children": _variable_scope_children(),
            },
            "collectionVariables": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Collection-level variable store",
                "children": _variable_scope_children(),
            },
            "globals": {
                "kind": "object",
                "type_str": "VariableScope",
                "doc": "Global variable store (persisted to disk)",
                "children": _variable_scope_children(),
            },
            "test": {
                "kind": "method",
                "type_str": "void",
                "doc": "Register a named test",
                "signature": "(name: string, fn: () => void)",
            },
            "expect": {
                "kind": "method",
                "type_str": "Expectation",
                "doc": "Create a Chai-like assertion chain",
                "signature": "(value: any)",
                "children": _EXPECTATION_CHAIN_JS,
            },
            "sendRequest": {
                "kind": "method",
                "type_str": "void",
                "doc": "Queue an HTTP sub-request (max 10 per script)",
                "signature": "(spec: string | RequestSpec, callback?: Function)",
            },
            "cookies": {
                "kind": "object",
                "type_str": "CookieJar",
                "doc": "Parsed Set-Cookie headers from response",
                "children": {
                    "get": {
                        "kind": "method",
                        "type_str": "string | undefined",
                        "doc": "Get cookie value by name",
                        "signature": "(name: string)",
                    },
                    "getAll": {
                        "kind": "method",
                        "type_str": "Array",
                        "doc": "Get all cookies as [{name, value}]",
                        "signature": "()",
                    },
                },
            },
            "execution": {
                "kind": "object",
                "type_str": "Execution",
                "doc": "Flow control for collection runner",
                "children": {
                    "setNextRequest": {
                        "kind": "method",
                        "type_str": "void",
                        "doc": "Set next request to execute; null stops",
                        "signature": "(name: string | null)",
                    },
                    "skipRequest": {
                        "kind": "method",
                        "type_str": "void",
                        "doc": "Skip the current request",
                        "signature": "()",
                    },
                },
            },
            "iterationData": {
                "kind": "object",
                "type_str": "IterationData",
                "doc": "Collection runner iteration data",
                "children": {
                    "get": {
                        "kind": "method",
                        "type_str": "any",
                        "doc": "Get iteration data value by key",
                        "signature": "(key: string)",
                    },
                    "toObject": {
                        "kind": "method",
                        "type_str": "object",
                        "doc": "Return copy of all iteration data",
                        "signature": "()",
                    },
                    "has": {
                        "kind": "method",
                        "type_str": "boolean",
                        "doc": "Check if key exists",
                        "signature": "(key: string)",
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
                "type_str": "void",
                "doc": "Log message at 'log' level",
                "signature": "(...args: any[])",
            },
            "warn": {
                "kind": "method",
                "type_str": "void",
                "doc": "Log message at 'warn' level",
                "signature": "(...args: any[])",
            },
            "error": {
                "kind": "method",
                "type_str": "void",
                "doc": "Log message at 'error' level",
                "signature": "(...args: any[])",
            },
            "info": {
                "kind": "method",
                "type_str": "void",
                "doc": "Log message at 'info' level",
                "signature": "(...args: any[])",
            },
        },
    },
}


# -- Vendor library + legacy postman schemas ----------------------------


def _crypto_hash_method(name: str) -> SchemaNode:
    """Build a CryptoJS hash/HMAC method node."""
    return {
        "kind": "method",
        "type_str": "WordArray",
        "doc": f"Compute {name} hash or HMAC",
        "signature": "(message: string, key?: string)",
    }


def _cipher_children(name: str, *, stream: bool = False) -> dict[str, SchemaNode]:
    """Build encrypt/decrypt children for a CryptoJS cipher."""
    sig_extra = "" if stream else ", cfg?: object"
    return {
        "encrypt": {
            "kind": "method",
            "type_str": "CipherParams",
            "doc": f"Encrypt with {name}",
            "signature": f"(message: string, key: string{sig_extra})",
        },
        "decrypt": {
            "kind": "method",
            "type_str": "WordArray",
            "doc": f"Decrypt with {name}",
            "signature": f"(ciphertext: CipherParams | string, key: string{sig_extra})",
        },
    }


_CRYPTO_ENC_CHILDREN: dict[str, SchemaNode] = {
    "Hex": {"kind": "property", "type_str": "Encoder", "doc": "Hexadecimal encoder"},
    "Utf8": {"kind": "property", "type_str": "Encoder", "doc": "UTF-8 encoder"},
    "Base64": {"kind": "property", "type_str": "Encoder", "doc": "Base64 encoder"},
    "Latin1": {"kind": "property", "type_str": "Encoder", "doc": "Latin-1 encoder"},
    "Utf16": {"kind": "property", "type_str": "Encoder", "doc": "UTF-16 encoder"},
}

_CRYPTO_JS_CHILDREN: dict[str, SchemaNode] = {
    "MD5": _crypto_hash_method("MD5"),
    "SHA1": _crypto_hash_method("SHA-1"),
    "SHA256": _crypto_hash_method("SHA-256"),
    "SHA224": _crypto_hash_method("SHA-224"),
    "SHA512": _crypto_hash_method("SHA-512"),
    "SHA384": _crypto_hash_method("SHA-384"),
    "SHA3": _crypto_hash_method("SHA-3"),
    "RIPEMD160": _crypto_hash_method("RIPEMD-160"),
    "HmacMD5": _crypto_hash_method("HMAC-MD5"),
    "HmacSHA1": _crypto_hash_method("HMAC-SHA1"),
    "HmacSHA256": _crypto_hash_method("HMAC-SHA256"),
    "HmacSHA512": _crypto_hash_method("HMAC-SHA512"),
    "AES": {
        "kind": "object",
        "type_str": "Cipher",
        "doc": "AES symmetric cipher",
        "children": _cipher_children("AES"),
    },
    "DES": {
        "kind": "object",
        "type_str": "Cipher",
        "doc": "DES symmetric cipher",
        "children": _cipher_children("DES"),
    },
    "TripleDES": {
        "kind": "object",
        "type_str": "Cipher",
        "doc": "Triple-DES symmetric cipher",
        "children": _cipher_children("Triple-DES"),
    },
    "Rabbit": {
        "kind": "object",
        "type_str": "Cipher",
        "doc": "Rabbit stream cipher",
        "children": _cipher_children("Rabbit", stream=True),
    },
    "RC4": {
        "kind": "object",
        "type_str": "Cipher",
        "doc": "RC4 stream cipher",
        "children": _cipher_children("RC4", stream=True),
    },
    "enc": {
        "kind": "object",
        "type_str": "Encoders",
        "doc": "Encoding formatters for hash output",
        "children": _CRYPTO_ENC_CHILDREN,
    },
    "lib": {
        "kind": "object",
        "type_str": "CryptoLib",
        "doc": "Core library classes",
        "children": {
            "WordArray": {
                "kind": "object",
                "type_str": "WordArray",
                "doc": "Array of 32-bit words",
                "children": {
                    "create": {
                        "kind": "method",
                        "type_str": "WordArray",
                        "doc": "Create a WordArray from values",
                        "signature": "(words?: number[], sigBytes?: number)",
                    },
                    "random": {
                        "kind": "method",
                        "type_str": "WordArray",
                        "doc": "Generate random bytes",
                        "signature": "(nBytes: number)",
                    },
                },
            },
        },
    },
}

_POSTMAN_CHILDREN: dict[str, SchemaNode] = {
    "setEnvironmentVariable": {
        "kind": "method",
        "type_str": "void",
        "doc": "Set an environment variable",
        "signature": "(key: string, value: string)",
    },
    "getEnvironmentVariable": {
        "kind": "method",
        "type_str": "string",
        "doc": "Get an environment variable value",
        "signature": "(key: string)",
    },
    "clearEnvironmentVariable": {
        "kind": "method",
        "type_str": "void",
        "doc": "Remove an environment variable",
        "signature": "(key: string)",
    },
    "setGlobalVariable": {
        "kind": "method",
        "type_str": "void",
        "doc": "Set a global variable",
        "signature": "(key: string, value: string)",
    },
    "getGlobalVariable": {
        "kind": "method",
        "type_str": "string",
        "doc": "Get a global variable value",
        "signature": "(key: string)",
    },
    "clearGlobalVariable": {
        "kind": "method",
        "type_str": "void",
        "doc": "Remove a global variable",
        "signature": "(key: string)",
    },
}

# Augment JS_SCHEMA with postman and CryptoJS dot-path entries.
JS_SCHEMA["postman"] = {
    "kind": "object",
    "type_str": "postman",
    "doc": "Legacy Postman scripting API (use pm.* instead)",
    "children": _POSTMAN_CHILDREN,
}

JS_SCHEMA["CryptoJS"] = {
    "kind": "object",
    "type_str": "CryptoJS",
    "doc": "CryptoJS encryption and hashing library",
    "children": _CRYPTO_JS_CHILDREN,
}


# -- JS-only globals (shown on Ctrl+Space without a dot prefix) --------

JS_GLOBALS: dict[str, SchemaNode] = {
    "require": {
        "kind": "method",
        "type_str": "module",
        "doc": "Import a bundled library (e.g. 'lodash', 'moment', 'crypto-js')",
        "signature": "(module: string)",
    },
    "atob": {
        "kind": "method",
        "type_str": "string",
        "doc": "Decode base64 string",
        "signature": "(encoded: string)",
    },
    "btoa": {
        "kind": "method",
        "type_str": "string",
        "doc": "Encode string to base64",
        "signature": "(data: string)",
    },
}
