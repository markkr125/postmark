"""Import parser package — detects and parses Postman, cURL, and URL data.

Usage::

    from services.import_parser import parse_collection_file, parse_curl, parse_raw_text
"""

from __future__ import annotations

from .curl_parser import is_curl, parse_curl
from .models import (
    ImportResult,
    ImportSummary,
    ParsedCollection,
    ParsedEnvironment,
    ParsedFolder,
    ParsedRequest,
    ParsedSavedResponse,
)
from .postman_parser import (
    detect_postman_type,
    parse_archive_folder,
    parse_collection_file,
    parse_environment_file,
    parse_json_text,
)
from .url_parser import fetch_and_parse_url, parse_raw_text

__all__ = [
    "ImportResult",
    "ImportSummary",
    "ParsedCollection",
    "ParsedEnvironment",
    "ParsedFolder",
    "ParsedRequest",
    "ParsedSavedResponse",
    "detect_postman_type",
    "fetch_and_parse_url",
    "is_curl",
    "parse_archive_folder",
    "parse_collection_file",
    "parse_curl",
    "parse_environment_file",
    "parse_json_text",
    "parse_raw_text",
]
