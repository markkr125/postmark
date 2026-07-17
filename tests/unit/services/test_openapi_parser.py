"""Tests for OpenAPI / Swagger import parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from services.import_parser.models import ParsedFolder, ParsedRequest
from services.import_parser.openapi import load_openapi_text, parse_openapi_document
from services.import_parser.url_parser import fetch_and_parse_url, parse_raw_text


_OPENAPI3 = {
    "openapi": "3.0.3",
    "info": {"title": "Pets API", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "tags": ["pets"],
                "summary": "List pets",
                "operationId": "listPets",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "example": 10},
                    }
                ],
            },
            "post": {
                "tags": ["pets"],
                "summary": "Create pet",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "example": "Rex"},
                                },
                            }
                        }
                    }
                },
            },
        },
        "/pets/{petId}": {
            "get": {
                "tags": ["pets"],
                "summary": "Get pet",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            }
        },
        "/health": {
            "get": {
                "summary": "Health",
            }
        },
    },
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            }
        }
    },
    "security": [{"ApiKeyAuth": []}],
}


_SWAGGER2 = {
    "swagger": "2.0",
    "info": {"title": "Legacy API", "version": "1"},
    "host": "legacy.example.com",
    "basePath": "/api",
    "schemes": ["https"],
    "paths": {
        "/users": {
            "get": {
                "tags": ["users"],
                "summary": "List users",
                "operationId": "listUsers",
            }
        }
    },
}


class TestOpenApiParser:
    """OpenAPI 3 and Swagger 2 → ParsedCollection."""

    def test_openapi3_tags_and_base_url(self) -> None:
        """Folders follow tags; baseUrl variable is set; auth is placeholders."""
        result = parse_openapi_document(_OPENAPI3)
        assert result["errors"] == []
        assert len(result["collections"]) == 1
        coll = result["collections"][0]
        assert coll["name"] == "Pets API"
        vars_ = {v["key"]: v["value"] for v in (coll.get("variables") or [])}
        assert vars_["baseUrl"] == "https://api.example.com/v1"
        folder_names = [i["name"] for i in coll["items"] if i.get("type") == "folder"]
        assert "pets" in folder_names
        assert "Default" in folder_names
        pets = cast(ParsedFolder, next(i for i in coll["items"] if i.get("name") == "pets"))
        assert len(pets["children"]) == 3
        get_pet = cast(ParsedRequest, next(r for r in pets["children"] if r["name"] == "Get pet"))
        assert "{{petId}}" in get_pet["url"]
        assert get_pet["url"].startswith("{{baseUrl}}")
        auth = coll.get("auth") or {}
        assert auth.get("type") == "apikey"
        values = {
            e["key"]: e["value"] for e in cast(list[dict[str, Any]], auth.get("apikey") or [])
        }
        assert values["value"] == "{{apiKey}}"
        blob = json.dumps(result)
        assert "secret-token" not in blob

    def test_openapi_yaml(self) -> None:
        """YAML OpenAPI documents are accepted."""
        import yaml

        text = yaml.dump(_OPENAPI3)
        result = load_openapi_text(text)
        assert result is not None
        assert result["collections"][0]["name"] == "Pets API"

    def test_swagger2(self) -> None:
        """Swagger 2 host/basePath become baseUrl."""
        result = parse_openapi_document(_SWAGGER2)
        coll = result["collections"][0]
        assert coll["name"] == "Legacy API"
        vars_ = {v["key"]: v["value"] for v in (coll.get("variables") or [])}
        assert vars_["baseUrl"] == "https://legacy.example.com/api"
        users = cast(ParsedFolder, next(i for i in coll["items"] if i.get("name") == "users"))
        first_req = cast(ParsedRequest, users["children"][0])
        assert first_req["method"] == "GET"

    def test_local_ref_resolve(self) -> None:
        """Local component $ref for requestBody schema is resolved."""
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "Ref API"},
            "paths": {
                "/item": {
                    "post": {
                        "tags": ["items"],
                        "summary": "Create",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Item"},
                                }
                            }
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "Item": {
                        "type": "object",
                        "properties": {"id": {"type": "integer", "example": 1}},
                    }
                }
            },
        }
        result = parse_openapi_document(doc)
        items = cast(
            ParsedFolder,
            next(i for i in result["collections"][0]["items"] if i["name"] == "items"),
        )
        body = cast(ParsedRequest, items["children"][0]).get("body") or ""
        assert "1" in body

    def test_fetch_url_openapi(self) -> None:
        """fetch_and_parse_url builds a real collection from OpenAPI JSON."""
        body = json.dumps(_OPENAPI3).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_and_parse_url("https://example.com/openapi.json")
        assert len(result["collections"]) == 1
        assert result["collections"][0]["name"] == "Pets API"
        # Not a bare single-GET URL Import
        assert result["collections"][0]["name"] != "URL Import"

    def test_parse_raw_text_lone_url_fetches(self) -> None:
        """Lone URL in paste area fetches rather than creating a bare GET."""
        body = json.dumps(_OPENAPI3).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = parse_raw_text("https://example.com/openapi.json")
        assert result["collections"][0]["name"] == "Pets API"

    def test_parse_collection_file_yaml(self, tmp_path: Path) -> None:
        """``.yaml`` OpenAPI files import via parse_collection_file."""
        import yaml

        from services.import_parser import parse_collection_file

        path = tmp_path / "api.yaml"
        path.write_text(yaml.dump(_OPENAPI3), encoding="utf-8")
        result = parse_collection_file(path)
        assert result["collections"][0]["name"] == "Pets API"
