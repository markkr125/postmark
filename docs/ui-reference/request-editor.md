# Request Editor

Main request composition pane with method, URL, body, and tabbed
detail sections.

Source: `src/ui/request/request_editor/`

## RequestEditorWidget

Inherits `_AuthMixin`, `_BodySearchMixin`, `_GraphQLMixin`.

### Top Bar

```
+--------+-----------------------------------+---------+
| Method | URL (VariableLineEdit)            |  Send   |
+--------+-----------------------------------+---------+
```

Method dropdown: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS.

URL input is a `VariableLineEdit` with `{{variable}}` highlighting
and hover popup.

### Tabs (6)

| Index | Tab | Content |
|-------|-----|---------|
| 0 | Params | `KeyValueTableWidget` for query parameters |
| 1 | Headers | `KeyValueTableWidget` for request headers |
| 2 | Body | Mode selector + stacked editors |
| 3 | Auth | Auth type selector + field pages (via `_AuthMixin`) |
| 4 | Description | `QTextEdit` for request documentation |
| 5 | Scripts | `QTextEdit` for pre-request/test scripts |

### Body Modes

| Index | Mode | Widget |
|-------|------|--------|
| 0 | None | Label (no body) |
| 1 | Raw | `CodeEditorWidget` with format selector and validation |
| 2 | Form-data / x-www-form-urlencoded | `KeyValueTableWidget` |
| 3 | GraphQL | Split-pane query + variables editors (`_GraphQLMixin`) |
| 4 | Binary | File selector with path label |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `send_requested` | *(none)* | Send button clicked |
| `save_requested` | *(none)* | Ctrl+S pressed |
| `dirty_changed` | `bool` | Modified state changed |
| `request_changed` | `dict` | Any field modified (debounced 500ms) |

### Key Methods

| Method | Description |
|--------|-------------|
| `load_request(data, request_id)` | Populate from `RequestLoadDict` |
| `set_variable_map(variables)` | Distribute variables to child widgets |
| `get_request_data()` | Return current values as dict |
| `get_headers_text()` | Formatted header string |

## Body Search (_BodySearchMixin)

Find/replace bar for the body editor.  Toggle with Ctrl+F, replace
with Ctrl+R.

| Method | Description |
|--------|-------------|
| `_toggle_body_search()` | Show/hide find bar |
| `_search_next()` / `_search_prev()` | Navigate matches |
| `_replace_all()` | Bulk replace |

## GraphQL (_GraphQLMixin)

Split-pane editor for GraphQL requests.

```
+---------------------------+-------------------+
| Query Editor (60%)        | Variables (40%)   |
| (CodeEditorWidget)        | (CodeEditorWidget)|
+---------------------------+-------------------+
| Prettify | Wrap | errors  | Fetch Schema      |
+---------------------------+-------------------+
```

Schema introspection runs on a `SchemaFetchWorker` background thread.
Clicking the schema label opens a details popup.

## Auth System

See [Authentication](../guides/adding-auth-type.md) for the full auth
architecture.  The `_AuthMixin` builds a stacked widget with 14 auth
type pages:

1. Inherit auth from parent
2. No Auth
3. Bearer Token
4. Basic Auth
5. API Key
6. Digest Auth
7. OAuth 1.0
8. OAuth 2.0
9. Hawk Authentication
10. AWS Signature
11. JWT Bearer
12. ASAP (Atlassian)
13. NTLM Authentication
14. Akamai EdgeGrid

Pages are lazy-loaded on first selection.  Each page is built from
`FieldSpec` definitions in `auth_field_specs.py`.  OAuth 2.0 gets a
dedicated `OAuth2Page` with grant-type switching.
