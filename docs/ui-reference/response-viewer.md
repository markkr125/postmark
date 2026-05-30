# Response Viewer

Response display pane with status metadata, body rendering, and
search/filter capabilities.

Source: `src/ui/request/response_viewer/`

## ResponseViewerWidget

Inherits `_PreRequestMixin`, `_TestResultsMixin`, `_PopupMixin`,
and `_SearchFilterMixin`.

### Visible States

| State | Display |
|-------|---------|
| Empty | "Select a request to view response" |
| Loading | Indeterminate progress bar |
| Response | Status badge + body/headers tabs + metadata |

### Status Bar (top-right corner)

```
+--------+--------+--------+---------+------------------+
| 200 OK | 245 ms | 1.2 KB | Network | Save Response .. |
+--------+--------+--------+---------+------------------+
```

Each label is a `ClickableLabel` that opens a popup:

| Label | Popup | Content |
|-------|-------|---------|
| Status badge | `StatusPopup` | Status code explanation |
| Time | `TimingPopup` | Phase breakdown (DNS, TCP, TLS, TTFB, download) |
| Size | `SizePopup` | Request/response size breakdown |
| Network icon | `NetworkPopup` | HTTP version, TLS, certificate details |

Status badge colour follows HTTP status ranges:
- 2xx: green (success)
- 3xx: blue (redirect)
- 4xx: amber (client error)
- 5xx: red (server error)

### Tabs

| Tab | Content |
|-----|---------|
| Body | `CodeEditorWidget` with format selector (Pretty/Raw/JSON/XML/HTML) |
| Headers | Read-only key-value display |
| Cookies | Response cookie list (hidden when empty) |
| Test Results | `pm.test()` assertion results (hidden when no tests) |
| Pre-request | Pre-request script activity log (hidden when no scripts) |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_response_requested` | `dict` | Save current response as named example |
| `save_availability_changed` | `bool` | Response became saveable or unsaveable |

### Key Methods

| Method | Description |
|--------|-------------|
| `load_response(data)` | Populate from `HttpResponseDict` |
| `show_loading()` | Show progress bar |
| `show_error(msg)` | Display error state |
| `set_variable_map(variables)` | Propagate to body editor |
| `load_test_results(results)` | Populate Test Results tab from `list[TestResult]` |
| `load_pre_request_data(...)` | Populate Pre-request tab (console, vars, errors) |

## Search and Filter (_SearchFilterMixin)

### Search Bar

Find bar with match count and navigation:

| Control | Action |
|---------|--------|
| Search input | Highlight all matches |
| Next / Prev | Navigate through matches |
| Close | Hide search bar |

### Filter Bar

JSONPath/XPath expression filter:

| Control | Action |
|---------|--------|
| Filter input | JSONPath expression (e.g. `$.store.books`) |
| Apply | Evaluate and display filtered result |
| Clear | Restore full response body |

## Response Metadata Popups

All popups inherit from `InfoPopup` and appear anchored to their
trigger label.

### StatusPopup

Displays HTTP status code with human-readable explanation.

### TimingPopup

Coloured bar chart of request phases from `TimingDict`:

```
Prepare  [====]         12 ms
DNS      [========]     25 ms
TCP      [======]       18 ms
TLS      [=========]    30 ms
TTFB     [===========]  45 ms
Download [===]          10 ms
```

### SizePopup

Request and response size breakdown:

| Metric | Description |
|--------|-------------|
| Request headers | Size of sent headers |
| Request body | Size of sent body |
| Response headers | Size of received headers |
| Response body | Compressed / uncompressed sizes |

### NetworkPopup

Connection-level details from `NetworkDict`:

| Field | Example |
|-------|---------|
| HTTP version | HTTP/2 |
| Remote address | 93.184.216.34:443 |
| TLS protocol | TLSv1.3 |
| Cipher | TLS_AES_256_GCM_SHA384 |
| Certificate CN | example.com |
| Issuer | Let's Encrypt |
| Valid until | 2025-06-01 |

## Test Results Tab

**Mixin:** `_TestResultsMixin` in `response_viewer/test_results_mixin.py`

Displays results from `pm.test()` assertions run in test scripts.
The tab is hidden by default and shown only when test results are
present.

### Layout

- **Summary header:** `N/M tests passed` with green/red styling.
- **Scrollable list:** One row per test with:
  - Green check (`✓`) or red cross (`✗`) icon.
  - Test name.
  - Error message (failed tests only).

### API

| Method | Description |
|--------|-------------|
| `load_test_results(results)` | Populate tab from `list[TestResult]` |
| `_clear_test_results_rows()` | Remove all rows |
| `_build_test_results_tab()` | Create tab widget (called once at init) |

The tab is integrated via the `clear()` method — it resets to hidden
state when a new request is sent.

## Pre-request Tab

**Mixin:** `_PreRequestMixin` in `response_viewer/pre_request_mixin.py`

Displays console output, variable changes, and runtime errors from
pre-request script execution.  The tab is hidden by default and shown
only when pre-request scripts ran.  The tab label turns **red** when
the script produced errors.

### Layout

- **Header:** Green "Pre-request script executed" or red
  "Pre-request script error" with error details.
- **Variable changes:** HTML table of key/value pairs set by the
  script (hidden when none).
- **Console output:** Monospaced read-only area showing `console.log`,
  `console.warn` (amber), and `console.error` (red) entries.

### API

| Method | Description |
|--------|-------------|
| `load_pre_request_data(...)` | Populate tab from console logs, variable changes, errors |
| `_clear_pre_request_tab()` | Remove all content, hide tab |
| `_build_pre_request_tab()` | Create tab widget (called once at init) |
| `_apply_pre_request_tab_color()` | Set tab label red/normal based on error state |

The tab is integrated via the `clear()` method — it resets to hidden
state when a new request is sent.
