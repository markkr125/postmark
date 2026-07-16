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

The non-debug send path delegates to
:func:`services.ai.chat.execution.send_core.run_shared_send`.  Debug
protocol step-through stays in this worker only.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal, Slot

from services.http.http_service import HttpResponseDict, HttpService
from services.scripting import ScriptEntry

if TYPE_CHECKING:
    from services.scripting import ScriptOutput
    from services.scripting.debug import DebugProtocol

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
    debug_paused = Signal(dict)  # DebugPauseInfo

    def __init__(self) -> None:
        """Initialise with empty request parameters."""
        super().__init__()
        self._method: str = "GET"
        self._url: str = ""
        self._headers: str | None = None
        self._body: str | None = None
        self._body_mode: str | None = None
        self._timeout: float = 30.0
        self._env_id: int | None = None
        self._request_id: int | None = None
        self._variable_collection_id: int | None = None
        self._request_name: str = ""
        self._auth_data: dict | None = None
        self._local_overrides: dict[str, str] = {}
        self._cancel_event = threading.Event()
        self._pre_scripts: list[ScriptEntry] = []
        self._test_scripts: list[ScriptEntry] = []
        self._declarative_test_script: ScriptEntry | None = None
        self._debug_protocol: DebugProtocol | None = None

    # -- Configuration (call before moveToThread) ----------------------

    def set_request(
        self,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
        body_mode: str | None = None,
        timeout: float = 30.0,
        env_id: int | None = None,
        request_id: int | None = None,
        request_name: str = "",
        auth_data: dict | None = None,
        variable_collection_id: int | None = None,
        local_overrides: dict[str, str] | None = None,
        pre_scripts: list[ScriptEntry] | None = None,
        test_scripts: list[ScriptEntry] | None = None,
        declarative_test_script: ScriptEntry | None = None,
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

        *pre_scripts* and *test_scripts* are the script inheritance
        chains resolved by ``ScriptService``.  Pre-request scripts
        run before the HTTP call; test scripts run after.

        *body_mode* ``binary`` means *body* is a filesystem path whose
        bytes are sent (not the path string).
        """
        self._method = method
        self._url = url
        self._headers = headers
        self._body = body
        self._body_mode = body_mode
        self._timeout = timeout
        self._env_id = env_id
        self._request_id = request_id
        self._variable_collection_id = variable_collection_id
        self._request_name = request_name or ""
        self._auth_data = auth_data
        self._local_overrides = local_overrides or {}
        self._pre_scripts = pre_scripts or []
        self._test_scripts = test_scripts or []
        self._declarative_test_script = declarative_test_script

    def set_debug_mode(self, protocol: DebugProtocol) -> None:
        """Enable debug execution mode with the given protocol.

        Must be called **before** the worker is moved to its thread.
        The protocol's ``on_pause`` callback will emit
        :attr:`debug_paused` on the main thread.
        """
        self._debug_protocol = protocol

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

        Pre-request scripts run after variable substitution but before
        the HTTP call.  Test scripts run after the response arrives.

        Non-debug sends use :func:`run_shared_send`.  Debug protocol
        step-through remains inline in :meth:`_run_debug_path`.
        """
        # 1. Check cancellation before starting the request
        if self._cancel_event.is_set():
            self.error.emit("Request cancelled")
            return

        if self._debug_protocol is not None:
            self._run_debug_path()
            return

        try:
            from services.ai.chat.execution.send_core import run_shared_send

            result = run_shared_send(
                method=self._method,
                url=self._url,
                headers=self._headers,
                body=self._body,
                body_mode=self._body_mode,
                timeout=self._timeout,
                request_id=self._request_id,
                request_name=self._request_name,
                env_id=self._env_id,
                variable_collection_id=self._variable_collection_id,
                local_overrides=self._local_overrides,
                auth_data=self._auth_data,
                pre_scripts=self._pre_scripts,
                test_scripts=self._test_scripts,
                declarative_test_script=self._declarative_test_script,
                persist_globals=True,
                cancel_event=self._cancel_event,
                acquire_agent_slot=False,
            )
            if result.get("cancelled"):
                self.error.emit("Request cancelled")
                return
            if not result.get("ok"):
                self.error.emit(str(result.get("error") or "Send failed"))
                return
            response = result.get("response")
            if not isinstance(response, dict):
                self.error.emit("Send failed: empty response")
                return
            self.finished.emit(response)
        except Exception as exc:
            logger.exception("HTTP send worker failed")
            self.error.emit(str(exc))

    def _run_debug_path(self) -> None:
        """Send with debug protocol step-through (worker-only path)."""
        try:
            method = self._method
            url = self._url
            headers = self._headers
            body = self._body

            # 2. Resolve collection + environment variables (DB on worker thread)
            from services.environment_service import EnvironmentService

            variables = EnvironmentService.build_combined_variable_map(
                self._env_id,
                self._request_id,
                collection_id=self._variable_collection_id,
            )

            # 2b. Apply per-request local overrides (highest precedence)
            if self._local_overrides:
                variables.update(self._local_overrides)

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
                    method=method,
                    body=body,
                )

            # 4. Run pre-request scripts (may mutate request + variables)
            from services.http.header_utils import parse_header_dict
            from services.scripting.context import (
                apply_request_mutations,
                apply_variable_changes,
                build_pre_request_context,
                build_script_info,
                load_globals,
                save_globals,
            )
            from services.scripting.engine import run_debug_chain

            env_name = ""
            if self._env_id is not None:
                env = EnvironmentService.get_environment(self._env_id)
                if env is not None:
                    env_name = str(env.name or "")

            global_vars = load_globals() if (self._pre_scripts or self._test_scripts) else {}

            pre_output = None
            protocol = self._debug_protocol
            assert protocol is not None

            if self._pre_scripts:
                header_dict = parse_header_dict(headers) if headers else {}
                pre_ctx = build_pre_request_context(
                    method=method,
                    url=url,
                    headers=header_dict,
                    body=body or "",
                    variables=variables,
                    environment_vars={},
                    collection_vars={},
                    global_vars=global_vars,
                    info=build_script_info(
                        event_name="prerequest",
                        request_name=self._request_name,
                        request_id=str(self._request_id or ""),
                    ),
                    auth=self._auth_data,
                    environment_name=env_name,
                )
                protocol.start(
                    on_pause=lambda info: self.debug_paused.emit(info),
                )
                pre_output = run_debug_chain(
                    self._pre_scripts,
                    pre_ctx,
                    protocol,
                    script_type="pre_request",
                )
                # Persist global variable changes.
                if pre_output.get("global_variable_changes"):
                    save_globals(pre_output["global_variable_changes"])
                    global_vars.update(pre_output["global_variable_changes"])
                # Apply request mutations from pre-request scripts
                if pre_output.get("request_mutations"):
                    method, url, header_dict, body_str = apply_request_mutations(
                        pre_output["request_mutations"],
                        method=method,
                        url=url,
                        headers=header_dict,
                        body=body or "",
                    )
                    body = body_str
                    # Rebuild headers string from dict
                    headers = "\n".join(f"{k}: {v}" for k, v in header_dict.items())
                # Apply variable changes
                if pre_output.get("variable_changes"):
                    variables = apply_variable_changes(pre_output["variable_changes"], variables)

            if self._cancel_event.is_set():
                self.error.emit("Request cancelled")
                return

            result: HttpResponseDict = HttpService.send_request(
                method=method,
                url=url,
                headers=headers,
                body=body,
                body_mode=self._body_mode,
                timeout=self._timeout,
            )

            # 5. Check cancellation after the request completes
            if self._cancel_event.is_set():
                self.error.emit("Request cancelled")
                return

            # 6. Run test scripts (debug path skips declarative tests)
            all_test_results: list[Any] = []
            all_console_logs: list[Any] = []
            all_var_changes: dict[str, str] = {}
            pre_request_errors: list[Any] = []
            pre_console_logs: list[Any] = []
            pre_var_changes: dict[str, str] = {}

            if pre_output:
                for tr in pre_output.get("test_results", []):
                    if tr.get("name") == "(runtime error)":
                        source = tr.get("source_name", "pre-request")
                        error = tr.get("error", "unknown error")
                        pre_request_errors.append(tr)
                        all_console_logs.append(
                            {
                                "level": "error",
                                "message": f"[{source}] {error}",
                                "timestamp": 0,
                            }
                        )
                pre_console_logs = list(pre_output.get("console_logs", []))
                all_console_logs.extend(pre_console_logs)
                pre_var_changes = dict(pre_output.get("variable_changes", {}))
                all_var_changes.update(pre_var_changes)

            if self._test_scripts:
                from services.scripting.context import build_script_info, build_test_context

                test_ctx = build_test_context(
                    request_data={
                        "url": url,
                        "method": method,
                        "headers": parse_header_dict(headers) if headers else {},
                        "body": body or "",
                    },
                    response_data={
                        "status_code": result.get("status_code", 0),
                        "status": result.get("status_text", ""),
                        "headers": {
                            h["key"]: h["value"]
                            for h in result.get("headers", [])
                            if isinstance(h, dict)
                        },
                        "body": result.get("body", ""),
                        "elapsed_ms": result.get("elapsed_ms", 0),
                        "size_bytes": result.get("size_bytes", 0),
                    },
                    variables=variables,
                    environment_vars={},
                    collection_vars={},
                    global_vars=global_vars,
                    info=build_script_info(
                        event_name="test",
                        request_name=self._request_name,
                        request_id=str(self._request_id or ""),
                    ),
                    environment_name=env_name,
                )

                test_output: dict[str, Any] | ScriptOutput
                if not protocol._stop_requested:
                    protocol.start(
                        on_pause=lambda info: self.debug_paused.emit(info),
                    )
                test_output = run_debug_chain(
                    self._test_scripts,
                    test_ctx,
                    protocol,
                    script_type="test",
                )
                all_test_results.extend(test_output.get("test_results", []))
                all_console_logs.extend(test_output.get("console_logs", []))
                all_var_changes.update(test_output.get("variable_changes", {}))
                if test_output.get("global_variable_changes"):
                    save_globals(test_output["global_variable_changes"])

            # 7. Attach script results to the response dict
            final = dict(result)
            if all_test_results:
                final["test_results"] = all_test_results
            if all_console_logs:
                final["console_logs"] = all_console_logs
            if all_var_changes:
                final["variable_changes"] = all_var_changes
            if pre_request_errors:
                final["pre_request_errors"] = pre_request_errors
            if pre_console_logs:
                final["pre_request_console_logs"] = pre_console_logs
            if pre_var_changes:
                final["pre_request_variable_changes"] = pre_var_changes
            if self._pre_scripts:
                final["has_pre_request_scripts"] = True

            self.finished.emit(final)
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

        Delegates to :func:`services.ai.chat.execution.send_core.apply_send_auth`.
        """
        from services.ai.chat.execution.send_core import apply_send_auth

        return apply_send_auth(
            auth_data,
            url,
            headers,
            variables,
            method=method,
            body=body,
        )


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
            from services.http.graphql_schema_service import GraphQLSchemaService

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
