"""OpenAPI securitySchemes / unspecified-signature import behaviour."""

from __future__ import annotations

from typing import Any

from services.import_parser.openapi import parse_openapi_document
from services.import_parser.openapi.security import UNSPECIFIED_SIGNATURE_NOTE


def _collection(doc: dict[str, Any]) -> dict[str, Any]:
    """Parse *doc* and return the first collection as a plain dict."""
    result = parse_openapi_document(doc)
    assert result["collections"], result
    return dict(result["collections"][0])


def test_hotelbeds_signature_pair_emits_signing_script() -> None:
    """Api-key + X-Signature securitySchemes → recipe pre-request + variables."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Hotelbeds Booking"},
        "servers": [{"url": "https://api.test.hotelbeds.com"}],
        "security": [{"Apikey": [], "Xsignature": []}],
        "components": {
            "securitySchemes": {
                "Apikey": {
                    "type": "apiKey",
                    "name": "Api-key",
                    "in": "header",
                },
                "Xsignature": {
                    "type": "apiKey",
                    "name": "X-Signature",
                    "in": "header",
                    "description": "SHA256 encoding signature",
                },
            }
        },
        "paths": {
            "/hotel-api/1.0/status": {
                "get": {
                    "summary": "Status",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    events = coll.get("events") or {}
    assert isinstance(events, dict)
    pre = str(events.get("pre_request") or "")
    assert "sha256_apikey_secret_timestamp" in pre or "hashlib_sha256" in pre
    assert "X-Signature" in pre
    assert "Api-key" in pre
    keys = {str(v.get("key")) for v in (coll.get("variables") or []) if isinstance(v, dict)}
    assert "apiKey" in keys
    assert "secret" in keys
    # Signature recipe owns auth via script — do not also set apikey auth tab.
    assert coll.get("auth") is None


def test_expedia_unspecified_signature_note_no_script() -> None:
    """Required Authorization + apikey without schemes → vars + note, no script."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Expedia Rapid"},
        "paths": {
            "/v3/properties/content": {
                "get": {
                    "summary": "Content",
                    "parameters": [
                        {
                            "name": "Authorization",
                            "in": "header",
                            "required": True,
                            "description": (
                                "Signature auth; see https://developers.expediagroup.com/docs/rapid"
                            ),
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "apikey",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    description = str(coll.get("description") or "")
    assert UNSPECIFIED_SIGNATURE_NOTE in description
    assert "algorithm not specified" in description
    assert "https://developers.expediagroup.com" in description
    events = coll.get("events")
    assert not events or not (isinstance(events, dict) and events.get("pre_request"))
    keys = {str(v.get("key")) for v in (coll.get("variables") or []) if isinstance(v, dict)}
    assert keys >= {"apiKey", "secret", "signature"}
    assert coll.get("auth") is None


def test_basic_auth_scheme() -> None:
    """Http basic → collection basic auth + username/password variables."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Basic API"},
        "components": {
            "securitySchemes": {
                "BasicAuth": {"type": "http", "scheme": "basic"},
            }
        },
        "security": [{"BasicAuth": []}],
        "paths": {
            "/me": {
                "get": {
                    "summary": "Me",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    auth = coll.get("auth") or {}
    assert auth.get("type") == "basic"
    keys = {str(v.get("key")) for v in (coll.get("variables") or []) if isinstance(v, dict)}
    assert "username" in keys
    assert "password" in keys


def test_bearer_auth_scheme() -> None:
    """Http bearer → collection bearer auth + bearerToken variable."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Bearer API"},
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"},
            }
        },
        "security": [{"BearerAuth": []}],
        "paths": {
            "/me": {
                "get": {
                    "summary": "Me",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    auth = coll.get("auth") or {}
    assert auth.get("type") == "bearer"
    keys = {str(v.get("key")) for v in (coll.get("variables") or []) if isinstance(v, dict)}
    assert "bearerToken" in keys


def test_oauth2_description_note_no_auth() -> None:
    """oauth2 → description note only; no half-configured auth."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "OAuth API"},
        "components": {
            "securitySchemes": {
                "OAuth2": {
                    "type": "oauth2",
                    "flows": {
                        "clientCredentials": {
                            "tokenUrl": "https://example.com/token",
                            "scopes": {},
                        }
                    },
                }
            }
        },
        "security": [{"OAuth2": []}],
        "paths": {
            "/data": {
                "get": {
                    "summary": "Data",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    assert coll.get("auth") is None
    description = str(coll.get("description") or "")
    assert "oauth2" in description.lower()
    assert "manually" in description.lower()


def test_multi_alternative_security_note_no_recipe() -> None:
    """OR-style security alternatives get a note — never a guessed signature pair."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Alt Auth"},
        "components": {
            "securitySchemes": {
                "Apikey": {"type": "apiKey", "name": "Api-key", "in": "header"},
                "Xsignature": {
                    "type": "apiKey",
                    "name": "X-Signature",
                    "in": "header",
                    "description": "SHA256 encoding signature",
                },
            }
        },
        "security": [{"Apikey": []}, {"Xsignature": []}],
        "paths": {
            "/x": {
                "get": {
                    "summary": "X",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    assert "Multiple alternative" in str(coll.get("description") or "")
    events = coll.get("events")
    assert not events or not (isinstance(events, dict) and events.get("pre_request"))
    assert coll.get("auth") is None


def test_and_combined_non_signature_schemes_note() -> None:
    """AND of basic+apiKey (non-signature) → note; do not drop the second scheme."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "AND Auth"},
        "components": {
            "securitySchemes": {
                "BasicAuth": {"type": "http", "scheme": "basic"},
                "ApiKey": {"type": "apiKey", "name": "X-Api-Key", "in": "header"},
            }
        },
        "security": [{"BasicAuth": [], "ApiKey": []}],
        "paths": {
            "/x": {
                "get": {
                    "summary": "X",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    description = str(coll.get("description") or "")
    assert "Combined security" in description
    assert coll.get("auth") is None


def test_plain_bearer_plus_apikey_no_false_signature_note() -> None:
    """Required Authorization without signing hints must not trigger Expedia path."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Bearer + key"},
        "paths": {
            "/me": {
                "get": {
                    "summary": "Me",
                    "parameters": [
                        {
                            "name": "Authorization",
                            "in": "header",
                            "required": True,
                            "description": "Bearer token",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "apikey",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    description = str(coll.get("description") or "")
    assert UNSPECIFIED_SIGNATURE_NOTE not in description
    keys = {str(v.get("key")) for v in (coll.get("variables") or []) if isinstance(v, dict)}
    assert "signature" not in keys


def test_expedia_apikey_in_query_detected() -> None:
    """Required Authorization + query apikey still surfaces the unspecified note."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Query key"},
        "paths": {
            "/v1/x": {
                "get": {
                    "summary": "X",
                    "parameters": [
                        {
                            "name": "Authorization",
                            "in": "header",
                            "required": True,
                            "description": "Signature; see https://example.com/signing",
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "api_key",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    assert UNSPECIFIED_SIGNATURE_NOTE in str(coll.get("description") or "")
    assert "https://example.com/signing" in str(coll.get("description") or "")


def test_operation_level_security_used_when_root_missing() -> None:
    """Per-operation security is used when the document has no root security."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Op security"},
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"},
            }
        },
        "paths": {
            "/me": {
                "get": {
                    "summary": "Me",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    auth = coll.get("auth") or {}
    assert auth.get("type") == "bearer"


def test_hostile_signature_header_name_sanitized() -> None:
    """Unsafe scheme header names fall back to defaults in the generated script."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Hostile"},
        "security": [{"Apikey": [], "Xsignature": []}],
        "components": {
            "securitySchemes": {
                "Apikey": {
                    "type": "apiKey",
                    "name": 'Api-key"; evil()',
                    "in": "header",
                },
                "Xsignature": {
                    "type": "apiKey",
                    "name": "X-Signature",
                    "in": "header",
                    "description": "SHA256 encoding signature",
                },
            }
        },
        "paths": {
            "/x": {
                "get": {
                    "summary": "X",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    events = coll.get("events") or {}
    pre = str(events.get("pre_request") or "")
    assert "hashlib_sha256" in pre or "CryptoJS.SHA256" in pre
    assert "evil()" not in pre
    assert "Api-key" in pre


def test_unspecified_signature_via_parameter_refs() -> None:
    """$ref'd Authorization + apikey parameters still trigger the unspecified note."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Ref params"},
        "components": {
            "parameters": {
                "AuthHeader": {
                    "name": "Authorization",
                    "in": "header",
                    "required": True,
                    "description": "Signature auth; see https://example.com/docs",
                    "schema": {"type": "string"},
                },
                "ApiKeyQuery": {
                    "name": "apikey",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string"},
                },
            }
        },
        "paths": {
            "/v1/x": {
                "get": {
                    "summary": "X",
                    "parameters": [
                        {"$ref": "#/components/parameters/AuthHeader"},
                        {"$ref": "#/components/parameters/ApiKeyQuery"},
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    description = str(coll.get("description") or "")
    assert UNSPECIFIED_SIGNATURE_NOTE in description
    assert "https://example.com/docs" in description


def test_security_scheme_ref_resolves_to_bearer() -> None:
    """$ref'd securitySchemes entries resolve before auth mapping."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Ref scheme"},
        "components": {
            "securitySchemes": {
                "BearerAuth": {"$ref": "#/components/securitySchemes/BearerAuthDef"},
                "BearerAuthDef": {"type": "http", "scheme": "bearer"},
            }
        },
        "security": [{"BearerAuth": []}],
        "paths": {
            "/me": {
                "get": {
                    "summary": "Me",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    coll = _collection(doc)
    assert (coll.get("auth") or {}).get("type") == "bearer"
