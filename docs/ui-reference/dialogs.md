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
`initial_category` (``"Appearance"``, ``"Tabs"``, or ``"Scripting"``)
selects the list row on open; the **Scripting** page holds the Deno path
and managed download.

### Category Pages

| Page | Settings |
|------|----------|
| Appearance | Style (Fusion / Native), colour scheme (Auto / Light / Dark) |
| Tabs | Tab limit, close policies, activate-on-close, wrap mode |
| Scripting | Deno executable path, validation, managed download; Python path |

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
