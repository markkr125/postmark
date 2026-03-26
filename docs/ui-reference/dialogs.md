# Dialogs

Modal dialog windows for import, save, settings, and batch execution.

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

Application preferences dialog.

### Category Pages

| Page | Settings |
|------|----------|
| Appearance | Style (Fusion / Native), colour scheme (Auto / Light / Dark) |
| Tabs | Tab limit, close policies, activate-on-close, wrap mode |

## CollectionRunner

Batch request executor that runs all requests in a collection
sequentially.

Background `_RunnerWorker` on `QThread` with signals:

| Signal | Parameters | Description |
|--------|------------|-------------|
| `progress` | `int, dict` | Single request completed (index, result) |
| `finished` | `list` | All requests completed |
| `error` | `str` | Fatal error |
