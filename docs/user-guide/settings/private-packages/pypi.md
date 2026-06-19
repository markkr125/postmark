# Private PyPI indexes

Point Python `pm.require` at private PyPI-compatible indexes with embedded credentials.

## Steps

1. Open **File → Settings…** → **Private packages** → **PyPI**.

## Index URLs

Add one or more index URLs. When authentication is required, supply username and token — Postmark embeds auth into the URL used by micropide at runtime (tokens are not shown in settings after save).

## Usage in scripts

```python
pkg = pm.require("my-private-lib==1.2.3")
```

The package name must exist on one of the configured indexes. Exact `==X.Y.Z` versioning applies.

## Requirements

- Pyodide runtime (Deno + vendored assets) must be available.
- Network access on first install.

## Related

- [Private packages hub](README.md)
- [External packages (Python)](../../scripting/python/external-packages.md)
