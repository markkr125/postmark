# Tests and assertions (JavaScript)

Test scripts validate responses after **Send**. Results appear under **Test Results** and in the script **Output** tab.

## Basic test

```javascript
pm.test("Status is 200", function () {
    pm.expect(pm.response.code).to.equal(200);
});
```

## Response body

```javascript
pm.test("Body is JSON with id", function () {
    const data = pm.response.json();
    pm.expect(data).to.have.property("id");
    pm.expect(data.id).to.be.a("number");
});
```

## Headers and timing

```javascript
pm.test("Content-Type is JSON", function () {
    pm.expect(pm.response.headers.get("Content-Type")).to.include("application/json");
});

pm.test("Fast enough", function () {
    pm.expect(pm.response.responseTime).to.be.below(500);
});
```

## Skip a test

```javascript
pm.test.skip("Optional check", function () {
    pm.expect(false).to.be.true;
});
```

## Declarative assertions tab

For simple checks without code:

1. Open the **Assertions** tab on the request.
2. Add rows: subject, operator, expected value.
3. Postmark compiles them into test script blocks on save.

Use **How it works** on that tab for a quick guide to subjects and operators.

## Related

- [First test script](first-test-script.md)
- [Console and output](../console-and-output.md)
- [JavaScript API reference](../../../scripting/javascript-api.md)
