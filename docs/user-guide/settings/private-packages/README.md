# Private packages

Authenticate to private npm, JSR, and PyPI registries so `pm.require` and Deno can download scoped packages in scripts.

| Page | Registry |
|------|----------|
| [npm](npm.md) | Private npm scopes and default registry token |
| [JSR](jsr.md) | Private JSR scopes |
| [PyPI](pypi.md) | Private index URLs and credentials |

Open **File → Settings…** → **Private packages** for the overview and secret-storage status, then select **npm**, **JSR**, or **PyPI** in the tree.

Tokens are stored in the system keychain when available, otherwise in an encrypted local store — never in plain QSettings.

## Related

- [External packages (JavaScript)](../../scripting/javascript/external-packages.md)
- [External packages (Python)](../../scripting/python/external-packages.md)
- [Scripting runtimes](../scripting-runtimes.md)
