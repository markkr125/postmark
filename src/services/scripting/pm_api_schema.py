"""Schema of the pm/postman API exposed to user scripts.

Used by ScriptLinter to flag unknown members and wrong-kind usage
(e.g. calling a namespace, accessing a property on a function).
Keep in sync with data/scripts/pm_bootstrap.js.
"""

from __future__ import annotations

from typing import Literal, TypedDict, cast

Kind = Literal["namespace", "function", "scope", "any"]


class PmNode(TypedDict, total=False):
    """Recursive schema node for the pm/postman API tree."""

    kind: Kind
    children: dict[str, PmNode]


# A "scope" has: get, set, unset, has, toObject, clear, replaceIn.
_SCOPE: PmNode = {
    "kind": "scope",
    "children": {
        "get": {"kind": "function"},
        "set": {"kind": "function"},
        "unset": {"kind": "function"},
        "has": {"kind": "function"},
        "toObject": {"kind": "function"},
        "clear": {"kind": "function"},
        "replaceIn": {"kind": "function"},
    },
}

PM_SCHEMA: PmNode = {
    "kind": "namespace",
    "children": {
        "info": {
            "kind": "namespace",
            "children": {
                "eventName": {"kind": "any"},
                "requestName": {"kind": "any"},
                "requestId": {"kind": "any"},
                "iteration": {"kind": "any"},
                "iterationCount": {"kind": "any"},
                "testFilter": {"kind": "any"},
            },
        },
        "request": {"kind": "namespace", "children": {}},
        "response": {"kind": "namespace", "children": {}},
        "cookies": {
            "kind": "namespace",
            "children": {
                "get": {"kind": "function"},
                "getAll": {"kind": "function"},
                "has": {"kind": "function"},
                "jar": {"kind": "function"},
            },
        },
        "iterationData": {
            "kind": "namespace",
            "children": {
                "get": {"kind": "function"},
                "has": {"kind": "function"},
                "toObject": {"kind": "function"},
            },
        },
        "execution": {
            "kind": "namespace",
            "children": {
                "setNextRequest": {"kind": "function"},
                "skipRequest": {"kind": "function"},
                "location": {"kind": "namespace", "children": {}},
            },
        },
        "variables": _SCOPE,
        "environment": {
            "kind": "scope",
            "children": {
                **(_SCOPE.get("children") or {}),
                "name": {"kind": "any"},
            },
        },
        "collectionVariables": _SCOPE,
        "globals": _SCOPE,
        "visualizer": {
            "kind": "namespace",
            "children": {
                "set": {"kind": "function"},
            },
        },
        "test": {"kind": "function"},
        "expect": {"kind": "function"},
        "sendRequest": {"kind": "function"},
        "require": {"kind": "function"},
    },
}

POSTMAN_SCHEMA: PmNode = {
    "kind": "namespace",
    "children": {
        "setEnvironmentVariable": {"kind": "function"},
        "getEnvironmentVariable": {"kind": "function"},
        "clearEnvironmentVariable": {"kind": "function"},
        "setGlobalVariable": {"kind": "function"},
        "getGlobalVariable": {"kind": "function"},
        "clearGlobalVariable": {"kind": "function"},
        "setNextRequest": {"kind": "function"},
    },
}

ROOTS: dict[str, PmNode] = {"pm": PM_SCHEMA, "postman": POSTMAN_SCHEMA}


def lookup(root_name: str, path: list[str]) -> PmNode | None:
    """Walk the schema. Return the node or None if any segment is unknown.

    If a segment lands inside a namespace whose children dict is EMPTY,
    further segments are accepted as 'any' (used for pm.request.headers etc
    whose shape is dynamic).
    """
    node = ROOTS.get(root_name)
    if node is None:
        return None
    for seg in path:
        children = node.get("children")
        if children is None:
            return cast(PmNode, {"kind": "any"})
        if not children:  # free-form namespace (e.g. pm.request.*) — any deeper segment is valid
            return cast(PmNode, {"kind": "any"})
        child = children.get(seg)
        if child is None:
            return None
        node = child
    return node
