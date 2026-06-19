# Chaining requests (JavaScript)

Call another HTTP request from a script and use its response in the main request or tests.

## pm.sendRequest with callback

```javascript
pm.sendRequest("https://auth.example.com/token", function (err, res) {
    if (err) {
        console.log(err);
        return;
    }
    const json = res.json();
    pm.environment.set("accessToken", json.access_token);
});
```

Then set the main request's **Authorization** header to `Bearer {{accessToken}}`.

## Async / await (JavaScript)

```javascript
const res = await pm.sendRequest({
    url: "https://auth.example.com/token",
    method: "POST",
    header: { "Content-Type": "application/json" },
    body: { mode: "raw", raw: JSON.stringify({ client_id: "x", client_secret: "y" }) },
});
pm.variables.set("accessToken", res.json().access_token);
```

## Control collection runner flow

In a collection run:

```javascript
// Skip sending this request's HTTP call
pm.execution.skipRequest();

// Jump to a named request instead of the next in folder order
pm.execution.setNextRequest("Login");
```

## Limits

- Sub-requests are capped per script run (avoid unbounded loops).
- Very large response bodies may be rejected — keep auth/token endpoints small.

## Related

- [Pre-request scripts](pre-request-scripts.md)
- [Collection runner](../../collection-runner/run-a-collection.md)
- [JavaScript API reference](../../../scripting/javascript-api.md)
