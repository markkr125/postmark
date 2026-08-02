"""OpenAPI ``securitySchemes`` / ``security`` → auth, signature recipes, notes.

Conservative rules:
- Hotelbeds-style ``apiKey`` + signature header pair → named SHA-256 recipe.
- Plain ``apiKey`` / ``http basic`` / ``http bearer`` → collection auth + vars.
- Expedia-style required ``Authorization`` + ``apikey`` with **no** schemes →
  variables + description note, **no** fabricated signing script.
- oauth2 / openIdConnect / mutualTLS / multi-alternative → description note only.
- Combined (AND) non-signature schemes → description note listing them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.ai.chat.tools.collection_draft.config import draft_script_language
from services.ai.chat.tools.collection_draft.recipes import (
    SignatureRecipe,
    build_signing_script,
    recipe_for_kind,
    recipe_variables,
    sanitize_header_name,
)
from services.import_parser.openapi.resolve import resolve_ref

_SIG_DESC_RE = re.compile(r"signature|sha[- ]?256|hmac", re.IGNORECASE)
# Plan §2b: Authorization description must hint at signing / external docs.
_AUTH_HINT_RE = re.compile(
    r"signature|hmac|signed|auth|external|document|docs?\b|https?://",
    re.IGNORECASE,
)
_APIKEY_NAME_RE = re.compile(r"^(api[-_]?key|apikey|x-api-key)$", re.IGNORECASE)
_DOC_URL_RE = re.compile(r"https?://[^\s)>\"]+", re.IGNORECASE)
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})

UNSPECIFIED_SIGNATURE_NOTE = "**Custom signature auth — algorithm not specified in this spec"


@dataclass
class OpenApiSecurityResult:
    """Auth, variables, optional signing events, and description notes."""

    auth: dict[str, Any] | None = None
    variables: list[dict[str, Any]] = field(default_factory=list)
    events: dict[str, str] | None = None
    description_notes: list[str] = field(default_factory=list)


def apply_openapi_security(
    data: dict[str, Any],
    warnings: list[str],
) -> OpenApiSecurityResult:
    """Map OpenAPI security into Postmark auth / signature / description notes."""
    schemes = _security_schemes(data, warnings)
    security = data.get("security")

    # Multi-alternative OR (several requirement objects) → note only; never guess.
    if isinstance(security, list) and len(security) > 1:
        names: list[str] = []
        for req in security:
            if isinstance(req, dict):
                names.extend(str(k) for k in req)
        note = (
            "**Multiple alternative security requirements** — "
            f"schemes {sorted(set(names))}; configure auth manually."
        )
        return OpenApiSecurityResult(description_notes=[note])

    preferred = _preferred_scheme_names(data)
    if not preferred:
        preferred = _preferred_scheme_names_from_operations(data)

    # 1. Named signature pair (Hotelbeds Api-key + X-Signature).
    pair = _detect_signature_pair(schemes, preferred)
    if pair is not None:
        return _result_from_signature_recipe(pair)

    # 2. Declared schemes — map first usable, or note conservative types.
    if schemes:
        return _result_from_schemes(schemes, preferred, warnings)

    # 3. No schemes — look for Expedia-style required Authorization + apikey.
    unspecified = _detect_unspecified_signature(data, warnings)
    if unspecified is not None:
        return unspecified

    return OpenApiSecurityResult()


def _security_schemes(
    data: dict[str, Any],
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    """Return resolved local security scheme definitions keyed by name."""
    raw: dict[str, Any] = {}
    if "openapi" in data:
        components = data.get("components")
        if isinstance(components, dict) and isinstance(components.get("securitySchemes"), dict):
            raw = components["securitySchemes"]
    elif isinstance(data.get("securityDefinitions"), dict):
        raw = data["securityDefinitions"]
    out: dict[str, dict[str, Any]] = {}
    for name, scheme in raw.items():
        resolved = resolve_ref(data, scheme, warnings)
        if isinstance(resolved, dict):
            out[str(name)] = resolved
    return out


def _preferred_scheme_names(data: dict[str, Any]) -> list[str]:
    """Return scheme names from the first root ``security`` requirement object."""
    security = data.get("security")
    if not isinstance(security, list) or not security:
        return []
    first = security[0]
    if isinstance(first, dict) and first:
        return [str(k) for k in first]
    return []


def _preferred_scheme_names_from_operations(data: dict[str, Any]) -> list[str]:
    """Fall back to the first non-empty per-operation ``security`` requirement.

    Root ``security`` is preferred when present; this covers specs that only
    declare schemes on individual operations.
    """
    paths = data.get("paths")
    if not isinstance(paths, dict):
        return []
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            security = operation.get("security")
            if not isinstance(security, list) or not security:
                continue
            # Per-op multi-alternative: skip (too ambiguous at collection level).
            if len(security) > 1:
                continue
            first = security[0]
            if isinstance(first, dict) and first:
                return [str(k) for k in first]
    return []


def _detect_signature_pair(
    schemes: dict[str, dict[str, Any]],
    preferred: list[str],
) -> SignatureRecipe | None:
    """Detect apiKey + signature-header pair matching the Hotelbeds pattern."""
    if len(schemes) < 2:
        return None

    def _scan(
        names: list[str],
    ) -> tuple[
        dict[str, Any] | None,
        dict[str, Any] | None,
        str,
        str,
    ]:
        key_scheme: dict[str, Any] | None = None
        sig_scheme: dict[str, Any] | None = None
        key_header = "Api-key"
        sig_header = "X-Signature"
        for name in names:
            scheme = schemes.get(name)
            if not isinstance(scheme, dict):
                continue
            stype = str(scheme.get("type") or "").lower()
            if stype != "apikey":
                continue
            if str(scheme.get("in") or "header").lower() != "header":
                continue
            header_name = sanitize_header_name(
                str(scheme.get("name") or "").strip(),
                "",
            )
            desc = str(scheme.get("description") or "")
            header_for_match = str(scheme.get("name") or "").strip()
            if _SIG_DESC_RE.search(desc) or _SIG_DESC_RE.search(header_for_match):
                sig_scheme = scheme
                sig_header = header_name or "X-Signature"
            elif key_scheme is None:
                key_scheme = scheme
                key_header = header_name or "Api-key"
        return key_scheme, sig_scheme, key_header, sig_header

    candidates = preferred if len(preferred) >= 2 else list(schemes.keys())
    key_scheme, sig_scheme, key_header, sig_header = _scan(candidates)

    # Full scan when the preferred/candidate pass did not yield a complete pair.
    # Always reset header names so a partial first pass cannot leak stale values.
    if key_scheme is None or sig_scheme is None:
        key_scheme, sig_scheme, key_header, sig_header = _scan(list(schemes.keys()))

    if key_scheme is None or sig_scheme is None:
        return None
    return recipe_for_kind(
        "sha256_apikey_secret_timestamp",
        {
            "key_header": key_header,
            "signature_header": sig_header,
            "key_var": "apiKey",
            "secret_var": "secret",
        },
    )


def _result_from_signature_recipe(recipe: SignatureRecipe) -> OpenApiSecurityResult:
    """Attach a reviewed signing script + credential variables (no auth tab)."""
    language = draft_script_language()
    script = build_signing_script(recipe, language)
    events: dict[str, str] = {
        "language": language,
        "pre_language": language,
        "test_language": language,
        "pre_request": script,
    }
    return OpenApiSecurityResult(
        auth=None,
        variables=recipe_variables(recipe),
        events=events,
        description_notes=[
            f"**Signature auth** — pre-request script from recipe `{recipe.kind}` "
            f"({recipe.notes}). Set `{{{{apiKey}}}}` and `{{{{secret}}}}`."
        ],
    )


def _result_from_schemes(
    schemes: dict[str, dict[str, Any]],
    preferred: list[str],
    warnings: list[str],
) -> OpenApiSecurityResult:
    """Map plain apiKey/basic/bearer, or note oauth2 / AND combinations."""
    # AND of multiple non-signature schemes → note (do not silently drop extras).
    if len(preferred) > 1:
        return OpenApiSecurityResult(
            description_notes=[
                "**Combined security requirements** — "
                f"schemes {preferred}; configure auth manually "
                "(OpenAPI import maps a single simple scheme, or a known "
                "signature-header pair)."
            ]
        )

    name = preferred[0] if preferred and preferred[0] in schemes else next(iter(schemes.keys()))
    scheme = schemes.get(name)
    if not isinstance(scheme, dict):
        return OpenApiSecurityResult()

    stype = str(scheme.get("type") or "").lower()
    if stype in ("oauth2", "openidconnect", "mutualtls"):
        return OpenApiSecurityResult(
            description_notes=[
                f"**{stype} security scheme** `{name}` — configure auth manually; "
                "OpenAPI import does not set up token flows."
            ]
        )

    if stype == "apikey":
        key_name = sanitize_header_name(str(scheme.get("name") or ""), "X-Api-Key")
        location = str(scheme.get("in") or "header")
        if location.lower() not in ("header", "query", "cookie"):
            location = "header"
        return OpenApiSecurityResult(
            auth={
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": key_name, "type": "string"},
                    {"key": "value", "value": "{{apiKey}}", "type": "string"},
                    {"key": "in", "value": location, "type": "string"},
                ],
            },
            variables=[
                {
                    "key": "apiKey",
                    "value": "",
                    "enabled": True,
                    "type": "default",
                    "description": f"API key for {key_name}",
                }
            ],
        )

    if stype == "http":
        http_scheme = str(scheme.get("scheme") or "").lower()
        if http_scheme == "bearer":
            return OpenApiSecurityResult(
                auth={
                    "type": "bearer",
                    "bearer": [{"key": "token", "value": "{{bearerToken}}", "type": "string"}],
                },
                variables=[
                    {
                        "key": "bearerToken",
                        "value": "",
                        "enabled": True,
                        "type": "default",
                        "description": "Bearer token",
                    }
                ],
            )
        if http_scheme == "basic":
            return OpenApiSecurityResult(
                auth={
                    "type": "basic",
                    "basic": [
                        {"key": "username", "value": "{{username}}", "type": "string"},
                        {"key": "password", "value": "{{password}}", "type": "string"},
                    ],
                },
                variables=[
                    {
                        "key": "username",
                        "value": "",
                        "enabled": True,
                        "type": "default",
                        "description": "Basic auth username",
                    },
                    {
                        "key": "password",
                        "value": "",
                        "enabled": True,
                        "type": "default",
                        "description": "Basic auth password",
                    },
                ],
            )

    if stype == "basic":
        return OpenApiSecurityResult(
            auth={
                "type": "basic",
                "basic": [
                    {"key": "username", "value": "{{username}}", "type": "string"},
                    {"key": "password", "value": "{{password}}", "type": "string"},
                ],
            },
            variables=[
                {
                    "key": "username",
                    "value": "",
                    "enabled": True,
                    "type": "default",
                },
                {
                    "key": "password",
                    "value": "",
                    "enabled": True,
                    "type": "default",
                },
            ],
        )

    warnings.append(f"Unsupported security scheme type for collection auth: {stype!r}")
    return OpenApiSecurityResult(
        description_notes=[f"**Unsupported security scheme** `{name}` ({stype})."]
    )


def _detect_unspecified_signature(
    data: dict[str, Any],
    warnings: list[str],
) -> OpenApiSecurityResult | None:
    """Detect required Authorization + apikey (header or query) with no schemes."""
    has_auth = False
    has_apikey = False
    doc_link = ""
    paths = data.get("paths")
    if not isinstance(paths, dict):
        return None

    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        shared = path_item.get("parameters")
        shared_list = shared if isinstance(shared, list) else []
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            params = list(shared_list)
            op_params = operation.get("parameters")
            if isinstance(op_params, list):
                params.extend(op_params)
            for raw in params:
                param = resolve_ref(data, raw, warnings)
                if not isinstance(param, dict):
                    continue
                where = str(param.get("in") or "").lower()
                if where not in ("header", "query"):
                    continue
                if not bool(param.get("required")):
                    continue
                name = str(param.get("name") or "").strip()
                desc = str(param.get("description") or "")
                if (
                    where == "header"
                    and name.lower() == "authorization"
                    and (_AUTH_HINT_RE.search(desc) or _DOC_URL_RE.search(desc))
                ):
                    has_auth = True
                    match = _DOC_URL_RE.search(desc)
                    if match:
                        doc_link = match.group(0)
                if _APIKEY_NAME_RE.match(name):
                    has_apikey = True
        if has_auth and has_apikey:
            break

    if not (has_auth and has_apikey):
        return None

    note = UNSPECIFIED_SIGNATURE_NOTE
    if doc_link:
        note += f"; see {doc_link}"
    note += " — configure a named signature recipe or add a pre-request script manually**."
    return OpenApiSecurityResult(
        auth=None,
        events=None,
        variables=[
            {
                "key": "apiKey",
                "value": "",
                "enabled": True,
                "type": "default",
                "description": "API key (algorithm not specified in this OpenAPI)",
            },
            {
                "key": "secret",
                "value": "",
                "enabled": True,
                "type": "default",
                "description": "Shared secret (algorithm not specified in this OpenAPI)",
            },
            {
                "key": "signature",
                "value": "",
                "enabled": True,
                "type": "default",
                "description": "Computed signature header value (fill manually or via script)",
            },
        ],
        description_notes=[note],
    )


def merge_description(base: str | None, notes: list[str]) -> str | None:
    """Append security notes to an OpenAPI info description."""
    parts: list[str] = []
    if base and str(base).strip():
        parts.append(str(base).strip())
    for note in notes:
        text = note.strip()
        if text and text not in parts:
            parts.append(text)
    if not parts:
        return None
    return "\n\n".join(parts)


def merge_variables(
    base: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge variable rows by key (base wins for existing keys)."""
    by_key: dict[str, dict[str, Any]] = {}
    for row in base:
        key = str(row.get("key") or "").strip()
        if key:
            by_key[key] = dict(row)
    for row in extra:
        key = str(row.get("key") or "").strip()
        if key and key not in by_key:
            by_key[key] = dict(row)
    return list(by_key.values())


__all__ = [
    "UNSPECIFIED_SIGNATURE_NOTE",
    "OpenApiSecurityResult",
    "apply_openapi_security",
    "merge_description",
    "merge_variables",
]
