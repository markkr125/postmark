# Python `pm` API quick reference

Generated from LSP stubs by ``scripts/build_app_wiki.py``. For narratives and examples see [JavaScript API](../../../docs/scripting/javascript-api.md) or [Python API](../../../docs/scripting/python-api.md).

Python scripts also accept camelCase aliases (e.g. `pm.collectionVariables`).

## `pm` members

- `pm`
- `pm.clear`
- `pm.expect`
- `pm.get`
- `pm.getAll`
- `pm.has`
- `pm.info`
- `pm.jar`
- `pm.location`
- `pm.replaceIn`
- `pm.request`
- `pm.require`
- `pm.response`
- `pm.sendRequest`
- `pm.set`
- `pm.setNextRequest`
- `pm.skipRequest`
- `pm.test`
- `pm.toObject`
- `pm.unset`

## Global helpers (call WITHOUT a `pm.` prefix)

These are top-level builtins in the script sandbox — e.g. `datetime_now()`, not `pm.datetime_now()`.

- `json_loads(s: str)` — Parse JSON string
- `json_dumps(obj)` — Serialize to JSON string
- `re_match(pattern, string)` — Match regex at start of string
- `re_search(pattern, string)` — Search for regex in string
- `re_findall(pattern, string)` — Find all regex matches
- `re_sub(pattern, repl, string)` — Replace regex matches
- `math_ceil(x)` — Ceiling of x
- `math_floor(x)` — Floor of x
- `math_sqrt(x)` — Square root of x
- `math_pow(x, y)` — x raised to power y
- `math_log(x)` — Natural logarithm of x
- `math_pi` — Constant pi
- `math_e` — Constant e
- `b64encode(s)` — Base64 encode
- `b64decode(s)` — Base64 decode
- `hashlib_md5(s)` — MD5 hex digest
- `hashlib_sha256(s)` — SHA-256 hex digest
- `hashlib_sha512(s)` — SHA-512 hex digest
- `hashlib_hmac_sha256(data, key)` — HMAC-SHA256 hex digest
- `hashlib_hmac_sha512(data, key)` — HMAC-SHA512 hex digest
- `uuid_v4()` — Random UUID v4 string
- `datetime_now()` — Current UTC ISO timestamp
- `datetime_utcnow()` — Alias for datetime_now()
- `unix_timestamp()` — Current Unix time in seconds (int; Python sandbox only)
- `url_quote(s)` — URL-encode a string
- `url_urlencode(params)` — URL-encode query parameters
