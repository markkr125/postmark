# Script Snippets

Postmark ships a **Snippets palette** — a popover, opened from the
script editor's status bar, that inserts ready-made `pm.*` boilerplate
at the cursor with one click. Pattern matches Postman's "Snippets"
sidebar.

> **Where the button lives:** Open any request → **Scripts** tab → look
> at the status bar at the bottom of the editor. The **Snippets** link
> sits right after **History**.

> **Where the data lives:** All snippet content is declarative JSON in
> [`data/snippets/<lang>.json`](../../data/snippets/). One file per
> language; new languages drop in without code changes.

## How it works (user view)

1. Click **Snippets** in the bottom status bar.
2. A frameless popover anchors below the button.
3. Type in the search box to filter by name or body substring
   (case-insensitive).
4. Click any row → the snippet body is inserted at the text cursor.
   The popover closes and editor focus returns. If you had a region
   selected, it's replaced.
5. Press **Esc** or click outside to dismiss without picking.

The popover is **context-filtered**: when the editor is in pre-request
mode, the `Tests` category is hidden; in post-response mode, the
`Request setup` category is hidden. Categories that apply to both
contexts (`Send requests`, `Variables`) appear in either tab.

The **Snippets** button is automatically disabled when no snippet file
exists for the current editor language. Tooltip in that case:
`No snippets for <language>`.

## Shipped categories (v1)

Both [`javascript.json`](../../data/snippets/javascript.json) (TypeScript
resolves here too via the loader fallback) and
[`python.json`](../../data/snippets/python.json) ship the same four
categories with matching counts:

| Category          | Contexts        | Items | Purpose                                                           |
|-------------------|-----------------|-------|-------------------------------------------------------------------|
| Send requests     | `pre` + `post` + `local` | 1     | `pm.sendRequest` / `pm.send_request` workflow scaffold.           |
| Variables         | `pre` + `post` + `local` | 12    | Get / set / unset across globals, collection, environment, local. |
| Request setup     | `pre` + `local` | 6     | Bearer / basic auth, ISO timestamp header, UUID, login flow…     |
| Tests             | `post` only     | 15    | Postman-style `pm.test(...)` assertions for status / body / etc.  |
| Import npm / PyPI | `pre` + `post` + `local` | varies | `pm.require` examples; `pm.response` rows hidden on local scripts. |

## Authoring (adding a snippet, category, or language)

Snippets are declarative JSON. **No Python or JS changes are required**
to add a snippet, a category, or a brand-new language.

### Adding a snippet to an existing category

Open the appropriate `data/snippets/<lang>.json`, find the category, and
append a row:

```json
{
  "name": "Set bearer token from env",
  "body": "pm.request.headers.add({\n    key: \"Authorization\",\n    value: \"Bearer \" + pm.environment.get(\"token\")\n});"
}
```

`body` is inserted **verbatim** at the cursor — newlines preserved.
Restart the app to pick up the change (snippets are loaded once per
process via `functools.lru_cache`).

### Adding a new category

Append a category object to the `categories` array. Set `contexts` to
filter where it appears:

```json
{
  "_comment": "Auth helpers — only useful in pre-request scripts.",
  "name": "Auth",
  "contexts": ["pre"],
  "snippets": [
    { "name": "Inject bearer", "body": "pm.request.headers.upsert({key:\"Authorization\",value:\"Bearer \" + pm.environment.get(\"token\")});" }
  ]
}
```

`contexts` accepts `"pre"` (pre-request editor), `"post"` (post-response
editor), `"local"` (local script tabs), or any combination. Omit the field
for back-compat default (request pre/post editors only). Built-in snippets
whose bodies contain `pm.response` are also hidden on local scripts.

### Adding a new language

1. Create `data/snippets/<lang>.json` where `<lang>` matches
   `CodeEditorWidget.language` (lowercase, e.g. `"go"`).
2. Use the JSON shape below.
3. Restart Postmark. The snippets toolbar button enables automatically
   when [`has_snippets()`](../../src/ui/widgets/snippets/loader.py) returns
   true for the new language.

## JSON schema

```json
{
  "_comment": "Optional metadata; ignored by the loader (any _-prefixed key).",
  "language": "javascript",
  "categories": [
    {
      "_comment": "Optional category-level metadata.",
      "name": "Category title",
      "contexts": ["pre", "post"],
      "snippets": [
        { "name": "Snippet title", "body": "verbatim\\ncode\\nwith\\nnewlines" }
      ]
    }
  ]
}
```

| Field                              | Required | Purpose                                                                                                       |
|------------------------------------|----------|---------------------------------------------------------------------------------------------------------------|
| `language`                         | No (v1)  | Documentary; not strictly validated.                                                                          |
| `categories[]`                     | Yes      | Ordered list of groups.                                                                                       |
| `categories[].name`                | Yes      | Bold non-selectable header in the popover.                                                                    |
| `categories[].contexts`            | No       | Array of `"pre"`, `"post"`, and/or `"local"`. Omit for request editors only.                                  |
| `categories[].snippets[]`          | Yes      | Ordered snippet rows.                                                                                         |
| `categories[].snippets[].name`     | Yes      | Visible row label.                                                                                            |
| `categories[].snippets[].body`     | Yes      | Inserted **verbatim** at the cursor (selection replaced).                                                      |

Any key whose name starts with `_` (e.g. `_comment`) is **stripped by the
loader** at every level — schema doc, category, snippet. Use them freely
to leave inline notes since JSON has no native comment syntax.

## TypeScript fallback

Editor language `typescript` resolves to `javascript.json`. TS scripts
share the same `pm.*` surface as JS at runtime (Deno bundles them the
same way), so the snippet content is identical. There is no separate
`typescript.json` in v1.

## Caching and reloading

`load_snippets(language)` is wrapped in
[`functools.lru_cache`](../../src/ui/widgets/snippets/loader.py). A file
is read once per process. Edits on disk require an app restart to take
effect.

## Insertion semantics

Picking a snippet calls `editor.textCursor().insertText(body)`. Qt's
`insertText` deletes the current selection (if any) before inserting, so
"replace highlighted region; otherwise insert at caret" is the natural
behaviour — no extra logic needed.

## Implementation files

| Concern                                          | File                                                                                                                                                                                          |
|--------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| JSON shape, loading, TS fallback, `_*` stripping | [`src/ui/widgets/snippets/loader.py`](../../src/ui/widgets/snippets/loader.py)                                                                                                                |
| Frameless popover, search, filter, anchor below  | [`src/ui/widgets/snippets/popup.py`](../../src/ui/widgets/snippets/popup.py)                                                                                                                  |
| Status-bar **Snippets** button + `_open_snippets`| [`src/ui/request/request_editor/scripts/scripts_mixin.py`](../../src/ui/request/request_editor/scripts/scripts_mixin.py) (`_build_script_status_bar`, `_open_snippets`, `_refresh_snippets_button`) |
| Snippet content (JS / TS)                        | [`data/snippets/javascript.json`](../../data/snippets/javascript.json)                                                                                                                        |
| Snippet content (Python)                         | [`data/snippets/python.json`](../../data/snippets/python.json)                                                                                                                                |
| Author runbook                                   | [`data/snippets/README.md`](../../data/snippets/README.md)                                                                                                                                    |

## Tests

| Test file                                                                                                              | Coverage                                                                                                                                                                              |
|------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`tests/ui/widgets/test_snippets_popup.py`](../../tests/ui/widgets/test_snippets_popup.py)                            | Loader (TS fallback, malformed JSON, unknown language, `_`-key stripping), context filter (`load_snippets_for`), popover (search, pick callback, Esc dismiss, header non-selectable). |

## Out of scope (v1)

- Body templating / placeholders / tab-stops (no `${1}` cursor marks).
- User-editable snippets (custom personal libraries).
- Hot-reload from disk without a restart.
- Per-collection snippet overrides.
- Snippet metadata (descriptions, deprecation, categories beyond JSON).

## Python differences from JavaScript

When porting a JS snippet to Python, most idioms map cleanly because
Postmark mirrors the `pm.*` surface in both runtimes. A few details
diverge:

| Concept                  | JavaScript                                            | Python                                                                                  |
|--------------------------|-------------------------------------------------------|------------------------------------------------------------------------------------------|
| Pickable lambdas         | `function () { ... }`                                  | `def t_fn(): ...; pm.test("name", t_fn)` — RestrictedPython forbids inline `lambda` bodies for `pm.test`. |
| Variable declaration     | `const`, `let` (no `var`)                              | Plain assignment; no declaration keyword.                                                |
| Base64 encode            | `btoa(...)`                                            | `b64encode(...)` (sandbox builtin; returns `bytes`, call `.decode()` for `str`).         |
| UUID v4                  | `pm.require("uuid").v4()`                              | `uuid_v4()` (sandbox builtin; no `import uuid`).                                         |
| ISO timestamp            | `new Date().toISOString()`                              | `datetime_now()` (sandbox builtin; no `import datetime`).                                |
| JSON encode/decode       | `JSON.stringify(x)` / `JSON.parse(s)`                  | `json_dumps(x)` / `json_loads(s)` (sandbox builtins; no `import json`).                  |
| Header mutation          | `pm.request.headers.add({key, value})`                  | `pm.request.headers["Name"] = "value"` (dict-style sugar on `_HeaderList`).              |
| Schema validation        | `pm.require("tv4").validate(...)`                      | No `jsonschema` in the sandbox; assert shape with `isinstance` and stdlib comprehensions.|

Both Python files (`pm_bootstrap.py` for Pyodide and `_py_sandbox.py`
for the RestrictedPython subprocess) accept either snake_case or
camelCase on the `pm` object — `pm.collectionVariables` and
`pm.collection_variables` are the same scope.

## Related

- [Postman API parity](postman-parity.md) — full matrix of `pm.*`
  surface vs Postman SDK.
- [JavaScript API Reference](javascript-api.md)
- [Python API Reference](python-api.md)
- [Examples](examples.md)
