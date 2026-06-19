# External packages (JavaScript)

Load npm, JSR, local, or bundled libraries with `pm.require`.

## npm and JSR

Use a **string literal** with an exact version when you pin a release:

```javascript
const _ = pm.require("npm:lodash@4.17.21");
const z = pm.require("npm:zod@3.23.8");
const fs = pm.require("jsr:@std/fs@1.0.0");
```

Rules:

- The argument must be a string literal (not a variable).
- Pinned versions use exact `X.Y.Z` — no `^`, `~`, or `latest`.
- Omitting `@version` resolves the registry's current release at run time (fine for experiments, not production).

First use may download packages and requires network permission for Deno.

## Local modules

Reuse code from the **Local scripts** tree:

```javascript
const fmt = pm.require("local:utils/format.js");
```

Path completion works while typing the string. Request scripts cannot use `import` for local files — use `pm.require('local:…')` instead.

## Legacy bundled libraries

Offline-friendly modules (no network) via the older `require()` shim:

```javascript
const moment = require("moment");
const CryptoJS = require("crypto-js");
```

Available names include `lodash`, `chai`, `ajv`, `tv4`, `uuid`, and others shipped with the app.

## Private registries

For private npm or JSR feeds, configure credentials under **File → Settings… → Private packages**. See [npm](../../settings/private-packages/npm.md) and [JSR](../../settings/private-packages/jsr.md).

## Related

- [Local scripts](../../local-scripts/overview.md)
- [Scripting runtimes](../../settings/scripting-runtimes.md)
- [External packages reference](../../../scripting/external-packages.md)
