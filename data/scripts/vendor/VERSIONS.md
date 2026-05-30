# Vendor Library Versions

Bundled JavaScript libraries loaded lazily by the scripting runtime.
All bundles are IIFE-wrapped via `esbuild --bundle --format=iife`.

## Libraries

| Library | Version | npm Package | Bundle Size | License |
|---------|---------|-------------|-------------|---------|
| CryptoJS | 4.2.0 | `crypto-js` | 219 KB | MIT |
| Lodash | 4.18.1 | `lodash` | 236 KB | MIT |
| Moment | 2.30.1 | `moment` | 156 KB | MIT |
| Chai | 6.2.2 | `chai` | 144 KB | MIT |
| tv4 | 1.3.0 | `tv4` | 68 KB | Public Domain |
| Ajv | 8.20.0 | `ajv` | 259 KB | MIT |
| xml2js | 0.6.2 | `xml2js` | 259 KB | MIT |
| csv-parse | 6.2.1 | `csv-parse` | 62 KB | MIT |
| Esprima | 4.0.1 | `esprima` | 284 KB | MIT |

`esprima.js` is a stock webpack bundle (not esbuild IIFE) used by `ScriptLinter` for static JavaScript analysis only; it is not part of the sandbox `require()` surface.

## Support Files

| File | Size | Purpose |
|------|------|---------|
| `polyfills.js` | 3 KB | `crypto.getRandomValues`, `atob`, `btoa`, `window` shim |
| `buffer-polyfill.js` | 67 KB | Node.js `Buffer` polyfill (required by csv-parse) |

**Total on disk:** ~1.5 MB
**Total in memory (worst case, all loaded):** ~1.5 MB

## Rebuilding Vendor Bundles

Each bundle is built from a tiny entry file that assigns the library to a
`globalThis.__pm_<name>` global. That global is the contract the runtime's
`require()` shim reads (see `_REQUIRE_MAP` in
`src/services/scripting/js_runtime.py`), so the assignment — not a
`--global-name` flag — is what matters. Build with `--legal-comments=inline`
so the bundle ends with the assignment, matching the committed files.

```bash
mkdir -p /tmp/vendor-build && cd /tmp/vendor-build
npm init -y
npm install crypto-js lodash moment chai tv4 ajv xml2js csv-parse \
    buffer esbuild events timers-browserify

# CommonJS libs (lodash shown; same pattern for crypto-js, moment, tv4, xml2js):
printf "globalThis.__pm_lodash = require('lodash');\n" > _entry_lodash.js
npx esbuild --bundle --format=iife --platform=browser --legal-comments=inline \
    --outfile=lodash.js _entry_lodash.js

# ajv exposes the Ajv class — unwrap the default export:
printf "const a = require('ajv'); globalThis.__pm_ajv = a.default || a;\n" > _entry_ajv.js
npx esbuild --bundle --format=iife --platform=browser --legal-comments=inline \
    --outfile=ajv.js _entry_ajv.js

# csv-parse: the sync module. `Buffer` is supplied at runtime by buffer-polyfill.js:
printf "globalThis.__pm_csv_parse = require('csv-parse/sync');\n" > _entry_csv.js
npx esbuild --bundle --format=iife --platform=browser --legal-comments=inline \
    --outfile=csv-parse.js _entry_csv.js

# chai 5+ is ESM-only — use an ESM entry (.mjs) with a namespace import:
printf "import * as chai from 'chai';\nglobalThis.__pm_chai = chai;\n" > _entry_chai.mjs
npx esbuild --bundle --format=iife --platform=browser --legal-comments=inline \
    --outfile=chai.js _entry_chai.mjs

cp *.js /path/to/postmark/data/scripts/vendor/
```

## Security Audit

A GitHub Actions workflow runs the audit on any PR that touches vendor
files.  You can also trigger it manually from the Actions tab or run
locally:

```bash
poetry run python scripts/audit_vendor.py
```

The script installs the pinned packages into a temp directory, runs
`npm audit` and `npm outdated`, and cross-checks versions against
this file.  Exit code `0` means clean; `1` means action is needed.

If a vulnerability or update is found:

1. Update the package version in `scripts/audit_vendor.py`
   (`_VENDOR_PACKAGES`) **and** the version table above.
2. Rebuild the affected IIFE bundle with `esbuild` (see above).
3. Replace the file in `data/scripts/vendor/`.
4. Run the full test suite: `poetry run pytest`.

## When to Update

- **Security advisories:** Check `npm audit` periodically or when
  a CVE is reported for any listed package.
- **Major releases:** Only update if the new version is backwards
  compatible — scripts in existing user collections depend on the
  current API surface.
- **Never auto-update:** Vendor bundles are committed to the repo.
  Updates are manual and deliberate.
