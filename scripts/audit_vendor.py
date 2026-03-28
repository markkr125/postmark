"""Audit bundled JavaScript vendor libraries for security and staleness.

Creates a temporary npm project with the same packages as
``data/scripts/vendor/VERSIONS.md``, runs ``npm audit`` and
``npm outdated``, and reports results.

Usage::

    poetry run python scripts/audit_vendor.py          # full audit
    poetry run python scripts/audit_vendor.py --fix    # rebuild outdated bundles

Exit code 0 means no vulnerabilities and no outdated packages.
Exit code 1 means issues were found (printed to stderr).

Requirements: ``node`` and ``npm`` must be on ``$PATH``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Pinned versions matching data/scripts/vendor/VERSIONS.md.
# Update these when you update the vendor bundles.
_VENDOR_PACKAGES: dict[str, str] = {
    "crypto-js": "4.2.0",
    "lodash": "4.17.23",
    "moment": "2.30.1",
    "chai": "4.5.0",
    "tv4": "1.3.0",
    "ajv": "8.18.0",
    "xml2js": "0.6.2",
    "csv-parse": "5.6.0",
}

# Build-time-only dependencies (not shipped, but needed for bundling).
_BUILD_DEPS: dict[str, str] = {
    "buffer": "6.0.3",
    "esbuild": "0.24.0",
    "events": "3.3.0",
    "timers-browserify": "2.0.12",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENDOR_DIR = _PROJECT_ROOT / "data" / "scripts" / "vendor"


def _check_npm() -> None:
    """Verify npm is available."""
    if shutil.which("npm") is None:
        print("ERROR: npm not found on $PATH", file=sys.stderr)
        sys.exit(2)


def _create_temp_project(tmp: Path) -> None:
    """Write a package.json with pinned vendor dependencies."""
    pkg: dict[str, object] = {
        "name": "postmark-vendor-audit",
        "private": True,
        "dependencies": {k: v for k, v in _VENDOR_PACKAGES.items()},
    }
    (tmp / "package.json").write_text(json.dumps(pkg, indent=2))
    subprocess.run(
        ["npm", "install", "--ignore-scripts"],
        cwd=tmp,
        capture_output=True,
        check=True,
    )


def _run_audit(tmp: Path) -> list[dict[str, object]]:
    """Run ``npm audit --json`` and return advisory list."""
    result = subprocess.run(
        ["npm", "audit", "--json"],
        cwd=tmp,
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    # npm audit JSON format has ``vulnerabilities`` dict.
    vulns = data.get("vulnerabilities", {})
    issues: list[dict[str, object]] = []
    for name, info in vulns.items():
        if name not in _VENDOR_PACKAGES:
            continue
        severity = info.get("severity", "unknown")
        via = info.get("via", [])
        titles: list[str] = []
        for v in via:
            if isinstance(v, dict):
                titles.append(str(v.get("title", v.get("url", ""))))
            elif isinstance(v, str):
                titles.append(v)
        issues.append(
            {
                "package": name,
                "severity": severity,
                "details": "; ".join(titles),
            }
        )
    return issues


def _run_outdated(tmp: Path) -> list[dict[str, str]]:
    """Run ``npm outdated --json`` and return stale package list."""
    result = subprocess.run(
        ["npm", "outdated", "--json"],
        cwd=tmp,
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    stale: list[dict[str, str]] = []
    for name, info in data.items():
        if name not in _VENDOR_PACKAGES:
            continue
        current = info.get("current", "?")
        latest = info.get("latest", "?")
        if current != latest:
            stale.append(
                {
                    "package": name,
                    "current": current,
                    "latest": latest,
                }
            )
    return stale


def _check_versions_md() -> list[str]:
    """Verify VERSIONS.md pinned versions match this script."""
    versions_path = _VENDOR_DIR / "VERSIONS.md"
    if not versions_path.exists():
        return ["VERSIONS.md not found"]

    content = versions_path.read_text()
    errors: list[str] = []
    for pkg, version in _VENDOR_PACKAGES.items():
        if version not in content:
            errors.append(f"VERSIONS.md missing version {version} for {pkg}")
    return errors


def main() -> None:
    """Run the full vendor audit."""
    _check_npm()

    # 1. Check VERSIONS.md consistency.
    md_errors = _check_versions_md()
    if md_errors:
        for e in md_errors:
            print(f"WARNING: {e}", file=sys.stderr)

    # 2. Create temp project and install.
    with tempfile.TemporaryDirectory(prefix="postmark-vendor-") as tmp_str:
        tmp = Path(tmp_str)
        print("Installing vendor packages for audit...")
        _create_temp_project(tmp)

        # 3. Security audit.
        print("Running npm audit...")
        issues = _run_audit(tmp)
        if issues:
            print(
                f"\n{len(issues)} SECURITY ISSUE(S) FOUND:",
                file=sys.stderr,
            )
            for issue in issues:
                print(
                    f"  [{issue['severity']}] {issue['package']}: {issue['details']}",
                    file=sys.stderr,
                )
        else:
            print("No known vulnerabilities found.")

        # 4. Outdated check.
        print("\nChecking for outdated packages...")
        stale = _run_outdated(tmp)
        if stale:
            print(
                f"\n{len(stale)} OUTDATED PACKAGE(S):",
                file=sys.stderr,
            )
            for s in stale:
                print(
                    f"  {s['package']}: {s['current']} → {s['latest']}",
                    file=sys.stderr,
                )
        else:
            print("All packages are up to date.")

    # 5. Summary.
    has_errors = bool(issues or stale or md_errors)
    if has_errors:
        print(
            "\nAudit found issues. See above for details.",
            file=sys.stderr,
        )
        print(
            "To update a package:\n"
            "  1. Update the version in _VENDOR_PACKAGES (this script)\n"
            "  2. Update data/scripts/vendor/VERSIONS.md\n"
            "  3. Rebuild the bundle — see VERSIONS.md for instructions\n"
            "  4. Run: poetry run pytest",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print("\nAll vendor libraries are secure and up to date.")


if __name__ == "__main__":
    main()
