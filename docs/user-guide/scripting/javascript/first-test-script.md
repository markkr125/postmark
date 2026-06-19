# Your first JavaScript test script

Write a test that checks the HTTP status code after you send a request.

## Steps

1. Open a saved or draft **HTTP request** in the centre editor.
2. Click the **Scripts** tab.
3. In the **Test** editor (bottom), ensure the language is **JavaScript** (status bar
   under the editor).
4. Paste:

```javascript
pm.test("Status is 200", function () {
    pm.expect(pm.response.code).to.equal(200);
});
```

5. Click **Send**.
6. Open the **Test Results** area in the response/script output — the test should pass
   when the server returns status 200.

## Check the response body

```javascript
pm.test("Body has ok field", function () {
    const data = pm.response.json();
    pm.expect(data.ok).to.eql(true);
});
```

## Related

- [Tests and assertions](tests-and-assertions.md)
- [JavaScript API reference](../../../scripting/javascript-api.md)
- [Scripts tab](../scripts-tab.md)
