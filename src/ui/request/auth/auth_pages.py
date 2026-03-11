"""Auth-type constants, field specifications, and data-driven page builder.

Defines the ordered list of supported auth types, human-readable labels,
stacked-widget page indices, per-type :class:`FieldSpec` descriptors, and
a generic :func:`build_fields_page` that constructs a Qt form page from a
sequence of field specs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.variable_line_edit import VariableLineEdit

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Auth-type display names (stacked-widget page order)
# ---------------------------------------------------------------------------

AUTH_TYPES: tuple[str, ...] = (
    "Inherit auth from parent",
    "No Auth",
    "Bearer Token",
    "Basic Auth",
    "API Key",
    "Digest Auth",
    "OAuth 1.0",
    "OAuth 2.0",
    "Hawk Authentication",
    "AWS Signature",
    "JWT Bearer",
    "ASAP (Atlassian)",
    "NTLM Authentication",
    "Akamai EdgeGrid",
)

# Postman type key -> display name (excludes inherit / noauth)
AUTH_TYPE_LABELS: dict[str, str] = {
    "bearer": "Bearer Token",
    "basic": "Basic Auth",
    "apikey": "API Key",
    "digest": "Digest Auth",
    "oauth1": "OAuth 1.0",
    "oauth2": "OAuth 2.0",
    "hawk": "Hawk Authentication",
    "awsv4": "AWS Signature",
    "jwt": "JWT Bearer",
    "asap": "ASAP (Atlassian)",
    "ntlm": "NTLM Authentication",
    "edgegrid": "Akamai EdgeGrid",
}

# Display name -> Postman type key
AUTH_TYPE_KEYS: dict[str, str] = {v: k for k, v in AUTH_TYPE_LABELS.items()}

# Postman type key -> display name (all types including inherit / noauth)
AUTH_KEY_TO_DISPLAY: dict[str, str] = {
    "inherit": "Inherit auth from parent",
    "noauth": "No Auth",
    **AUTH_TYPE_LABELS,
}

# Order of field-based pages in the stacked widget (after inherit=0, noauth=1)
AUTH_FIELD_ORDER: tuple[str, ...] = (
    "bearer",
    "basic",
    "apikey",
    "digest",
    "oauth1",
    "oauth2",
    "hawk",
    "awsv4",
    "jwt",
    "asap",
    "ntlm",
    "edgegrid",
)

# Display name -> stacked-widget page index
AUTH_PAGE_INDEX: dict[str, int] = {
    "Inherit auth from parent": 0,
    "No Auth": 1,
}
for _i, _key in enumerate(AUTH_FIELD_ORDER, start=2):
    AUTH_PAGE_INDEX[AUTH_TYPE_LABELS[_key]] = _i

# Short description shown in the left column for each auth type
AUTH_TYPE_DESCRIPTIONS: dict[str, str] = {
    "Inherit auth from parent": (
        "This request will use the authorization configured on its parent collection or folder."
    ),
    "No Auth": "This request does not use any authorization.",
    "Bearer Token": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "Basic Auth": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "API Key": (
        "The key-value pair will be added as a header or query parameter when you send the request."
    ),
    "Digest Auth": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "OAuth 1.0": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "OAuth 2.0": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "Hawk Authentication": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "AWS Signature": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "JWT Bearer": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "ASAP (Atlassian)": (
        "The authorization header will be automatically generated when you send the request."
    ),
    "NTLM Authentication": (
        "NTLM credentials will be used for Windows authentication when you send the request."
    ),
    "Akamai EdgeGrid": (
        "The authorization header will be automatically generated when you send the request."
    ),
}


# ---------------------------------------------------------------------------
# Field specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Describes a single form field in an auth page.

    *kind* — ``"text"``, ``"password"``, ``"combo"``, or ``"textarea"``.
    *combo_map* — Postman serialised value -> combo display text.  When
    empty the display text is used as-is for both load and save.
    *save_as_bool* — When ``True`` the serialiser converts ``"true"``
    / ``"false"`` strings back to Python booleans on save.
    *advanced* — When ``True`` the field is placed under a collapsible
    "Advanced configuration" section, matching Postman's layout.
    *suffix* — Optional suffix text displayed right of the input widget
    (e.g. ``"bytes"``).
    """

    key: str
    label: str
    kind: str = "text"
    placeholder: str = ""
    options: tuple[str, ...] = ()
    combo_map: dict[str, str] = field(default_factory=dict)
    default: str = ""
    width: int | None = None
    save_as_bool: bool = False
    advanced: bool = False
    suffix: str = ""


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

_TEXTAREA_MAX_HEIGHT = 120
_INPUT_MAX_WIDTH = 360
_ADV_DESCRIPTION = (
    "Auto-generated default values are used for some of these fields unless a value is specified."
)


def _build_widget(spec: FieldSpec, on_change: Callable[[], None]) -> QWidget:
    """Create the input widget for a single :class:`FieldSpec`."""
    if spec.kind == "combo":
        w: QWidget = QComboBox()
        assert isinstance(w, QComboBox)
        w.addItems(list(spec.options))
        if spec.width:
            w.setFixedWidth(spec.width)
        else:
            w.setMaximumWidth(_INPUT_MAX_WIDTH)
        w.currentTextChanged.connect(on_change)
    elif spec.kind == "checkbox":
        w = QCheckBox(spec.label)
        w.stateChanged.connect(lambda _: on_change())
    elif spec.kind == "password":
        w = VariableLineEdit()
        w.setPlaceholderText(spec.placeholder)
        w.setEchoMode(QLineEdit.EchoMode.Password)
        w.setMaximumWidth(_INPUT_MAX_WIDTH)
        w.textChanged.connect(on_change)
    elif spec.kind == "textarea":
        w = QTextEdit()
        assert isinstance(w, QTextEdit)
        w.setPlaceholderText(spec.placeholder)
        w.setMaximumHeight(_TEXTAREA_MAX_HEIGHT)
        w.setMaximumWidth(_INPUT_MAX_WIDTH)
        w.textChanged.connect(on_change)
    else:
        w = VariableLineEdit()
        w.setPlaceholderText(spec.placeholder)
        w.setMaximumWidth(_INPUT_MAX_WIDTH)
        w.textChanged.connect(on_change)
    return w


def _add_field_row(
    form: QFormLayout,
    spec: FieldSpec,
    widget: QWidget,
) -> None:
    """Add a label + widget row to *form*, handling suffix/checkbox."""
    if spec.kind == "checkbox":
        form.addRow(widget)
        return
    lbl = QLabel(spec.label)
    lbl.setObjectName("sectionLabel")
    if spec.suffix:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(widget)
        suffix = QLabel(spec.suffix)
        suffix.setObjectName("mutedLabel")
        row.addWidget(suffix)
        row.addStretch()
        form.addRow(lbl, row)
    else:
        form.addRow(lbl, widget)


def build_fields_page(
    specs: tuple[FieldSpec, ...],
    on_change: Callable[[], None],
) -> tuple[QWidget, dict[str, QWidget]]:
    """Build a form page from *specs* with an optional advanced section.

    Returns ``(page_widget, widgets_dict)`` where *widgets_dict* maps
    each :attr:`FieldSpec.key` to the corresponding input widget.

    Primary fields appear at the top.  If any spec has ``advanced=True``,
    those fields are grouped under a collapsible "Advanced configuration"
    toggle matching Postman's layout.
    """
    primary = [s for s in specs if not s.advanced]
    advanced = [s for s in specs if s.advanced]

    inner = QWidget()
    root = QVBoxLayout(inner)
    root.setContentsMargins(16, 8, 0, 0)
    root.setSpacing(0)

    widgets: dict[str, QWidget] = {}

    # -- Primary fields ------------------------------------------------
    if primary:
        primary_form = QFormLayout()
        primary_form.setContentsMargins(0, 0, 0, 0)
        primary_form.setHorizontalSpacing(12)
        primary_form.setVerticalSpacing(10)
        primary_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for spec in primary:
            w = _build_widget(spec, on_change)
            _add_field_row(primary_form, spec, w)
            widgets[spec.key] = w
        root.addLayout(primary_form)

    # -- Advanced section (collapsible) --------------------------------
    if advanced:
        root.addSpacing(12)

        toggle = QToolButton()
        toggle.setObjectName("advancedToggle")
        toggle.setText("\u25b8 Advanced configuration")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setStyleSheet("QToolButton { border: none; font-weight: bold; font-size: 12px; }")
        root.addWidget(toggle)

        adv_container = QWidget()
        adv_layout = QVBoxLayout(adv_container)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(0)

        desc = QLabel(_ADV_DESCRIPTION)
        desc.setObjectName("mutedLabel")
        desc.setWordWrap(True)
        adv_layout.addWidget(desc)
        adv_layout.addSpacing(8)

        adv_form = QFormLayout()
        adv_form.setContentsMargins(0, 0, 0, 0)
        adv_form.setHorizontalSpacing(12)
        adv_form.setVerticalSpacing(10)
        adv_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for spec in advanced:
            w = _build_widget(spec, on_change)
            _add_field_row(adv_form, spec, w)
            widgets[spec.key] = w
        adv_layout.addLayout(adv_form)

        adv_container.setVisible(False)
        root.addWidget(adv_container)

        def _on_toggle(checked: bool) -> None:
            adv_container.setVisible(checked)
            toggle.setText(
                "\u25be Advanced configuration" if checked else "\u25b8 Advanced configuration"
            )

        toggle.toggled.connect(_on_toggle)

    root.addStretch()

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(inner)
    return scroll, widgets


def build_inherit_page() -> tuple[QWidget, QLabel]:
    """Build the *Inherit auth from parent* right-side page.

    Returns ``(page_widget, preview_label)`` so the caller can update
    the preview text as the active environment changes.
    """
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 8, 0, 0)
    preview = QLabel()
    preview.setObjectName("sectionLabel")
    preview.setWordWrap(True)
    layout.addWidget(preview)
    layout.addStretch()
    return page, preview


def build_noauth_page() -> QWidget:
    """Build the *No Auth* right-side page (empty placeholder)."""
    page = QWidget()
    return page
