"""OpenAPI response/request ``examples`` import → saved responses.

The Hotelbeds Booking API spec (and many others) documents named examples on
request and response media types. These must survive import as saved
responses on each request — including the request snapshot, so the Request
Body tab shows what produced them.
"""

from __future__ import annotations

from typing import Any

from services.import_parser.openapi import parse_openapi_document


def _first_request(collection: dict[str, Any]) -> dict[str, Any]:
    """Return the first request leaf in a parsed collection tree."""
    stack: list[dict[str, Any]] = list(collection.get("items") or [])
    while stack:
        node = stack.pop(0)
        if node.get("type") == "request":
            return node
        stack.extend(node.get("children") or [])
    raise AssertionError("no request in parsed collection")


def _hotelbeds_style_doc() -> dict[str, Any]:
    """Compact doc mirroring the Hotelbeds Booking API examples layout."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Hotel Booking API"},
        "servers": [{"url": "https://api.test.hotelbeds.com/hotel-api/1.0"}],
        "paths": {
            "/hotels": {
                "post": {
                    "tags": ["Availability"],
                    "summary": "Availability",
                    "operationId": "availability",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/availabilityRQ"},
                                "examples": {
                                    "Ex1": {
                                        "summary": "Search one room (by hotel code list)",
                                        "value": {
                                            "stay": {
                                                "checkIn": "2024-06-15",
                                                "checkOut": "2024-06-16",
                                            },
                                            "occupancies": [{"rooms": 1, "adults": 2}],
                                            "hotels": {"hotel": [123223]},
                                        },
                                    },
                                    "Ex2": {
                                        "summary": "Search one room (by geolocation)",
                                        "value": {
                                            "stay": {
                                                "checkIn": "2024-06-15",
                                                "checkOut": "2024-06-16",
                                            },
                                            "geolocation": {
                                                "latitude": 41.38,
                                                "longitude": 2.17,
                                                "radius": 20,
                                                "unit": "km",
                                            },
                                        },
                                    },
                                },
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Successful operation",
                            "content": {
                                "application/json": {
                                    "examples": {
                                        "Ex1": {
                                            "summary": "Search one room (by hotel code list)",
                                            "value": {
                                                "auditData": {"processTime": "158"},
                                                "hotels": {"hotels": [{"code": 123223}]},
                                            },
                                        },
                                        "Ex2": {
                                            "summary": "No availability",
                                            "value": {
                                                "auditData": {"processTime": "21"},
                                                "hotels": {},
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Bad request",
                            "content": {
                                "application/json": {"example": {"error": "Invalid request body"}}
                            },
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "availabilityRQ": {
                    "type": "object",
                    "properties": {"stay": {"type": "object"}},
                }
            }
        },
    }


def _parse_request(doc: dict[str, Any]) -> dict[str, Any]:
    """Parse *doc* and return its first request."""
    result = parse_openapi_document(doc)
    assert result["collections"], result
    return _first_request(dict(result["collections"][0]))


def test_response_named_examples_become_saved_responses() -> None:
    """OAS3 named response examples import as saved responses with code/status."""
    request = _parse_request(_hotelbeds_style_doc())
    saved = request.get("saved_responses") or []
    names = [row["name"] for row in saved]
    assert "Search one room (by hotel code list)" in names
    assert "No availability" in names
    by_name = {row["name"]: row for row in saved}
    ex1 = by_name["Search one room (by hotel code list)"]
    assert ex1["code"] == 200
    assert ex1["status"] == "OK"
    assert ex1["preview_language"] == "json"
    assert "123223" in (ex1["body"] or "")
    # Singular `example` on the 400 media type also lands.
    assert "Example (400)" in names or "Example" in names
    ex400 = next(row for row in saved if row["code"] == 400)
    assert "Invalid request body" in (ex400["body"] or "")


def test_saved_response_snapshot_carries_request_body() -> None:
    """Each response example's Request Body tab mirrors the request example."""
    request = _parse_request(_hotelbeds_style_doc())
    saved = request.get("saved_responses") or []
    assert saved
    snapshot = saved[0].get("original_request") or {}
    assert snapshot.get("method") == "POST"
    assert "hotels" in str((snapshot.get("url") or {}).get("raw"))
    body = snapshot.get("body") or {}
    assert body.get("mode") == "raw"
    assert "checkIn" in str(body.get("raw"))
    assert (body.get("options") or {}).get("raw", {}).get("language") == "json"


def test_first_request_example_is_body_extras_become_variants() -> None:
    """Multiple request examples: first fills the body, extras are kept as variants."""
    request = _parse_request(_hotelbeds_style_doc())
    assert "checkIn" in (request.get("body") or "")
    assert "123223" in (request.get("body") or "")
    saved = request.get("saved_responses") or []
    variants = [row for row in saved if row["name"].endswith("— request")]
    assert len(variants) == 1
    variant = variants[0]
    assert "geolocation" in variant["name"]
    # A request variant has no response body of its own; the variant payload
    # lives in its request snapshot.
    assert variant["body"] is None
    snap_body = (variant.get("original_request") or {}).get("body") or {}
    assert "latitude" in str(snap_body.get("raw"))


def test_swagger2_response_examples_become_saved_responses() -> None:
    """Swagger 2 ``examples: {mime: payload}`` also maps to saved responses."""
    doc = {
        "swagger": "2.0",
        "info": {"title": "Legacy API"},
        "host": "api.example.com",
        "basePath": "/v1",
        "paths": {
            "/ping": {
                "get": {
                    "summary": "Ping",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "examples": {"application/json": {"pong": True}},
                        }
                    },
                }
            }
        },
    }
    request = _parse_request(doc)
    saved = request.get("saved_responses") or []
    assert len(saved) == 1
    assert saved[0]["code"] == 200
    assert saved[0]["status"] == "OK"
    assert '"pong": true' in (saved[0]["body"] or "")
    assert saved[0]["preview_language"] == "json"
    assert (saved[0].get("original_request") or {}).get("method") == "GET"


def test_operation_without_examples_has_no_saved_responses() -> None:
    """Operations without examples must not grow phantom saved responses."""
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Plain API"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List items",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    request = _parse_request(doc)
    assert not request.get("saved_responses")
