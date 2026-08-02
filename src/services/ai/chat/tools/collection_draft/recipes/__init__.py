"""Reviewed signature recipes for collection drafts and OpenAPI imports.

Importing this package registers the built-in recipe kinds. Prefer the
re-exported helpers over reaching into individual modules.
"""

from __future__ import annotations

# Side-effect imports register each recipe with the base registry.
from services.ai.chat.tools.collection_draft.recipes import hmac_sha256 as _hmac_sha256
from services.ai.chat.tools.collection_draft.recipes import sha256_apikey as _sha256_apikey
from services.ai.chat.tools.collection_draft.recipes.base import (
    SignatureRecipe,
    build_signing_script,
    is_safe_header_name,
    is_safe_var_name,
    known_recipe_kinds,
    recipe_for_kind,
    recipe_variables,
    sanitize_header_name,
    sanitize_var_name,
    validate_signature_overrides,
)

# Keep module references so Ruff does not flag the register side-effects as unused.
_ = (_hmac_sha256, _sha256_apikey)

__all__ = [
    "SignatureRecipe",
    "build_signing_script",
    "is_safe_header_name",
    "is_safe_var_name",
    "known_recipe_kinds",
    "recipe_for_kind",
    "recipe_variables",
    "sanitize_header_name",
    "sanitize_var_name",
    "validate_signature_overrides",
]
