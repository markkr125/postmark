"""HTTP request execution service.

Wraps ``httpx`` to send HTTP requests and return structured response data.
All methods are ``@staticmethod`` — no instance state.  Errors are returned
as part of the response dict, never raised into callers.
"""

from __future__ import annotations

import logging
import time
from typing import NotRequired, TypedDict

import httpx

logger = logging.getLogger(__name__)

# Default timeout in seconds for HTTP requests.
DEFAULT_TIMEOUT = 30.0


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


def _build_headers(raw: str | None) -> dict[str, str]:
    """Parse a newline-separated header string into a mapping.

    Each line should be ``Key: Value``.  Malformed lines are silently
    skipped.
    """
    if not raw:
        return {}

    headers: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
    return headers


class HttpService:
    """Send HTTP requests and return structured response dicts.

    Every method is a ``@staticmethod`` — no shared state.
    """

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
        parsed_headers = _build_headers(headers)
        content: bytes | None = body.encode("utf-8") if body else None

        start = time.monotonic()
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=parsed_headers,
                    content=content,
                )

            elapsed = (time.monotonic() - start) * 1000  # ms

            response_headers: list[dict[str, str]] = [
                {"key": k, "value": v} for k, v in response.headers.multi_items()
            ]
            body_text = response.text
            size = len(response.content)

            return HttpResponseDict(
                status_code=response.status_code,
                status_text=response.reason_phrase,
                headers=response_headers,
                body=body_text,
                elapsed_ms=round(elapsed, 1),
                size_bytes=size,
            )

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
