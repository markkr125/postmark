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
| 5 | Scripts | Dual `CodeEditorWidget` tabs (Pre-request / Post-response) with inline output panels |

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

## Scripts (_ScriptsMixin)

Scripts has two sub-tabs:

- **Pre-request** — runs before send.
- **Post-response** — runs against a response context.

Each sub-tab uses a vertical splitter between the code editor and the **Output**
panel (`ScriptOutputPanel`). The panel uses tabs: **Output** (console / debug),
**Problems** (LSP diagnostics), and **Mock response** on post-response scripts only.
The default split gives the output band slightly
more than half of the tab height (you can drag the handle). During inline debug,
the variable inspector grows with that output area; long lists scroll inside it.
Variable names and values are selectable for copy (each cell is a label; the
tree item text in those columns is cleared so only one layer is painted).
Long values start collapsed with an arrow to expand the full text.

Below the editor, a **status strip** shows cursor line/column, a **language**
control (VS Code-style: underlined accent link; click to choose JavaScript, TypeScript, Python, or **Auto**), a **History** link (same link styling; opens script version history), and a
character count. In **Auto** mode the language is inferred from the script text
after a short debounce; choosing JavaScript, TypeScript, or Python locks the mode until you
pick **Auto** again. Saved requests store `pre_language` and `test_language`
independently.

Post-response controls live on the **Mock response** tab:

- `Use current response` (default): `Run` first sends the active request, then executes the current post-response script against the live response.
- `Manual mock response`: shows status, **Headers** key-value rows, and a full **CodeEditorWidget** JSON body (same folding and gutter chrome as other editors); keeps the original offline inline run behavior.

**Folder / collection Scripts → Post-response** (same `ScriptOutputPanel` with
`host_kind="folder"`) has **no** “Use current response” option (there is no
single request tab to send), but the **Mock response** tab (status + headers + body)
is always available so `pm.response` is populated for inline Run/Debug (paste JSON
for `pm.response.json()`).  A blank mock body defaults to ``{}`` so
`pm.response.json()` is valid without typing a body first.  Postman-style
`pm.response.to.have.status(…)`, `header(…)`, and `jsonBody(…)` assertions are
supported in both JavaScript and Python test scripts.

For **JavaScript** inline debug (Deno), gutter breakpoints inside a
`pm.test(..., function () { ... })` callback are wired to the inspector like
any other user line; use **Debug test '…'** from the test gutter menu when you
want to run a single named test only.

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
