# Run a collection

Execute every request under a folder (or collection) from the folder editor's inline runner.

## Open the runner

1. In the left **Collections** tree, click a collection or folder (not a single request).
2. In the centre editor, open the **Runs** section.
3. Click **New run** to show the runner configuration panel.

Alternatively, use the collection tree context action to open the folder tab focused on **Runs**.

## Configure a run

| Control | Purpose |
|---------|---------|
| **Environment** | Active variable set for `{{var}}` substitution and scripts |
| **Requests** | Checklist of requests to include (all descendants selected by default) |
| **Data file** | Optional CSV or JSON rows for data-driven iterations |
| **Iterations** | Repeat the full pass N times |
| **Delay** | Pause between requests (milliseconds) |
| **Scripts enabled** | Run inherited pre-request and test scripts |

## Start

1. Adjust settings as needed.
2. Click **Run collection** (or the equivalent start button).
3. Watch progress in the results table.

## Read results

| Column | Meaning |
|--------|---------|
| Name | Request name |
| Status | HTTP code, **ERR**, or **SKIP** |
| Time | Response time in ms |
| Tests | Passed/total test count |
| Result | **OK** or error message |

Select a row to see response headers, body preview, and per-test pass/fail lines.

A summary line shows totals for requests, tests, errors, and skips.

## Export

Click **Export…** to save results as CSV or JSON for CI logs or spreadsheets.

## Script behaviour during runs

- Pre-request scripts run top-down; tests run bottom-up (same as single **Send**).
- `pm.execution.skipRequest()` skips HTTP for that iteration.
- `pm.execution.setNextRequest("Name")` jumps to a named request.
- `pm.iterationData` exposes the current data-file row when one is loaded.

## Related

- [Collection runner hub](README.md)
- [Variables](../environments/variables.md)
