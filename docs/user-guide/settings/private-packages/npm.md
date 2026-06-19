# Private npm registries

Map npm scopes to registry URLs and tokens for `pm.require('npm:…')` in JavaScript and TypeScript scripts.

## Steps

1. Open **File → Settings…** → **Private packages** → **npm**.

## Scope mappings

Add rows for each scope your packages use:

| Field | Example |
|-------|---------|
| Scope | `@mycompany` |
| Registry URL | `https://npm.mycompany.com/` |
| Token | `_authToken` or bearer value |

When a script requires `npm:@mycompany/pkg@1.0.0`, Deno uses the matching registry and token.

## Default npm registry

Configure a token for the public `registry.npmjs.org` when you need authenticated access to private packages on npm's default registry (not only scoped feeds).

## After saving

1. Click **Apply** or **OK**.
2. If LSP or completions look wrong, use **Reset LSP workspace caches** on the **Scripting** page.

## Related

- [Private packages hub](README.md)
- [External packages (JavaScript)](../../scripting/javascript/external-packages.md)
