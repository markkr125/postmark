"""Static diagnostics for direct ``pm.require('local:…')`` dependencies in host scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from database.database import get_session
from services.lsp.client import Diagnostic as LspDiagnostic
from services.scripting.engine import ScriptLinter
from services.scripting.local_script_modules import (
    LocalScriptModule,
    _import_allowed,
    build_module_index,
    iter_pm_require_local_paths_js,
)
from services.scripting.pm_api_linter import Diagnostic as LinterDiagnostic

_PM_REQUIRE_SITE_RE = re.compile(
    r"""(?:(?P<kind>const|let|var)\s+(?P<name>\w+)\s*=\s*)?"""
    r"""pm\s*\.\s*require\s*\(\s*['"]local:(?P<path>[^'"]+)['"]\s*\)""",
    re.MULTILINE,
)


@dataclass(frozen=True)
class RequireSite:
    """A ``pm.require('local:…')`` call site in a host script buffer."""

    rel_path: str
    line: int
    column: int
    binding_name: str | None


@dataclass(frozen=True)
class RequireAnchorDiagnostic:
    """Gutter marker on the host ``pm.require`` line (1-based positions)."""

    line: int
    column: int
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class LocalDependencyDiagnosticBundle:
    """Merged dependency diagnostics for a host script."""

    dependency_rows: list[LspDiagnostic]
    require_anchors: list[RequireAnchorDiagnostic]
    resolution_rows: list[LspDiagnostic]


def iter_pm_require_local_sites(source: str) -> list[RequireSite]:
    """Return direct ``local:`` require sites with 1-based line/column of ``pm``."""
    sites: list[RequireSite] = []
    for m in _PM_REQUIRE_SITE_RE.finditer(source):
        rel_path = m.group("path").strip()
        if not rel_path:
            continue
        line, column = _line_col_1based(source, m.start())
        name = m.group("name")
        sites.append(
            RequireSite(
                rel_path=rel_path,
                line=line,
                column=column,
                binding_name=name.strip() if name else None,
            )
        )
    return sites


def collect_direct_local_dependency_diagnostics(
    user_source: str,
    language: str,
) -> LocalDependencyDiagnosticBundle:
    """Lint each directly required local module; anchor errors on the require line."""
    if not (user_source or "").strip():
        return LocalDependencyDiagnosticBundle([], [], [])

    lang = (language or "javascript").lower().strip()
    sites = iter_pm_require_local_sites(user_source)
    if not sites:
        return LocalDependencyDiagnosticBundle([], [], [])

    with get_session() as session:
        index = build_module_index(session)

    dependency_rows: list[LspDiagnostic] = []
    require_anchors: list[RequireAnchorDiagnostic] = []
    resolution_rows: list[LspDiagnostic] = []

    for site in sites:
        mod = index.get(site.rel_path)
        if mod is None:
            msg = (
                f"No local script at {site.rel_path!r} "
                "(check the Local scripts tree; paths are case-sensitive)"
            )
            resolution_rows.append(_host_resolution_row(site, msg))
            require_anchors.append(
                RequireAnchorDiagnostic(
                    line=site.line,
                    column=site.column,
                    message=f"Local dependency not found: {site.rel_path}",
                )
            )
            continue

        ext = mod.rel_path[mod.rel_path.rfind(".") :]
        if not _import_allowed(lang, ext):
            msg = (
                f"Cannot import {mod.rel_path!r} from a "
                f"{lang} script (extension {ext!r} is not allowed)"
            )
            resolution_rows.append(_host_resolution_row(site, msg))
            require_anchors.append(
                RequireAnchorDiagnostic(
                    line=site.line,
                    column=site.column,
                    message=msg,
                )
            )
            continue

        linter_diags = _lint_local_module(mod)
        lsp_rows = [_linter_diag_to_dependency_row(d, mod) for d in linter_diags]
        dependency_rows.extend(lsp_rows)

        errors = [d for d in linter_diags if d.get("severity", "error") == "error"]
        if errors:
            require_anchors.append(_aggregate_require_anchor(site, mod, errors))

    return LocalDependencyDiagnosticBundle(
        dependency_rows=dependency_rows,
        require_anchors=require_anchors,
        resolution_rows=resolution_rows,
    )


def has_error_severity_dependency_issues(bundle: LocalDependencyDiagnosticBundle) -> bool:
    """Return whether *bundle* contains error-severity dependency or resolution issues."""
    if any(
        (row.severity or "").lower() == "error"
        for row in (*bundle.dependency_rows, *bundle.resolution_rows)
    ):
        return True
    return any((anchor.severity or "").lower() == "error" for anchor in bundle.require_anchors)


def direct_local_paths_in_source(source: str) -> list[str]:
    """Unique virtual paths from direct ``pm.require('local:…')`` in *source*."""
    return iter_pm_require_local_paths_js(source)


def _line_col_1based(source: str, index: int) -> tuple[int, int]:
    line = source.count("\n", 0, index) + 1
    last_nl = source.rfind("\n", 0, index)
    column = index - last_nl if last_nl >= 0 else index + 1
    return line, column


def _lint_local_module(mod: LocalScriptModule) -> list[LinterDiagnostic]:
    ext = mod.rel_path[mod.rel_path.rfind(".") :]
    mod_lang = (mod.language or "javascript").lower().strip()
    if ext == ".cjs":
        return ScriptLinter.check_commonjs_local_script(mod.source)
    if ext == ".py":
        return ScriptLinter.check(mod.source, "python")
    return ScriptLinter.check_es_module(mod.source, mod_lang)


def _linter_diag_to_dependency_row(
    d: LinterDiagnostic,
    mod: LocalScriptModule,
) -> LspDiagnostic:
    line0 = max(0, int(d["line"]) - 1)
    col0 = max(0, int(d["column"]) - 1)
    return LspDiagnostic(
        line=line0,
        column=col0,
        end_line=line0,
        end_column=col0 + 1,
        severity=str(d.get("severity", "error")),
        message=str(d["message"]),
        source="postmark",
        related_local_path=mod.rel_path,
        related_local_script_id=mod.script_id,
        related_line=line0,
        related_column=col0,
    )


def _host_resolution_row(site: RequireSite, message: str) -> LspDiagnostic:
    line0 = max(0, site.line - 1)
    col0 = max(0, site.column - 1)
    return LspDiagnostic(
        line=line0,
        column=col0,
        end_line=line0,
        end_column=col0 + 1,
        severity="error",
        message=message,
        source="postmark",
        related_local_path=site.rel_path,
        related_local_script_id=None,
        related_line=None,
        related_column=None,
    )


def _aggregate_require_anchor(
    site: RequireSite,
    mod: LocalScriptModule,
    errors: list[LinterDiagnostic],
) -> RequireAnchorDiagnostic:
    first = errors[0]
    base = mod.rel_path.rsplit("/", 1)[-1]
    detail = str(first["message"])
    if len(errors) == 1:
        summary = f"Dependency error ({base}:{first['line']}): {detail}"
    else:
        summary = f"Dependency has {len(errors)} errors ({base}:{first['line']}): {detail}"
    return RequireAnchorDiagnostic(
        line=site.line,
        column=site.column,
        message=summary,
        severity="error",
    )
