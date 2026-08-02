"""Signature recipe registry — deterministic, reviewed signing scripts.

The model never invents crypto. It names a recipe ``kind``; we emit a
reviewed pre-request script that uses sandbox shims (Python) or CryptoJS (JS).

Header and variable names interpolated into generated scripts are validated
against strict patterns so hostile OpenAPI names or model overrides cannot
break out of string literals.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.ai.chat.tools.collection_draft.config import draft_script_language

# Strict patterns — values are interpolated into generated Python/JS source.
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OVERRIDE_KEYS = frozenset({"signature_header", "key_header", "key_var", "secret_var"})


@dataclass(frozen=True)
class SignatureRecipe:
    """A named, reviewed header-signature algorithm.

    Attributes:
        kind: Stable identifier (e.g. ``sha256_apikey_secret_timestamp``).
        signature_header: HTTP header that receives the computed signature.
        key_header: Optional companion header for the API key (e.g. ``Api-key``).
        key_var: Collection variable name for the API key (default ``apiKey``).
        secret_var: Collection variable name for the shared secret.
        notes: Short human-readable description of the algorithm.
    """

    kind: str
    signature_header: str
    key_header: str | None
    key_var: str
    secret_var: str
    notes: str


# kind -> (recipe factory from optional overrides, py builder, js builder)
_RecipeBuilders = tuple[
    Callable[[dict[str, Any]], SignatureRecipe],
    Callable[[SignatureRecipe], str],
    Callable[[SignatureRecipe], str],
]

_REGISTRY: dict[str, _RecipeBuilders] = {}


def is_safe_header_name(value: str) -> bool:
    """Return True when *value* is safe to interpolate as an HTTP header name."""
    return bool(value) and _HEADER_NAME_RE.fullmatch(value) is not None


def is_safe_var_name(value: str) -> bool:
    """Return True when *value* is safe to interpolate as a collection variable name."""
    return bool(value) and _VAR_NAME_RE.fullmatch(value) is not None


def validate_signature_overrides(raw: dict[str, Any]) -> str | None:
    """Return an error hint when any override field fails the safety pattern.

    ``None`` means all provided override fields are safe (or absent).
    """
    for key in ("signature_header", "key_header"):
        value = str(raw.get(key) or "").strip()
        if value and not is_safe_header_name(value):
            return (
                f"signature.{key} must be an HTTP header name "
                f"(letters, digits, hyphen, underscore); got {value!r}."
            )
    for key in ("key_var", "secret_var"):
        value = str(raw.get(key) or "").strip()
        if value and not is_safe_var_name(value):
            return (
                f"signature.{key} must be a variable name "
                f"(letter/underscore then alphanumerics); got {value!r}."
            )
    return None


def sanitize_header_name(value: str, default: str) -> str:
    """Return *value* when safe, otherwise *default*."""
    cleaned = (value or "").strip()
    if cleaned and is_safe_header_name(cleaned):
        return cleaned
    return default


def sanitize_var_name(value: str, default: str) -> str:
    """Return *value* when safe, otherwise *default*."""
    cleaned = (value or "").strip()
    if cleaned and is_safe_var_name(cleaned):
        return cleaned
    return default


def register_recipe(
    kind: str,
    *,
    factory: Callable[[dict[str, Any]], SignatureRecipe],
    build_python: Callable[[SignatureRecipe], str],
    build_javascript: Callable[[SignatureRecipe], str],
) -> None:
    """Register a recipe kind and its language-specific script builders."""
    _REGISTRY[kind] = (factory, build_python, build_javascript)


def recipe_for_kind(kind: str, overrides: dict[str, Any] | None = None) -> SignatureRecipe | None:
    """Return a :class:`SignatureRecipe` for *kind*, or ``None`` when unknown.

    Unsafe override values are dropped (defaults used) — callers that need a
    recoverable error for the draft tool should call
    :func:`validate_signature_overrides` first.
    """
    entry = _REGISTRY.get((kind or "").strip())
    if entry is None:
        return None
    factory, _py, _js = entry
    return factory(_safe_overrides(overrides or {}))


def _safe_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Copy override keys, dropping values that fail the safety patterns."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _OVERRIDE_KEYS:
            # Non-name fields (other than kind) are ignored by factories today.
            continue
        text = str(value or "").strip()
        if not text:
            continue
        if key in ("signature_header", "key_header"):
            if is_safe_header_name(text):
                out[key] = text
        elif is_safe_var_name(text):
            out[key] = text
    return out


def known_recipe_kinds() -> tuple[str, ...]:
    """Return the registered recipe kind identifiers."""
    return tuple(sorted(_REGISTRY))


def recipe_variables(recipe: SignatureRecipe) -> list[dict[str, Any]]:
    """Return empty-value collection variable rows for the recipe credentials."""
    rows: list[dict[str, Any]] = [
        {
            "key": recipe.key_var,
            "value": "",
            "enabled": True,
            "type": "default",
            "description": "API key used by the signature pre-request script",
        },
        {
            "key": recipe.secret_var,
            "value": "",
            "enabled": True,
            "type": "default",
            "description": "Shared secret used by the signature pre-request script",
        },
    ]
    return rows


def build_signing_script(
    recipe: SignatureRecipe,
    language: str | None = None,
) -> str:
    """Return the reviewed pre-request script for *recipe* in *language*."""
    entry = _REGISTRY.get(recipe.kind)
    if entry is None:
        return ""
    _factory, build_python, build_javascript = entry
    lang = (language or draft_script_language() or "python").strip().lower()
    if lang in ("javascript", "typescript", "js", "ts"):
        return build_javascript(recipe).strip() + "\n"
    return build_python(recipe).strip() + "\n"


def _str_field(raw: dict[str, Any], key: str, default: str) -> str:
    """Return a non-empty string override or *default*.

    Callers must pass already-sanitized *raw* (see :func:`_safe_overrides`).
    """
    value = str(raw.get(key) or "").strip()
    return value or default


__all__ = [
    "SignatureRecipe",
    "_str_field",
    "build_signing_script",
    "is_safe_header_name",
    "is_safe_var_name",
    "known_recipe_kinds",
    "recipe_for_kind",
    "recipe_variables",
    "register_recipe",
    "sanitize_header_name",
    "sanitize_var_name",
    "validate_signature_overrides",
]
