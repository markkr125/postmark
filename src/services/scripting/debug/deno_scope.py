"""CDP call-frame scope materialisation (``Runtime.getProperties``).

Expands ``pm`` and ``console`` RemoteObjects into nested dicts so the debug
inspector and merged hover locals are not stuck on the CDP description string
``Object``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_SCOPE_INCLUDE_TYPES: frozenset[str] = frozenset(
    {
        "local",
        "block",
        "closure",
        "catch",
        "with",
        "eval",
        # Deno debug bundles are ``.mjs``; top-level ``const``/``let`` live here.
        "module",
    },
)
_SCOPE_MAX_PROPS: int = 200
_SCOPE_LABELS: dict[str, str] = {
    "local": "Local",
    "block": "Block",
    "closure": "Closure",
    "catch": "Catch",
    "with": "With",
    "eval": "Eval",
    "module": "Module",
}

# Bundle ``module`` scope lists every top-level binding (polyfills, bootstrap).
# When paused inside these frames, skip ``module`` — user bindings are local.
_SKIP_MODULE_FOR_FUNCTION: frozenset[str] = frozenset(
    {"__pm_debugUserScript", "__denoIpcDrain"},
)

# Deep-fetch these module-scope bindings (CDP ``description`` is only "Object").
_SCOPE_EXPAND_BINDING_NAMES: frozenset[str] = frozenset({"pm", "console"})
_SCOPE_OBJECT_RECURSE_MAX: int = 3

# Must match ``ui.widgets.debug_value_tree.CLASSNAME_KEY`` (no services → ui import).
_PM_CLASSNAME_KEY: str = "__pm_className__"


def _merge_nested_with_remote_classname(
    nested: dict[str, Any],
    val_obj: dict[str, Any],
) -> dict[str, Any]:
    """Attach CDP ``description`` as a UI-only classname when it is informative."""
    raw = val_obj.get("description")
    desc = raw.strip() if isinstance(raw, str) else ""
    if not desc or desc in ("Object", "Array"):
        return nested
    if re.fullmatch(r"Array\(\d+\)", desc):
        return nested
    return {**nested, _PM_CLASSNAME_KEY: desc}


def _filter_module_scope_keys(vars_: dict[str, Any]) -> dict[str, Any]:
    """Remove ``__*`` names from the bundle module record (polyfill / runtime)."""
    return {k: v for k, v in vars_.items() if isinstance(k, str) and not k.startswith("__")}


def _materialize_remote_value(ro: dict[str, Any]) -> Any:
    """Reduce a CDP RemoteObject to a primitive or string for display."""
    if not isinstance(ro, dict):
        return None
    t = ro.get("type")
    sub = ro.get("subtype")
    desc = ro.get("description")
    if t in ("string", "number", "boolean") and "value" in ro:
        return ro["value"]
    if t == "undefined":
        return None
    if sub == "null":
        return None
    if t == "bigint":
        return desc if desc is not None else str(ro.get("value", ""))
    if t == "object":
        return desc if desc else "[object]"
    if t == "function":
        return desc if desc else "[function]"
    if t == "symbol":
        return desc if desc else "[symbol]"
    return desc if desc is not None else str(ro.get("value", ""))


class _CdpClient(Protocol):
    """Minimal CDP surface used by scope collection."""

    def req(self, method: str, params: dict[str, Any] | None) -> Any: ...


def _fetch_own_properties_nested(
    c: _CdpClient,
    object_id: str,
    *,
    depth: int,
    max_depth: int,
) -> dict[str, Any] | None:
    """Return own enumerable properties as a JSON-like dict, or ``None`` on CDP failure."""
    if depth > max_depth:
        return None
    try:
        res = c.req(
            "Runtime.getProperties",
            {
                "objectId": object_id,
                "ownProperties": True,
                "generatePreview": True,
            },
        )
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.debug("nested getProperties failed: %s", exc)
        return None
    if not isinstance(res, dict):
        return None
    props = res.get("result")
    if not isinstance(props, list):
        return None
    out: dict[str, Any] = {}
    for p in props[:_SCOPE_MAX_PROPS]:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name or name.startswith("["):
            continue
        val_obj = p.get("value")
        if val_obj is None:
            continue
        if not isinstance(val_obj, dict):
            out[name] = str(val_obj)
            continue
        t = val_obj.get("type")
        if t == "object":
            oid = val_obj.get("objectId")
            if isinstance(oid, str) and oid and depth < max_depth:
                nested = _fetch_own_properties_nested(c, oid, depth=depth + 1, max_depth=max_depth)
                if nested is not None:
                    out[name] = _merge_nested_with_remote_classname(nested, val_obj)
                else:
                    out[name] = _materialize_remote_value(val_obj)
            else:
                out[name] = _materialize_remote_value(val_obj)
        else:
            out[name] = _materialize_remote_value(val_obj)
    return out


def _fetch_scope_vars(c: _CdpClient, scope_obj_id: str) -> dict[str, Any]:
    """Call ``Runtime.getProperties`` for one scope object; return flat name→value."""
    out: dict[str, Any] = {}
    try:
        res = c.req(
            "Runtime.getProperties",
            {
                "objectId": scope_obj_id,
                "ownProperties": True,
                "generatePreview": True,
            },
        )
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.debug("scope getProperties failed: %s", exc)
        return out
    if not isinstance(res, dict):
        return out
    props = res.get("result")
    if not isinstance(props, list):
        return out
    for p in props[:_SCOPE_MAX_PROPS]:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name or name.startswith("["):
            continue
        val_obj = p.get("value")
        if val_obj is None:
            out[name] = "<unreadable>"
            continue
        if not isinstance(val_obj, dict):
            out[name] = str(val_obj)
            continue
        if (
            name in _SCOPE_EXPAND_BINDING_NAMES
            and val_obj.get("type") == "object"
            and isinstance(val_obj.get("objectId"), str)
        ):
            oid = val_obj["objectId"]
            expanded = _fetch_own_properties_nested(
                c,
                oid,
                depth=0,
                max_depth=_SCOPE_OBJECT_RECURSE_MAX,
            )
            out[name] = expanded if expanded is not None else _materialize_remote_value(val_obj)
        else:
            out[name] = _materialize_remote_value(val_obj)
    return out


def _collect_call_frame_scopes(
    m: dict[str, Any],
    c: _CdpClient,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Walk ``callFrames[0].scopeChain``; return ``(flat_locals, scopes_list)``.

    ``scopes_list`` preserves CDP order (innermost-first). ``flat_locals`` is
    innermost-wins so the hover popup picks the closest binding.
    """
    flat: dict[str, Any] = {}
    scopes: list[dict[str, Any]] = []
    if not isinstance(m, dict):
        return flat, scopes
    params = m.get("params")
    if not isinstance(params, dict):
        return flat, scopes
    cfs = params.get("callFrames")
    if not isinstance(cfs, list) or not cfs:
        return flat, scopes
    cf0 = cfs[0]
    if not isinstance(cf0, dict):
        return flat, scopes
    fn = str(cf0.get("functionName") or "")
    skip_module_scope = fn in _SKIP_MODULE_FOR_FUNCTION
    chain = cf0.get("scopeChain") or []
    if not isinstance(chain, list):
        return flat, scopes
    for sc in chain:
        if not isinstance(sc, dict):
            continue
        stype = sc.get("type")
        if stype not in _SCOPE_INCLUDE_TYPES:
            continue
        if stype == "module" and skip_module_scope:
            continue
        obj = sc.get("object") or {}
        oid = obj.get("objectId") if isinstance(obj, dict) else None
        if not isinstance(oid, str) or not oid:
            continue
        vars_ = _fetch_scope_vars(c, oid)
        if stype == "module":
            vars_ = _filter_module_scope_keys(vars_)
        if not vars_:
            continue
        label = _SCOPE_LABELS.get(str(stype), str(stype).capitalize() if stype else "Local")
        scopes.append({"type": stype, "name": label, "vars": vars_})
        for k, v in vars_.items():
            if k not in flat:
                flat[k] = v
    return flat, scopes
