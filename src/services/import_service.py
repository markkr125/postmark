"""Service layer for importing collections, environments, and requests.

Orchestrates the import parsers and repository functions.  All database
access from the UI layer should go through this module.
"""

from __future__ import annotations

import logging
from pathlib import Path

from database.models.collections.import_repository import import_collection_tree
from database.models.environments.environment_repository import create_environment

from .import_parser import (
    ImportResult,
    ImportSummary,
    fetch_and_parse_url,
    parse_archive_folder,
    parse_collection_file,
    parse_curl,
    parse_raw_text,
)

logger = logging.getLogger(__name__)


class ImportService:
    """Service that coordinates parsing and persisting imported data.

    All methods are ``@staticmethod`` — the class exists for consistency
    with ``CollectionService`` and future extensibility.
    """

    @staticmethod
    def import_files(paths: list[Path]) -> ImportSummary:
        """Import one or more files (collections or environments).

        Each file is auto-detected as a Postman collection or environment.
        """
        all_results = ImportResult(collections=[], environments=[], errors=[])

        for path in paths:
            result = parse_archive_folder(path) if path.is_dir() else parse_collection_file(path)
            all_results.get("collections", []).extend(result.get("collections", []))
            all_results.get("environments", []).extend(result.get("environments", []))
            all_results.get("errors", []).extend(result.get("errors", []))

        return _persist(all_results)

    @staticmethod
    def import_folder(path: Path) -> ImportSummary:
        """Import a folder — either a Postman archive or a directory of JSON files."""
        result = parse_archive_folder(path)
        return _persist(result)

    @staticmethod
    def import_text(text: str) -> ImportSummary:
        """Import from raw text — auto-detects cURL, JSON, or URL."""
        result = parse_raw_text(text)
        return _persist(result)

    @staticmethod
    def import_curl(text: str) -> ImportSummary:
        """Import one or more cURL commands."""
        result = parse_curl(text)
        return _persist(result)

    @staticmethod
    def import_url(url: str) -> ImportSummary:
        """Fetch a URL and import its contents."""
        result = fetch_and_parse_url(url)
        return _persist(result)


def _persist(result: ImportResult) -> ImportSummary:
    """Persist parsed data to the database and return a summary."""
    summary = ImportSummary(
        collections_imported=0,
        requests_imported=0,
        responses_imported=0,
        environments_imported=0,
        errors=list(result.get("errors", [])),
    )

    # 1. Import collections
    for coll in result.get("collections", []):
        try:
            counters = import_collection_tree(dict(coll))  # type: ignore[arg-type]
            summary["collections_imported"] += counters["collections_imported"]
            summary["requests_imported"] += counters["requests_imported"]
            summary["responses_imported"] += counters["responses_imported"]
        except Exception as exc:
            name = coll.get("name", "<unknown>")
            summary["errors"].append(f"Failed to import collection {name!r}: {exc}")
            logger.exception("Failed to import collection %r", name)

    # 2. Import environments
    for env in result.get("environments", []):
        try:
            create_environment(
                name=env.get("name", "Untitled Environment"),
                values=env.get("values"),
            )
            summary["environments_imported"] += 1
        except Exception as exc:
            name = env.get("name", "<unknown>")
            summary["errors"].append(f"Failed to import environment {name!r}: {exc}")
            logger.exception("Failed to import environment %r", name)

    logger.info(
        "Import complete: %d collections, %d requests, %d responses, %d environments, %d errors",
        summary["collections_imported"],
        summary["requests_imported"],
        summary["responses_imported"],
        summary["environments_imported"],
        len(summary["errors"]),
    )
    return summary
