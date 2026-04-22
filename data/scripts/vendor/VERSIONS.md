# Vendor Library Versions

Bundled JavaScript libraries loaded lazily by the scripting runtime.
All bundles are IIFE-wrapped via `esbuild --bundle --format=iife`.

## Libraries

| Library | Version | npm Package | Bundle Size | License |
|---------|---------|-------------|-------------|---------|
| CryptoJS | 4.2.0 | `crypto-js` | 219 KB | MIT |
| Lodash | 4.17.23 | `lodash` | 236 KB | MIT |
| Moment | 2.30.1 | `moment` | 156 KB | MIT |
| Chai | 4.5.0 | `chai` | 179 KB | MIT |
| tv4 | 1.3.0 | `tv4` | 68 KB | Public Domain |
| Ajv | 8.18.0 | `ajv` | 255 KB | MIT |
| xml2js | 0.6.2 | `xml2js` | 259 KB | MIT |
| csv-parse | 5.6.0 | `csv-parse` | 61 KB | MIT |
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

```bash
mkdir -p /tmp/vendor-build && cd /tmp/vendor-build
npm init -y
npm install crypto-js lodash moment chai@4 tv4 ajv xml2js csv-parse \
    buffer esbuild events timers-browserify

# Example: rebuild lodash
npx esbuild --bundle --format=iife --platform=browser \
    --global-name=__vendorExports \
    --outfile=lodash.js \
    <<< "module.exports = require('lodash');"

cp lodash.js /path/to/postmark/data/scripts/vendor/
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
