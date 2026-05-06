"""Helpers for tests that need Deno and a working Esprima (``deno run``) parse."""

from __future__ import annotations


def deno_and_esprima_available() -> bool:
    """True when ``deno`` runs and :func:`esprima_parse_to_dict` returns data.

    Some machines expose ``deno`` for ``--version`` but the Esprima subprocess
    still fails (or returns ``None``); those cases should skip strict JS tests.
    """
    from services.scripting.engine import ScriptLinter
    from services.scripting.runtime_settings import RuntimeSettings

    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    if not st.get("available"):
        return False
    r = ScriptLinter._esprima_parse_result("var x=1;")
    return r is not None
