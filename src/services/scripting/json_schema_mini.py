"""Minimal JSON Schema validator for ``pm.expect(...).jsonSchema()`` parity."""

from __future__ import annotations

from typing import Any


def validate(data: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate *data* against a subset JSON Schema. Returns ``(ok, errors)``."""
    errors: list[str] = []
    _validate_value(data, schema, path="", errors=errors)
    return (len(errors) == 0, errors)


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
    if isinstance(value, int | float) and not isinstance(value, bool):
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
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                _validate_value(
                    value[key], sub, path=f"{path}.{key}" if path else key, errors=errors
                )


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True
