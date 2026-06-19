# Private JSR registries

Configure JSR scope tokens for `pm.require('jsr:…')` in JavaScript and TypeScript.

## Steps

1. Open **File → Settings…** → **Private packages** → **JSR**.

## Scope mappings

Add a row per private JSR scope:

| Field | Purpose |
|-------|---------|
| Scope | JSR scope name |
| Token | Bearer or API token for that scope |

Scripts must still use string literals with exact versions, e.g. `pm.require('jsr:@myscope/lib@1.0.0')`.

## Related

- [Private packages hub](README.md)
- [External packages (JavaScript)](../../scripting/javascript/external-packages.md)
