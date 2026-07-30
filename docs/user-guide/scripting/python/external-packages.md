# External packages (Python)

Load PyPI packages with `pm.require` when the Pyodide runtime is available (Deno + vendored assets). Reuse code from the **Local scripts** tree with `pm.require("local:…")` on both Pyodide and the restricted runtime.

## Local modules

```python
helpers = pm.require("local:utils/helpers.py")
pm.variables.set("sum", str(helpers.add(2, 3)))
```

Rules:

- Paths must end in `.py`.
- Path completion works while typing the string.
- Request and folder scripts cannot use Python `import` for local files — use `pm.require('local:…')`.
- Nested `pm.require("local:…")` inside a local module is supported; cycles raise an error.

See [Local scripts overview](../../local-scripts/overview.md).

## PyPI packages

```python
jmespath = pm.require("jmespath")
result = jmespath.search("foo.bar", {"foo": {"bar": 1}})
```

Pin an exact version:

```python
jose = pm.require("python-jose==3.3.0")
```

## Rules (PyPI)

- Argument must be a **string literal**.
- Exact versions use `==X.Y.Z` — no ranges.
- First download may need network access to PyPI.
- Only packages with compatible wheels work under Pyodide.

## Without Pyodide

The restricted Python subprocess does not support arbitrary PyPI `pm.require` downloads. Local `pm.require("local:…py")` still works. Use injected stdlib shims documented in the Python API reference, or install/configure Pyodide via **Scripting** settings.

## Private PyPI

Configure index URLs and tokens under **File → Settings… → Private packages → PyPI**. See [PyPI settings](../../settings/private-packages/pypi.md).

## Related

- [Scripting runtimes](../../settings/scripting-runtimes.md)
- [External packages reference](../../../scripting/external-packages.md)
- [Local scripts](../../local-scripts/overview.md)
