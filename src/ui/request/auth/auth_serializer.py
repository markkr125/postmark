"""Auth field serialisation — load/save between Postman dicts and UI widgets.

Uses the :data:`AUTH_FIELD_SPECS` registry from :mod:`auth_pages`
so that adding a new auth type requires **zero** changes here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QLineEdit, QTextEdit,
                               QWidget)

from ui.request.auth.auth_field_specs import AUTH_FIELD_SPECS


def load_auth_fields(
    auth_type: str,
    widgets: dict[str, QWidget],
    entries: list[dict],
) -> None:
    """Populate *widgets* from a Postman key-value *entries* list.

    Each entry is ``{"key": "<name>", "value": "<val>", ...}``.
    The *auth_type* selects the matching :class:`FieldSpec` list so
    that combo-box mappings and defaults are applied correctly.
    """
    specs = AUTH_FIELD_SPECS.get(auth_type, ())
    entry_map: dict[str, object] = {
        e["key"]: e.get("value", "") for e in entries if isinstance(e, dict)
    }
    for spec in specs:
        widget = widgets.get(spec.key)
        if widget is None:
            continue
        raw = entry_map.get(spec.key, spec.default)
        # Normalise booleans coming from Postman JSON
        if isinstance(raw, bool):
            value = "true" if raw else "false"
        elif raw is None:
            value = ""
        else:
            value = str(raw)

        if spec.kind == "combo" and isinstance(widget, QComboBox):
            display = spec.combo_map.get(value, value) if spec.combo_map else value
            widget.setCurrentText(display)
        elif spec.kind == "checkbox" and isinstance(widget, QCheckBox):
            widget.setChecked(value == "true")
        elif spec.kind == "textarea" and isinstance(widget, QTextEdit):
            widget.setPlainText(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(value)


def get_auth_fields(
    auth_type: str,
    widgets: dict[str, QWidget],
) -> list[dict]:
    """Serialise *widgets* into a Postman key-value entry list.

    Returns a list of ``{"key": ..., "value": ..., "type": "string"}``
    dicts ready for embedding in the auth configuration dict.
    """
    specs = AUTH_FIELD_SPECS.get(auth_type, ())
    result: list[dict] = []
    for spec in specs:
        widget = widgets.get(spec.key)
        if widget is None:
            continue

        if spec.kind == "combo" and isinstance(widget, QComboBox):
            if spec.combo_map:
                reverse = {v: k for k, v in spec.combo_map.items()}
                raw_value: str | bool = reverse.get(widget.currentText(), widget.currentText())
            else:
                raw_value = widget.currentText()
        elif spec.kind == "checkbox" and isinstance(widget, QCheckBox):
            raw_value = "true" if widget.isChecked() else "false"
        elif spec.kind == "textarea" and isinstance(widget, QTextEdit):
            raw_value = widget.toPlainText()
        elif isinstance(widget, QLineEdit):
            raw_value = widget.text()
        else:
            raw_value = ""

        # Convert "true"/"false" back to Python bools for Postman compat
        if spec.save_as_bool and isinstance(raw_value, str) and raw_value in ("true", "false"):
            result.append({"key": spec.key, "value": raw_value == "true", "type": "string"})
        else:
            result.append({"key": spec.key, "value": raw_value, "type": "string"})
    return result
    return result
