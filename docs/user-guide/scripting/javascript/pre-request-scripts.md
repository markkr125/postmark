# Pre-request scripts (JavaScript)

Pre-request scripts run **before** **Send**. Use them to set variables, mutate the request, or fetch tokens.

## Steps

1. Open a request → **Scripts** tab.
2. Select **JavaScript** in the pre-request editor status bar.
3. Write your script in the **Pre-request** editor.
4. Click **Send**.

## Set variables

```javascript
pm.variables.set("timestamp", Date.now().toString());
pm.environment.set("requestId", pm.variables.replaceIn("{{$guid}}"));
```

Use `{{timestamp}}` and `{{requestId}}` in the URL, headers, or body.

## Modify the request

```javascript
pm.request.headers.upsert({ key: "X-Request-Time", value: new Date().toISOString() });

const url = pm.request.url;
url.query.add({ key: "debug", value: "1" });
```

## Important rules

- **`pm.response` is null** in pre-request scripts — only use it in the **Test** editor.
- Changes to headers, URL, and body apply to the outgoing HTTP request.
- Collection and folder pre-request scripts run first — see [Execution order](../execution-order.md).

## Run without sending HTTP

When the script toolbar offers **Run**, you can execute the pre-request chain alone (no HTTP). Useful for checking logs and variable side effects.

## Related

- [Variables](variables.md)
- [Chaining requests](chaining-requests.md)
- [Execution order](../execution-order.md)
