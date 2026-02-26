"""Data classes for the import parser intermediate representation.

These ``TypedDict`` classes define the schema that flows from parsers
into the import service and repository layers.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ParsedSavedResponse(TypedDict, total=False):
    """A single saved response (Postman example)."""

    name: str
    status: str | None
    code: int | None
    headers: list[dict[str, Any]] | None
    body: str | None
    preview_language: str | None
    original_request: dict[str, Any] | None


class ParsedRequest(TypedDict, total=False):
    """A single HTTP request extracted from an import source."""

    type: str  # "request"
    name: str
    method: str
    url: str
    headers: list[dict[str, Any]] | None
    request_parameters: list[dict[str, Any]] | None
    body: str | None
    body_mode: str | None
    body_options: dict[str, Any] | None
    auth: dict[str, Any] | None
    description: str | None
    events: list[dict[str, Any]] | None
    scripts: dict[str, Any] | None
    settings: dict[str, Any] | None
    protocol_profile_behavior: dict[str, Any] | None
    saved_responses: list[ParsedSavedResponse]


class ParsedFolder(TypedDict, total=False):
    """A folder node in the collection tree."""

    type: str  # "folder"
    name: str
    description: str | None
    auth: dict[str, Any] | None
    events: list[dict[str, Any]] | None
    variables: list[dict[str, Any]] | None
    children: list[ParsedFolder | ParsedRequest]


class ParsedCollection(TypedDict, total=False):
    """A complete parsed collection ready for DB import."""

    name: str
    description: str | None
    events: list[dict[str, Any]] | None
    variables: list[dict[str, Any]] | None
    auth: dict[str, Any] | None
    items: list[ParsedFolder | ParsedRequest]


class ParsedEnvironment(TypedDict, total=False):
    """A parsed environment with its variable list."""

    name: str
    values: list[dict[str, Any]]


class ImportResult(TypedDict, total=False):
    """Aggregate result returned by any parser entry point."""

    collections: list[ParsedCollection]
    environments: list[ParsedEnvironment]
    errors: list[str]


class ImportSummary(TypedDict):
    """Summary of what was actually persisted to the database."""

    collections_imported: int
    requests_imported: int
    responses_imported: int
    environments_imported: int
    errors: list[str]
