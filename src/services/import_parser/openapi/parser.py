"""Detect and load OpenAPI 3.x / Swagger 2.0 documents (JSON or YAML)."""

from __future__ import annotations

import json
import logging
from typing import Any

from services.import_parser.models import ImportResult
from services.import_parser.openapi.mapping import build_collection_from_openapi

logger = logging.getLogger(__name__)


def detect_openapi(data: dict[str, Any]) -> bool:
    """Return True when *data* looks like OpenAPI 3 or Swagger 2."""
    if not isinstance(data, dict):
        return False
    if "openapi" in data and isinstance(data.get("paths"), dict):
        return True
    swagger = data.get("swagger")
    return (
        swagger is not None and str(swagger).startswith("2") and isinstance(data.get("paths"), dict)
    )


def _loads_json_or_yaml(text: str) -> dict[str, Any] | None:
    """Parse JSON or YAML into a dict; return None on failure."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    try:
        import yaml

        data = yaml.safe_load(stripped)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("YAML parse failed for OpenAPI candidate", exc_info=True)
        return None


def load_openapi_text(text: str) -> ImportResult | None:
    """Parse *text* as OpenAPI/Swagger when detected; else return None."""
    data = _loads_json_or_yaml(text)
    if data is None or not detect_openapi(data):
        return None
    return parse_openapi_document(data)


def parse_openapi_document(data: dict[str, Any]) -> ImportResult:
    """Convert an OpenAPI/Swagger document dict into an :class:`ImportResult`."""
    warnings: list[str] = []
    try:
        collection = build_collection_from_openapi(data, warnings)
    except Exception as exc:
        logger.exception("OpenAPI parse failed")
        return ImportResult(
            collections=[],
            environments=[],
            errors=[f"Failed to parse OpenAPI document: {exc}"],
        )
    return ImportResult(collections=[collection], environments=[], errors=list(warnings))
