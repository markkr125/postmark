# Tests and assertions (Python)

Use `pm.test` and `pm.expect` in the **Test** editor after **Send**.

## Status and body

```python
pm.test("Status is 200", lambda: pm.expect(pm.response.code).to.equal(200))

data = pm.response.json()
pm.test("Has email", lambda: pm.expect(data).to.have.property("email"))
```

## Skip

```python
pm.test.skip("Not ready", lambda: pm.expect(False).to.be.true)
```

## JSON schema (subset)

```python
schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "number"}}}
pm.test("Schema", lambda: pm.expect(data).to.have.json_schema(schema))
```

For full JSON Schema draft features, load `ajv` or `tv4` via bundled `require` in JavaScript, or a PyPI package in Python when Pyodide is available.

## Declarative assertions

The request **Assertions** tab compiles to script tests for all languages — use it for simple status/body/header checks without hand-written code.

## Related

- [First test script](first-test-script.md)
- [Console and output](../console-and-output.md)
