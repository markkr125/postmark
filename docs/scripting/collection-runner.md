# Collection Runner Scripting

The Collection Runner executes all requests in a collection
sequentially.  When scripts are present, the runner integrates them
into the execution lifecycle.

## Execution Lifecycle

For each request in the collection:

```text
1. Fetch script chain (collection --> folders --> request)
2. Run pre-request scripts (top-down)
3. Check for pm.execution.skipRequest() -- skip HTTP if set
4. Apply request mutations from scripts
5. Send HTTP request (unless skipped)
6. Run test scripts (bottom-up)
7. Check for pm.execution.setNextRequest() -- override next request
8. Record test results and console output
9. Emit progress with per-request results
```

## Test Results Display

The runner's results table includes a **Tests** column showing pass/fail
counts per request:

| Column | Content |
|--------|---------|
| Name | Request name |
| Status | HTTP status code, `ERR`, or `SKIP` |
| Time (ms) | Response time |
| Tests | `passed/total` (color-coded green/red) |
| Result | `OK` or error message |

A summary line shows aggregate totals:
`Done: N/M requests OK | Tests: P/T passed | E error(s) | S skipped`

### Per-Request Detail

Clicking a result row shows a detail panel with:

- Response status code and timing
- Response headers
- Response body (first 2000 characters)
- Test assertions with pass/fail icons
- Error message (if any)

### Export

The **Export…** button saves the results to CSV or JSON.
The export includes name, method, status, timing, test counts,
and result/error for each request.

## Implementation

The runner worker (`RunnerWorker` in `collection_runner/worker.py`) fetches
script chains via `ScriptService.build_script_chain(request_id)` and
executes them via `ScriptEngine.run_pre_request_scripts()` and
`ScriptEngine.run_test_scripts()`.

Pre-request script mutations (URL, method, headers, body) are applied
before the HTTP request is sent.

## Environment Variables

The runner's **Environment** dropdown lets you select an environment
before starting a run.  Selected environment variables are:

- Substituted into URLs, headers, and body text (`{{variable}}`)
- Passed to pre-request and test script contexts via
  `pm.environment.get(key)`

Variable substitution uses the same `{{key}}` pattern as the main
send pipeline.

## Request Selection

The runner shows a checklist of all requests in the collection.
Uncheck individual requests to exclude them from the run.
Use **Select All** / **Deselect All** buttons for bulk control.

## Variable Propagation

Variables set by scripts in one request are currently scoped to that
request's execution.  Cross-request variable sharing in the runner is
planned for a future release.

## Flow Control

The `pm.execution` API controls request ordering in the runner:

- `pm.execution.setNextRequest(name)` — jump to the named request
  after the current one finishes.  Pass `null` / `None` to stop
  the runner entirely.
- `pm.execution.skipRequest()` — skip the current request's HTTP
  send.  The request is recorded with status `0` and shown as
  `SKIP` in the results table.

Flow control is evaluated at the end of each request.  The last
`setNextRequest()` call wins when multiple scripts set it.

```javascript
// Test script: retry on failure
pm.test("Retry on 500", function() {
    if (pm.response.code === 500) {
        pm.execution.setNextRequest(pm.info.requestName);
    }
});
```

## Data-Driven Runs

The runner supports data-driven iterations via CSV or JSON data files:

1. Click **Data File…** to load a CSV or JSON file.
2. Each row becomes one iteration.
3. `pm.iterationData.get(key)` / `pm.iteration_data.get(key)` returns
   the value for the current row.
4. The **Iterations** spinner adjusts the iteration count.

### CSV format

```csv
username,password
alice,secret1
bob,secret2
```

### JSON format

```json
[
  {"username": "alice", "password": "secret1"},
  {"username": "bob", "password": "secret2"}
]
```

The runner repeats the full request sequence once per data row.
Progress bar and table show all iterations.

## Global Script Toggle

Script execution can be disabled globally in **Settings → Scripting**.
When disabled, pre-request and test scripts are skipped for both
single requests and collection runs.  The setting is stored in
QSettings under `scripting/enabled`.

## Related Pages

- [Overview](overview.md) — execution order and inheritance
- [JavaScript API](javascript-api.md) — full JS pm reference
- [Python API](python-api.md) — full Python pm reference
- [Security](security.md) — sandbox and resource limits
