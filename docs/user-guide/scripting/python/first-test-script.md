# Your first Python test script

Validate a response using Python syntax on the **Scripts** tab.

## Steps

1. Open a request → **Scripts** tab.
2. In the **Test** editor, set the language to **Python** (status bar).
3. Paste:

```python
def test_status():
    pm.test("Status is 200", lambda: pm.expect(pm.response.code).to.equal(200))

test_status()
```

4. Click **Send**.
5. Open **Test Results** — the test passes when the server returns 200.

## Check JSON body

```python
def test_body():
    data = pm.response.json()
    pm.test("Has id", lambda: pm.expect(data).to.have.property("id"))

test_body()
```

## Note on pm.test

Python `pm.test` callbacks are synchronous. Define a small wrapper function if you prefer clearer structure.

## Related

- [Naming conventions](naming-conventions.md)
- [Tests and assertions](tests-and-assertions.md)
- [Python API reference](../../../scripting/python-api.md)
