"""Background workers for HTTP requests on a dedicated QThread.

Follows the ``QObject.moveToThread()`` pattern established by
``_ImportWorker`` in ``import_dialog.py``.  Each worker is single-use:
create, configure, move to a ``QThread``, start, and discard after the
``finished`` or ``error`` signal fires.

Workers:
    HttpSendWorker — send a regular HTTP request.
    SchemaFetchWorker — fetch a GraphQL schema via introspection.

Supports **cancellation**: the owning tab calls ``cancel()`` which sets a
``threading.Event`` flag checked before and after the network call.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal, Slot

from services.http.http_service import HttpResponseDict, HttpService

logger = logging.getLogger(__name__)


class HttpSendWorker(QObject):
    """Execute a single HTTP request on a background thread.

    Set request parameters via the setter methods **before** calling
    ``moveToThread()``.  Connect ``finished`` and ``error`` signals,
    then start the owning ``QThread``.

    Optionally accepts *env_id* and *auth_data* so that variable
    substitution and auth injection happen on the worker thread
    rather than the GUI thread.

    Signals:
        finished(dict): Emitted with an :class:`HttpResponseDict` on success.
        error(str): Emitted with an error message on failure.
    """

    finished = Signal(dict)  # HttpResponseDict
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with empty request parameters."""
        super().__init__()
        self._method: str = "GET"
        self._url: str = ""
        self._headers: str | None = None
        self._body: str | None = None
        self._timeout: float = 30.0
        self._env_id: int | None = None
        self._request_id: int | None = None
        self._auth_data: dict | None = None
        self._local_overrides: dict[str, str] = {}
        self._cancel_event = threading.Event()

    # -- Configuration (call before moveToThread) ----------------------

    def set_request(
        self,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
        timeout: float = 30.0,
        env_id: int | None = None,
        request_id: int | None = None,
        auth_data: dict | None = None,
        local_overrides: dict[str, str] | None = None,
    ) -> None:
        """Configure the HTTP request to send.

        Must be called **before** the worker is moved to its thread.
        When *env_id*, *request_id*, or *auth_data* are provided,
        variable substitution and auth injection happen on the worker
        thread.  Collection variables (inherited from the parent chain
        of *request_id*) are merged with environment variables, with
        environment variables taking precedence.

        *local_overrides* are per-request overrides set by the user
        via the variable popup ("use for this request only").  They
        take highest precedence.
        """
        self._method = method
        self._url = url
        self._headers = headers
        self._body = body
        self._timeout = timeout
        self._env_id = env_id
        self._request_id = request_id
        self._auth_data = auth_data
        self._local_overrides = local_overrides or {}

    def cancel(self) -> None:
        """Request cancellation of the in-flight HTTP request.

        Thread-safe — can be called from any thread.
        """
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancel_event.is_set()

    # -- Execution (runs on the worker thread) -------------------------

    @Slot()
    def run(self) -> None:
        """Send the HTTP request and emit the result signal.

        Checks the cancellation flag before and after the network call.
        When *env_id* or *auth_data* were provided, variable substitution
        and auth injection happen here on the worker thread.
        """
        # 1. Check cancellation before starting the request
        if self._cancel_event.is_set():
            self.error.emit("Request cancelled")
            return

        try:
            url = self._url
            headers = self._headers
            body = self._body

            # 2. Resolve collection + environment variables (DB on worker thread)
            from services.environment_service import EnvironmentService

            variables = EnvironmentService.build_combined_variable_map(
                self._env_id,
                self._request_id,
            )

            # 2b. Apply per-request local overrides (highest precedence)
            if self._local_overrides:
                variables.update(self._local_overrides)

            if variables:
                url = EnvironmentService.substitute(url, variables)
                if headers:
                    headers = EnvironmentService.substitute(headers, variables)
                if body:
                    body = EnvironmentService.substitute(body, variables)

            # 3. Apply auth configuration
            if self._auth_data:
                url, headers = self._apply_auth(
                    self._auth_data,
                    url,
                    headers,
                    variables,
                    method=self._method,
                    body=body,
                )

            result: HttpResponseDict = HttpService.send_request(
                method=self._method,
                url=url,
                headers=headers,
                body=body,
                timeout=self._timeout,
            )

            # 4. Check cancellation after the request completes
            if self._cancel_event.is_set():
                self.error.emit("Request cancelled")
                return

            self.finished.emit(dict(result))
        except Exception as exc:
            logger.exception("HTTP send worker failed")
            self.error.emit(str(exc))

    @staticmethod
    def _apply_auth(
        auth_data: dict | None,
        url: str,
        headers: str | None,
        variables: dict[str, str],
        *,
        method: str = "GET",
        body: str | None = None,
    ) -> tuple[str, str | None]:
        """Inject auth credentials into the URL or headers.

        Substitutes environment variables in auth entry values, then
        delegates to :func:`services.http.auth_handler.apply_auth`.
        Returns the (possibly modified) ``url`` and ``headers``.
        """
        if not auth_data:
            return url, headers

        from services.environment_service import EnvironmentService
        from services.http.auth_handler import apply_auth
        from services.http.header_utils import parse_header_dict

        sub = EnvironmentService.substitute
        auth_type = auth_data.get("type", "noauth")

        # Substitute variables in entry values (shallow copy to avoid mutation)
        entries = auth_data.get(auth_type, [])
        if entries and variables:
            substituted = dict(auth_data)
            substituted[auth_type] = [
                {**e, "value": sub(str(e.get("value", "")), variables)}
                if isinstance(e, dict)
                else e
                for e in entries
            ]
        else:
            substituted = auth_data

        # Convert header string to dict, apply auth, convert back
        hdr_dict = parse_header_dict(headers)
        url, hdr_dict = apply_auth(
            substituted,
            url,
            hdr_dict,
            method=method,
            body=body,
        )
        new_headers: str | None = (
            "\n".join(f"{k}: {v}" for k, v in hdr_dict.items()) if hdr_dict else None
        )
        return url, new_headers


class SchemaFetchWorker(QObject):
    """Fetch a GraphQL schema via introspection on a background thread.

    Set the endpoint via :meth:`set_endpoint` **before** calling
    ``moveToThread()``.  Connect ``finished`` and ``error`` signals,
    then start the owning ``QThread``.

    Signals:
        finished(dict): Emitted with a :class:`SchemaResultDict` on success.
        error(str): Emitted with an error message on failure.
    """

    finished = Signal(dict)  # SchemaResultDict
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with empty endpoint parameters."""
        super().__init__()
        self._url: str = ""
        self._headers: dict[str, str] | None = None

    # -- Configuration (call before moveToThread) ----------------------

    def set_endpoint(
        self,
        *,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Configure the GraphQL endpoint to introspect.

        Must be called **before** the worker is moved to its thread.
        """
        self._url = url
        self._headers = headers

    # -- Execution (runs on the worker thread) -------------------------

    @Slot()
    def run(self) -> None:
        """Send the introspection query and emit the result signal."""
        try:
            from services.http.graphql_schema_service import \
                GraphQLSchemaService

            result = GraphQLSchemaService.fetch_schema(
                self._url,
                headers=self._headers,
            )
            self.finished.emit(dict(result))
        except Exception as exc:
            logger.exception("Schema fetch worker failed")
            self.error.emit(str(exc))


class OAuth2TokenWorker(QObject):
    """Execute an OAuth 2.0 token flow on a background thread.

    Set configuration via :meth:`set_config` **before** calling
    ``moveToThread()``.  Connect ``finished`` and ``error`` signals,
    then start the owning ``QThread``.

    Signals:
        finished(dict): Emitted with an :class:`OAuth2TokenResult` on success.
        error(str): Emitted with an error message on failure.
    """

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise with empty configuration."""
        super().__init__()
        self._config: dict = {}

    def set_config(self, config: dict) -> None:
        """Configure the OAuth 2.0 flow parameters.

        Must be called **before** the worker is moved to its thread.
        """
        self._config = config

    @Slot()
    def run(self) -> None:
        """Perform the token exchange and emit the result signal."""
        try:
            from services.http.oauth2_service import OAuth2Service

            result = OAuth2Service.get_token(self._config)
            if result.get("error"):
                self.error.emit(str(result["error"]))
            else:
                self.finished.emit(dict(result))
        except Exception as exc:
            logger.exception("OAuth 2.0 token worker failed")
            self.error.emit(str(exc))
            self.error.emit(str(exc))
