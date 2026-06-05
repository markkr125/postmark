# Dialogs

Modal dialog windows for import, save, and settings.  The collection
runner is **inline** in the folder editor (see below).

Source: `src/ui/dialogs/`

## ImportDialog

Collection and environment importer with three input modes.

### Input Tabs

| Tab | Description |
|-----|-------------|
| Paste | QTextEdit for cURL commands, JSON, or URLs |
| Files | Drag-drop zone + file selector for JSON files |
| Folder | Drag-drop zone + folder selector for Postman archives |

### Execution

A background `_ImportWorker` runs on a `QThread`.  Emits
`finished(ImportSummary)` on success or `error(str)` on failure.

Progress is shown with an indeterminate progress bar.  The results
panel displays error and success counts.

## SaveRequestDialog

Save a draft request to an existing or new collection.

### UI Components

| Component | Description |
|-----------|-------------|
| Name field | Pre-filled with "Untitled Request" |
| Search input | Filter collections by name |
| Collection tree | Searchable, expandable tree of collections |
| New Collection button | Create a new collection inline |
| Cancel / Save | Action buttons |

### Key Methods

| Method | Returns |
|--------|---------|
| `request_name()` | User-entered request name |
| `selected_collection_id()` | Chosen collection ID |

## SettingsDialog

Application preferences dialog.  Optional constructor keyword
`initial_category` (``"Appearance"``, ``"Tabs"``, ``"Scripting"``,
``"History"``, ``"AI"``, ``"Models"``, ``"Private packages"``, ``"npm"``, ``"JSR"``, or
``"PyPI"``) selects the list row on open; the **Scripting** page holds
the Deno path and managed download.

Footer buttons (left to right): **OK** (apply pending changes if any, then
close), **Cancel** (close without applying), **Apply** (persist and stay open;
enabled when a setting changes).

### Category Pages

| Page | Settings |
|------|----------|
| Appearance | Style (Fusion / Native), colour scheme (Auto / Light / Dark) |
| Tabs | Tab limit, close policies, activate-on-close, wrap mode |
| Scripting | Deno executable path, validation, managed download; Python path; LSP toggle (tooltip notes debounced `didChange` / `pm.require` indexing); **Reset LSP workspace caches** (`pm_require_types.reset_workspace`); auto-save default; **Private package registries** (npm / JSR scope-mapped + default-npm override + PyPI primary/extra index with embedded auth) |
| History | Send retention (days), max entries per day (or unlimited), save response bodies toggle, max response size (MiB), read-only storage path under user data (`history/`). Applied on next send and by background prune. See [RequestHistoryService](../api-reference/services/request-history-service.md). |
| AI | Overview landing for AI settings (parent tree row). Select **Models** for configuration. |
| Models (under AI) | **Search models** field above the tree filters by display name, model id, or provider name. **Add provider** opens the provider dialog (test + import tool-capable models on save). **Edit provider** opens with the saved model list prefilled; skips connection test on Save when only the display name and/or Ollama **Default context** changed (provider type, URL, and API key unchanged). **Refresh model list** or **Test connection** replaces the list after a successful fetch. Tree columns: Name, Model, Context, **Cost** (USD per 1M tokens when known; blank otherwise), **Capabilities** (colored pills painted by `AiModelsTreeDelegate`: `suggest`, `tools`, `vision`; hover each tag for a description). Ollama refresh probes each model with `/api/show` for `insert`/`tools`/`vision`. The provider dialog includes **Default context** (4k–1M; default **32k**) used when context cannot be resolved from the API. Column widths are user-resizable and persisted in QSettings (`ui/ai_models_tree_header`). Model rows load in batches after the page is shown. Provider rows show the connection name in **Name** (bold) and a **gear** button at the far right of **Capabilities** that opens a menu: **Edit provider**, **Refresh models**, **Select all**, **Deselect all**, and **Remove provider**. Bottom bar: **Add provider**, **Expand all**, **Collapse all**. Saves immediately to QSettings. `ai_page.py`, `ai_page_actions.py`, `ai_provider_dialog.py`; `services/ai/ops/model_metadata.py`. |

### Private package registries (Scripting page)

Sub-section of the Scripting page. See
[docs/scripting/external-packages.md](../scripting/external-packages.md#private-package-registries)
for the full reference. Auth tokens live in the OS keychain via the
[`keyring`](https://pypi.org/project/keyring/) library by default, with a
Fernet-encrypted file fallback (machine-id-derived key) when keyring is
unavailable — the dialog surfaces a "less safe" warning in that case.
Per-row "Auth…" buttons open a `SecretEntryDialog`
([`src/ui/dialogs/secret_entry_dialog.py`](../../src/ui/dialogs/secret_entry_dialog.py))
that supports Token / Basic / None modes; no token ever lands in
`QSettings`.

## Collection runner (inline)

Batch request executor that runs all requests in a collection
sequentially.  The UI lives in **Folder editor → Runs → New run**
(`ui/request/folder_editor/runner_panel.py`); shared widgets and the
worker live under `ui/dialogs/collection_runner/` (no modal shell).

The checklist includes **every request under the open folder** (any depth,
including nested subfolders), not only requests when the folder is a root
collection.

Background ``RunnerWorker`` on ``QThread`` with signals:

| Signal | Parameters | Description |
|--------|------------|-------------|
| `progress` | `int, dict` | Single request completed (index, result) |
| `finished` | `list` | All requests completed |
| `error` | `str` | Fatal error |

### Script Integration

The runner executes inherited script chains for each request:

1. `ScriptService.build_script_chain(request_id)` resolves
   pre-request and test scripts from ancestors.
2. `ScriptEngine.run_pre_request_scripts()` runs before sending.
3. `ScriptEngine.run_test_scripts()` runs after receiving a response.
4. Variable mutations from `pm.environment.set()` propagate across
   subsequent requests within the run.

### Results Table

| Column | Content |
|--------|---------|
| Name | Request name (resizable) |
| Method | HTTP method |
| Status | HTTP status code, `ERR`, or `SKIP` |
| Time (ms) | Response time |
| Tests | `passed/total` (colour-coded) |
| Result | `OK` or error text (stretches to fill) |

Columns are resizable; the last column grows with the available width. The
summary line aggregates pass/fail across the run. When the run completes,
the first result row is selected so the detail panel is populated
immediately.
