# HttpService

HTTP request execution via `httpx`.  Captures detailed timing, size,
and network metadata.  All methods are `@staticmethod`.

Source: `src/services/http/http_service.py`

## Methods

### `send_request`

```python
@staticmethod
def send_request(
    *,
    method: str,
    url: str,
    headers: str | None = None,
    body: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> HttpResponseDict
```

Execute an HTTP request and return a structured response.

**Parameters:**
- `method` — HTTP method string (GET, POST, etc.).
- `url` — fully resolved URL (no `{{variables}}`).
- `headers` — raw header string or `None`.  Parsed via
  `parse_header_dict()`.
- `body` — request body string or `None`.
- `timeout` — request timeout in seconds.

**Returns:** `HttpResponseDict` containing status, headers, body,
timing breakdown, size breakdown, network metadata, and any error.

**Error handling:** Errors are returned as part of the response dict
(`error` key) — never raised into callers.

## Timing Capture

The service captures per-phase timing via httpx/httpcore trace callbacks:

```text
DNS resolution    --> timing["dns_ms"]
TCP connect       --> timing["tcp_ms"]
TLS handshake     --> timing["tls_ms"]
Time to first byte --> timing["ttfb_ms"]
Download          --> timing["download_ms"]
Post-processing   --> timing["process_ms"]
```

## Size Capture

```text
request_headers_size    Bytes of serialised request headers
request_body_size       Bytes of request body
response_headers_size   Bytes of serialised response headers
size_bytes              Bytes of response body (compressed)
response_uncompressed_size  Bytes of response body (uncompressed)
```

## Network Metadata

Captured via socket inspection and TLS context:

```text
http_version       "HTTP/1.1" or "HTTP/2"
remote_address     "93.184.216.34:443"
local_address      "192.168.1.100:54321"
tls_protocol       "TLSv1.3" or None (plain HTTP)
cipher_name        "TLS_AES_256_GCM_SHA384" or None
certificate_cn     Common name from server certificate
issuer_cn          Certificate issuer common name
valid_until        Certificate expiry date string
```

## TypedDicts

See [TypedDict Catalogue](../typedicts.md) for `HttpResponseDict`,
`TimingDict`, and `NetworkDict` field definitions.
