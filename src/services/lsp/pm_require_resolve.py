"""Resolve unversioned npm/jsr specifiers to a pinned version for LSP types."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import quote

from services.scripting.js_runtime import PmRequireSpec

logger = logging.getLogger(__name__)

_REGISTRY_TIMEOUT_S = 15.0


def types_specifier(spec: PmRequireSpec) -> str:
    """Return runtime specifier for Deno cache (latest when version omitted)."""
    if spec.version:
        return spec.specifier
    pinned = _resolve_latest_version(spec)
    return pinned or spec.specifier


def npm_types_package_name(npm_name: str) -> str | None:
    """Return the DefinitelyTyped package name for an npm package, or ``None`` for JSR."""
    if npm_name.startswith("@"):
        # ``@scope/pkg`` → ``@types/scope__pkg``
        return f"@types/{npm_name[1:].replace('/', '__')}"
    return f"@types/{npm_name}"


def npm_types_specifier(spec: PmRequireSpec) -> str | None:
    """Return ``npm:@types/…@version`` for npm specs (``None`` for JSR)."""
    if spec.registry != "npm":
        return None
    pkg = npm_types_package_name(spec.name)
    if not pkg:
        return None
    if spec.version:
        return f"npm:{pkg}@{spec.version}"
    ver = _npm_latest_version(pkg)
    return f"npm:{pkg}@{ver}" if ver else f"npm:{pkg}"


def primary_type_export_name(types_dir: Path) -> str:
    """Guess the primary exported type name from an ``@types`` package root."""
    index = types_dir / "index.d.ts"
    if not index.is_file():
        return "default"
    text = index.read_text(encoding="utf-8")
    if "interface LoDashStatic" in text:
        return "LoDashStatic"
    if "export default" in text:
        return "default"
    if "export =" in text:
        return "LoDashStatic" if "LoDashStatic" in text else "default"
    return "default"


def _resolve_latest_version(spec: PmRequireSpec) -> str | None:
    """Look up registry ``latest`` and return ``reg:name@version`` or ``None``."""
    if spec.registry == "npm":
        ver = _npm_latest_version(spec.name)
    elif spec.registry == "jsr":
        ver = _jsr_latest_version(spec.name)
    else:
        return None
    if not ver:
        return None
    return f"{spec.registry}:{spec.name}@{ver}"


def _fetch_json(url: str) -> dict | None:
    """Best-effort GET returning parsed JSON or ``None``."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_REGISTRY_TIMEOUT_S) as resp:
            body = resp.read().decode()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("registry lookup failed for %s: %s", url, exc)
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.debug("registry JSON parse failed for %s: %s", url, exc)
        return None
    return parsed if isinstance(parsed, dict) else None


def _npm_latest_version(package: str) -> str | None:
    """Return npm ``dist-tags.latest`` for *package* (``lodash`` or ``@scope/pkg``)."""
    path = quote(package, safe="@/")
    data = _fetch_json(f"https://registry.npmjs.org/{path}")
    if not data:
        return None
    dist_tags = data.get("dist-tags")
    if not isinstance(dist_tags, dict):
        return None
    latest = dist_tags.get("latest")
    if isinstance(latest, str) and latest.strip():
        return latest.strip()
    return None


def _jsr_latest_version(package: str) -> str | None:
    """Return JSR ``meta.json`` ``latest`` for *package* (``@scope/name``)."""
    if not package.startswith("@"):
        logger.debug("jsr package %r missing @ scope", package)
        return None
    path = quote(package, safe="@/")
    data = _fetch_json(f"https://jsr.io/{path}/meta.json")
    if not data:
        return None
    latest = data.get("latest")
    if isinstance(latest, str) and latest.strip():
        return latest.strip()
    return None


__all__ = [
    "npm_types_package_name",
    "npm_types_specifier",
    "primary_type_export_name",
    "types_specifier",
]
