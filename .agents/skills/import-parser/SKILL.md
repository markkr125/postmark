---
name: import-parser
description: Guide for adding new import format parsers to the Postmark import pipeline. Use when adding support for new collection formats (e.g. Insomnia, HAR, OpenAPI) or new import sources.
---

# Adding a new import parser

Step-by-step guide for adding support for a new import format to the
Postmark import pipeline.

## Architecture overview

```
Import flow:
  UI (ImportDialog) / Agent postmark_import
    → ImportService.import_files / import_text / import_url / import_folder
      → Parser (postman / curl / url / openapi/ / wsdl/)
        → Returns ParsedCollection / ParsedEnvironment
      → import_repository.import_collection_tree() (DB persist)
    → ImportSummary dict returned to UI / observation
```

Built-in formats: Postman Collection/Environment JSON, cURL, raw URL,
**OpenAPI 3 / Swagger 2** (JSON or YAML), **WSDL 1.1** (SOAP 1.1 POSTs).
Detection lives in ``url_parser.try_parse_spec_text`` (OpenAPI then WSDL)
and is shared by file load, paste, and URL fetch. Agent import is the dedicated
OpenHands tool ``postmark_import`` (Action: ``url`` | ``path`` | ``text`` | ``curl``),
not a mutate entity. OpenAPI request/response ``examples`` are mapped to saved
responses by ``openapi/examples.py`` (first request example → body; named
response examples → saved responses with a request snapshot; extra request
examples → ``… — request`` variants).

**PDF/DOCX messy docs** are not a new `ImportResult` parser: in Agent mode the
assistant calls read-only `postmark_document_import` to extract text and
screenshots, then synthesizes Postman JSON and calls `postmark_import` once.

## TypedDict schemas (`services/import_parser/models.py`)

All parsers must return data conforming to these TypedDicts:

```python
class ParsedSavedResponse(TypedDict):
    name: str
    status: str | None
    code: int | None
    headers: list[dict[str, Any]] | None
    body: str | None
    preview_language: str | None
    original_request: dict[str, Any] | None  # Postman-shaped request snapshot

class ParsedRequest(TypedDict, total=False):
    type: str          # "request" — always set
    name: str
    method: str
    url: str
    headers: list[dict[str, Any]] | None
    request_parameters: list[dict[str, Any]] | None
    body: str | None
    body_mode: str | None
    body_options: dict[str, Any] | None
    description: str | None
    saved_responses: list[ParsedSavedResponse]
    # + auth/events/scripts/settings/protocol_profile_behavior

class ParsedFolder(TypedDict):
    type: str          # "folder"
    name: str
    description: str | None
    auth: dict[str, Any] | None
    events: list[dict[str, Any]] | None
    children: list[ParsedFolder | ParsedRequest]
    variables: NotRequired[list[dict[str, Any]] | None]

class ParsedCollection(TypedDict):
    name: str
    items: list[ParsedFolder | ParsedRequest]
    description: NotRequired[str | None]
    events: NotRequired[list[dict[str, Any]] | dict[str, Any] | None]
    variables: NotRequired[list[dict[str, Any]] | None]
    auth: NotRequired[dict[str, Any] | None]

class ParsedEnvironment(TypedDict):
    name: str
    values: list[dict[str, Any]]

class ImportResult(TypedDict):
    collections: list[ParsedCollection]
    environments: list[ParsedEnvironment]
    errors: list[str]

class ImportSummary(TypedDict):
    collections_imported: int
    requests_imported: int
    responses_imported: int
    environments_imported: int
    scripts_detected: int
    errors: list[str]
    imported_collections: list[ImportedCollectionRef]  # {id, name}
```

## Step-by-step: Add a new parser

### 1. Create the parser file

Create `src/services/import_parser/your_parser.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Any

from services.import_parser.models import ImportResult, ParsedCollection

logger = logging.getLogger(__name__)


def parse_your_format(data: dict[str, Any]) -> ImportResult:
    """Parse YourFormat JSON into Postmark's import schema."""
    collections: list[ParsedCollection] = []

    # 1. Extract collections/folders/requests
    # 2. Map to ParsedCollection / ParsedFolder structures
    # 3. Return ImportResult

    return ImportResult(collections=collections, environments=[])
```

### 2. Register in ImportService

Edit `src/services/import_service.py` to detect and dispatch to your parser.
The detection usually happens in `import_files` or `import_text`:

```python
from services.import_parser.your_parser import parse_your_format

# In the detection logic:
if _is_your_format(data):
    result = parse_your_format(data)
```

### 3. Add tests

Create `tests/unit/services/test_your_parser.py` (or add to
`test_import_parser.py`):

```python
from __future__ import annotations

from services.import_parser.your_parser import parse_your_format


class TestYourParser:
    def test_parse_basic_collection(self) -> None:
        data = {... your format ...}
        result = parse_your_format(data)
        assert len(result["collections"]) == 1
        assert result["collections"][0]["name"] == "Expected"
```

### 4. Update instruction files

After adding a new parser:

1. Add the file to the architecture tree in root [`AGENTS.md`](../../../AGENTS.md).
2. Add the test file to the test tree in [`tests/AGENTS.md`](../../../tests/AGENTS.md).
3. Add the parser to the ImportService section in the
   `service-repository-reference` skill.

## Existing parsers

| Parser | File | Detects |
|--------|------|---------|
| Postman | `postman_parser.py` | `info.schema` contains `collection` |
| cURL | `curl_parser.py` | Text starts with `curl ` |
| URL | `url_parser.py` | Auto-detect URL or raw text |
