# Adding an Auth Type

How to add a new authentication type to the request editor and HTTP
send pipeline.

## Architecture

```
RequestEditorWidget
  -> _AuthMixin builds stacked pages
    -> auth_pages.py builds field form from FieldSpec
    -> auth_field_specs.py defines per-type fields
  -> get_request_data() includes auth config

HttpSendWorker
  -> auth_handler.apply_auth() injects headers/params
  -> oauth2_service.py handles OAuth 2.0 token exchange
```

## Steps

### 1. Define field specs

Add your auth type key and field definitions to
`src/ui/request/auth/auth_field_specs.py`:

```python
AUTH_FIELD_SPECS["your_auth"] = (
    FieldSpec("username", "Username", placeholder="Enter username"),
    FieldSpec("password", "Password", kind="password"),
    FieldSpec(
        "algorithm",
        "Algorithm",
        kind="combo",
        options=("SHA-256", "SHA-512"),
        default="SHA-256",
        advanced=True,
    ),
)
```

### FieldSpec Options

```python
@dataclass
class FieldSpec:
    key: str                       # Internal field name
    label: str                     # Display label
    kind: str = "text"             # text | password | combo | checkbox | textarea
    placeholder: str = ""
    options: tuple[str, ...] = ()  # Options for combo
    combo_map: dict | None = None  # Value mapping for combos
    default: str = ""
    width: int | None = None       # Fixed field width
    advanced: bool = False         # In collapsed "Advanced" section
    save_as_bool: bool = True      # Auto bool conversion
```

### 2. Register the auth type

Add your auth type to the `AUTH_TYPES` list in `auth_pages.py`:

```python
AUTH_TYPES: list[str] = [
    "Inherit auth from parent",
    "No Auth",
    "Bearer Token",
    ...
    "Your Auth Type",  # <-- add here
]
```

### 3. Add header injection

Add a handler case in `src/services/http/auth_handler.py`:

```python
def apply_auth(
    auth_data: dict[str, Any] | None,
    headers: dict[str, str],
    params: dict[str, str],
) -> None:
    ...
    elif auth_type == "your_auth":
        _apply_your_auth(entries, headers)
    ...

def _apply_your_auth(
    entries: dict[str, str],
    headers: dict[str, str],
) -> None:
    username = entries.get("username", "")
    password = entries.get("password", "")
    if username:
        # Build auth header
        headers["Authorization"] = f"YourScheme {computed_value}"
```

### 4. Write tests

Add test cases in `tests/unit/services/http/test_auth_handler.py`:

```python
class TestYourAuth:
    """Tests for Your Auth type header injection."""

    def test_apply_your_auth_basic(self) -> None:
        auth_data = {
            "type": "your_auth",
            "your_auth": [
                {"key": "username", "value": "user"},
                {"key": "password", "value": "pass"},
            ],
        }
        headers: dict[str, str] = {}
        apply_auth(auth_data, headers, {})
        assert "Authorization" in headers
```

### 5. Update instructions

1. Update `AUTH_TYPES` count in root [`AGENTS.md`](../../AGENTS.md)
2. Add the new type to the auth handler docs
3. Update the `auth_field_specs.py` reference in skills

## Serialisation Format

Auth data is stored in Postman format:

```python
{
    "type": "your_auth",
    "your_auth": [
        {"key": "username", "value": "user", "type": "string"},
        {"key": "password", "value": "secret", "type": "string"},
    ]
}
```

The `auth_serializer.py` module handles load/save between widgets
and this format.  No changes needed there unless your type has
non-standard serialisation needs.
