"""Pyodide JSON Schema mini-validator — mirrors json_schema_mini."""

from __future__ import annotations

from typing import Any


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _validate_value(value: Any, schema: dict[str, Any], *, path: str, errors: list[str]) -> None:
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path or 'root'}: not in enum")
        return
    if "type" in schema and not _type_matches(value, schema["type"]):
        errors.append(f"{path or 'root'}: expected type {schema['type']}")
        return
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            errors.append(f"{path}: minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            errors.append(f"{path}: maxLength")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: maximum")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            errors.append(f"{path}: minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: maxItems")
        items = schema.get("items")
        if items:
            for i, item in enumerate(value):
                _validate_value(item, items, path=f"{path}[{i}]", errors=errors)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                _validate_value(
                    value[key],
                    sub,
                    path=f"{path}.{key}" if path else key,
                    errors=errors,
                )


def _pm_validate_schema(data: Any, schema: dict[str, Any]) -> dict[str, Any]:
    """Validate *data* against *schema*; returns ``{ok, errors}``."""
    errors: list[str] = []
    _validate_value(data, schema or {}, path="", errors=errors)
    return {"ok": len(errors) == 0, "errors": errors}
