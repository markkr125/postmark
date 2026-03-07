"""HTTP request execution service.

Wraps ``httpx`` to send HTTP requests and return structured response data.
All methods are ``@staticmethod`` — no instance state.  Errors are returned
as part of the response dict, never raised into callers.

Captures detailed timing breakdown (DNS, TCP, TLS, TTFB, download),
size breakdown (request/response headers and body), and network metadata
(HTTP version, remote/local address, TLS protocol, cipher, certificate)
via httpx/httpcore trace callbacks and ``socket.getaddrinfo`` pre-resolve.
"""

from __future__ import annotations

import logging
import socket
import ssl as ssl_module
import time
from typing import Any, NotRequired, TypedDict
from urllib.parse import urlparse

import httpx

from services.http.header_utils import parse_header_dict

logger = logging.getLogger(__name__)

# Default timeout in seconds for HTTP requests.
DEFAULT_TIMEOUT = 30.0


class TimingDict(TypedDict):
    """Per-phase timing breakdown in milliseconds.

    All values are ``float`` >= 0.  On connection reuse the TCP/TLS
    phases will be 0.
    """

    dns_ms: float
    tcp_ms: float
    tls_ms: float
    ttfb_ms: float
    download_ms: float
    process_ms: float


class NetworkDict(TypedDict):
    """Network-level metadata captured from the connection.

    TLS-related fields are ``None`` for plain HTTP connections.
    """

    http_version: str
    remote_address: str
    local_address: str
    tls_protocol: str | None
    cipher_name: str | None
    certificate_cn: str | None
    issuer_cn: str | None
    valid_until: str | None


class HttpResponseDict(TypedDict):
    """Structured HTTP response passed from the service to the UI.

    ``elapsed_ms`` is always present.  Success responses carry
    ``status_code``, ``status_text``, ``headers``, ``body``, and
    ``size_bytes``.  Error responses carry ``error`` instead.
    Keys that may be absent are marked ``NotRequired``.
    """

    elapsed_ms: float
    status_code: NotRequired[int]
    status_text: NotRequired[str]
    headers: NotRequired[list[dict[str, str]]]
    body: NotRequired[str]
    size_bytes: NotRequired[int]
    error: NotRequired[str]

    # Timing breakdown
    timing: NotRequired[TimingDict]

    # Size breakdown
    request_headers_size: NotRequired[int]
    request_body_size: NotRequired[int]
    response_headers_size: NotRequired[int]
    response_uncompressed_size: NotRequired[int]

    # Network metadata
    network: NotRequired[NetworkDict]


def _phase_ms(trace_times: dict[str, float], *prefixes: str) -> float:
    """Compute the duration of a trace phase from start/complete timestamps.

    Accepts one or more httpcore event prefixes (e.g.
    ``"connection.connect_tcp"``) and tries each until a matching pair of
    ``"<prefix>.started"`` / ``"<prefix>.complete"`` is found.  Returns
    ``0.0`` if no matching pair exists (e.g. connection reuse).
    """
    for prefix in prefixes:
        started = trace_times.get(f"{prefix}.started")
        complete = trace_times.get(f"{prefix}.complete")
        if started is not None and complete is not None:
            return max(0.0, (complete - started) * 1000)
    return 0.0


class HttpService:
    """Send HTTP requests and return structured response dicts.

    Every method is a ``@staticmethod`` — no shared state.
    """

    @staticmethod
    def _resolve_dns(host: str, port: int) -> tuple[float, str]:
        """Pre-resolve *host* via ``getaddrinfo`` and return (dns_ms, ip).

        Returns ``(0.0, "")`` if resolution fails so the caller can let
        httpx attempt its own resolution (and raise its own error).
        """
        try:
            start = time.perf_counter()
            results = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            dns_ms = (time.perf_counter() - start) * 1000
            ip = str(results[0][4][0]) if results else ""
            return dns_ms, ip
        except (socket.gaierror, OSError):
            return 0.0, ""

    @staticmethod
    def _extract_cert_field(cert: dict[str, Any], field: str) -> str | None:
        """Extract a single field (e.g. ``commonName``) from a cert dict.

        The dict returned by ``ssl.SSLObject.getpeercert()`` stores
        subject/issuer as a tuple of tuples of ``(key, value)`` pairs.
        """
        for rdn in cert.get(field, ()):
            for attr_key, attr_value in rdn:
                if attr_key == "commonName":
                    return str(attr_value)
        return None

    @staticmethod
    def send_request(
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> HttpResponseDict:
        """Execute an HTTP request and return the response.

        Captures detailed timing, size breakdown, and network metadata
        in addition to the basic response fields.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full request URL.
            headers: Newline-separated ``Key: Value`` header string.
            body: Request body text (sent as-is).
            timeout: Timeout in seconds.

        Returns:
            An :class:`HttpResponseDict` with response details or an
            ``error`` key describing the failure.
        """
        parsed_headers = parse_header_dict(headers)
        content: bytes | None = body.encode("utf-8") if body else None

        # -- 1. DNS pre-resolve ----------------------------------------
        parsed_url = urlparse(url)
        host = parsed_url.hostname or ""
        default_port = 443 if parsed_url.scheme == "https" else 80
        port = parsed_url.port or default_port
        dns_ms, remote_ip = HttpService._resolve_dns(host, port)

        # -- 2. Prepare trace callback storage -------------------------
        trace_times: dict[str, float] = {}
        tls_info: dict[str, Any] = {}

        def _trace(name: str, info: dict[str, Any]) -> None:
            """Record ``perf_counter`` timestamps for connection phases."""
            now = time.perf_counter()
            trace_times[name] = now

            # Capture return_value from connect_tcp.complete
            if name == "connection.connect_tcp.complete":
                rv = info.get("return_value")
                if rv is not None:
                    try:
                        local = rv.get_extra_info("sockname")
                        if local:
                            tls_info["local_address"] = f"{local[0]}:{local[1]}"
                    except Exception:
                        pass

            # Capture TLS metadata from start_tls.complete
            if name == "connection.start_tls.complete":
                rv = info.get("return_value")
                if rv is not None:
                    try:
                        ssl_obj = rv.get_extra_info("ssl_object")
                        if isinstance(ssl_obj, ssl_module.SSLObject | ssl_module.SSLSocket):
                            tls_info["tls_protocol"] = ssl_obj.version()
                            cipher = ssl_obj.cipher()
                            if cipher:
                                tls_info["cipher_name"] = cipher[0]
                            cert = ssl_obj.getpeercert()
                            if cert:
                                tls_info["cert"] = cert
                    except Exception:
                        pass

        # -- 3. Send request -------------------------------------------
        start = time.monotonic()
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=parsed_headers,
                    content=content,
                    extensions={"trace": _trace},
                )

            elapsed = (time.monotonic() - start) * 1000  # ms

            # -- 4. Build response headers -----------------------------
            response_headers: list[dict[str, str]] = [
                {"key": k, "value": v} for k, v in response.headers.multi_items()
            ]
            body_text = response.text
            size = len(response.content)

            # -- 5. Compute timing breakdown ---------------------------
            tcp_ms = _phase_ms(trace_times, "connection.connect_tcp")
            tls_ms = _phase_ms(trace_times, "connection.start_tls")
            ttfb_ms = _phase_ms(
                trace_times,
                "http11.receive_response_headers",
                "http2.receive_response_headers",
            )
            download_ms = _phase_ms(
                trace_times,
                "http11.receive_response_body",
                "http2.receive_response_body",
            )
            known = dns_ms + tcp_ms + tls_ms + ttfb_ms + download_ms
            process_ms = max(0.0, elapsed - known)

            timing = TimingDict(
                dns_ms=round(dns_ms, 2),
                tcp_ms=round(tcp_ms, 2),
                tls_ms=round(tls_ms, 2),
                ttfb_ms=round(ttfb_ms, 2),
                download_ms=round(download_ms, 2),
                process_ms=round(process_ms, 2),
            )

            # -- 6. Compute size breakdown -----------------------------
            resp_headers_size = sum(
                len(k) + len(v) + 4  # ": " + "\r\n"
                for k, v in response.headers.raw
            )
            req_headers_size = sum(
                len(k.encode()) + len(v.encode()) + 4 for k, v in parsed_headers.items()
            )
            req_body_size = len(content) if content else 0

            # -- 7. Build network metadata -----------------------------
            http_version = getattr(response, "http_version", "HTTP/1.1")
            remote_addr = f"{remote_ip}:{port}" if remote_ip else ""
            local_addr = tls_info.get("local_address", "")

            cert = tls_info.get("cert")
            cert_cn = HttpService._extract_cert_field(cert, "subject") if cert else None
            issuer_cn = HttpService._extract_cert_field(cert, "issuer") if cert else None
            valid_until = cert.get("notAfter") if cert else None

            network = NetworkDict(
                http_version=http_version,
                remote_address=remote_addr,
                local_address=local_addr,
                tls_protocol=tls_info.get("tls_protocol"),
                cipher_name=tls_info.get("cipher_name"),
                certificate_cn=cert_cn,
                issuer_cn=issuer_cn,
                valid_until=valid_until,
            )

            # -- 8. Check for uncompressed size ------------------------
            result = HttpResponseDict(
                status_code=response.status_code,
                status_text=response.reason_phrase,
                headers=response_headers,
                body=body_text,
                elapsed_ms=round(elapsed, 1),
                size_bytes=size,
                timing=timing,
                request_headers_size=req_headers_size,
                request_body_size=req_body_size,
                response_headers_size=resp_headers_size,
                network=network,
            )

            content_encoding = response.headers.get("content-encoding", "").lower()
            if content_encoding in ("gzip", "br", "deflate"):
                result["response_uncompressed_size"] = len(body_text.encode("utf-8"))

            return result

        except httpx.ConnectError as exc:
            elapsed = (time.monotonic() - start) * 1000
            msg = f"Connection refused: {exc}"
            logger.warning(msg)
            return HttpResponseDict(error=msg, elapsed_ms=round(elapsed, 1))

        except httpx.TimeoutException as exc:
            elapsed = (time.monotonic() - start) * 1000
            msg = f"Request timed out: {exc}"
            logger.warning(msg)
            return HttpResponseDict(error=msg, elapsed_ms=round(elapsed, 1))

        except httpx.TooManyRedirects as exc:
            elapsed = (time.monotonic() - start) * 1000
            msg = f"Too many redirects: {exc}"
            logger.warning(msg)
            return HttpResponseDict(error=msg, elapsed_ms=round(elapsed, 1))

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            msg = f"Request failed: {exc}"
            logger.exception(msg)
            return HttpResponseDict(error=msg, elapsed_ms=round(elapsed, 1))
