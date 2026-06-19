# External packages (Python)

Load PyPI packages with `pm.require` when the Pyodide runtime is available (Deno + vendored assets).

## Basic usage

```python
jmespath = pm.require("jmespath")
result = jmespath.search("foo.bar", {"foo": {"bar": 1}})
```

Pin an exact version:

```python
jose = pm.require("python-jose==3.3.0")
```

## Rules

- Argument must be a **string literal**.
- Exact versions use `==X.Y.Z` — no ranges.
- First download may need network access to PyPI.
- Only packages with compatible wheels work under Pyodide.

## Without Pyodide

The restricted Python subprocess does not support arbitrary `pm.require` downloads. Use injected stdlib shims documented in the Python API reference, or install/configure Pyodide via **Scripting** settings.

## Private PyPI

Configure index URLs and tokens under **File → Settings… → Private packages → PyPI**. See [PyPI settings](../../settings/private-packages/pypi.md).

## Related

- [Scripting runtimes](../../settings/scripting-runtimes.md)
- [External packages reference](../../../scripting/external-packages.md)
