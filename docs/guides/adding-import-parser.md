# Adding an Import Parser

How to add support for a new collection format (e.g. Insomnia, HAR,
OpenAPI) to the import pipeline.

## Architecture

```
ImportDialog (UI)
  -> ImportService.import_files / import_text / import_folder
    -> Parser module (postman / curl / url / YOUR PARSER)
      -> Returns ImportResult (ParsedCollection + ParsedEnvironment)
    -> import_repository.import_collection_tree() (DB persist)
  -> ImportSummary dict returned to UI
```

## Steps

### 1. Create the parser file

Create `src/services/import_parser/your_parser.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Any

from services.import_parser.models import (
    ImportResult,
    ParsedCollection,
    ParsedFolder,
    ParsedRequest,
)

logger = logging.getLogger(__name__)


def detect_your_format(data: dict[str, Any]) -> bool:
    """Return True if data matches your format."""
    return "your_marker_key" in data


def parse_your_format(data: dict[str, Any]) -> ImportResult:
    """Parse YourFormat JSON into the internal import schema."""
    collections: list[ParsedCollection] = []

    # 1. Extract top-level collection metadata
    # 2. Recursively convert folders/requests
    # 3. Map fields to ParsedFolder / ParsedRequest
    # 4. Return ImportResult

    return ImportResult(
        collections=collections,
        environments=[],
        errors=[],
    )
```

### 2. Register in ImportService

Edit `src/services/import_service.py` to detect and dispatch:

```python
from services.import_parser.your_parser import (
    detect_your_format,
    parse_your_format,
)

# In the detection logic within import_text or import_files:
if detect_your_format(data):
    result = parse_your_format(data)
```

### 3. Write tests

Create `tests/unit/services/test_your_parser.py`:

```python
from __future__ import annotations

from services.import_parser.your_parser import (
    detect_your_format,
    parse_your_format,
)


class TestYourParser:
    """Tests for YourFormat parser."""

    def test_detect_valid_format(self) -> None:
        data = {"your_marker_key": "v1", ...}
        assert detect_your_format(data)

    def test_detect_invalid_format(self) -> None:
        data = {"info": {"schema": "postman"}}
        assert not detect_your_format(data)

    def test_parse_basic_collection(self) -> None:
        data = {... your format ...}
        result = parse_your_format(data)
        assert len(result["collections"]) == 1
        assert result["collections"][0]["name"] == "Expected"
        assert result["errors"] == []
```

### 4. Update instructions

After adding the parser:

1. Add the file to the architecture tree in `copilot-instructions.md`
2. Add the test file to the test tree
3. Update `service-repository-reference` skill with the new parser
4. Update this docs page (or `import-parsers.md`)

## Required TypedDicts

All parsers must return data conforming to these schemas.  See
[TypedDict Catalogue](../api-reference/typedicts.md) for full field
definitions.

| TypedDict | Purpose |
|-----------|---------|
| `ImportResult` | Top-level return value with collections + environments |
| `ParsedCollection` | Collection with name and root items |
| `ParsedFolder` | Folder node with name and children |
| `ParsedRequest` | Single HTTP request with method, URL, body |
| `ParsedEnvironment` | Environment with name and variable list |
| `ParsedSavedResponse` | Saved response example |

## Existing parsers

| Parser | File | Detection |
|--------|------|-----------|
| Postman | `postman_parser.py` | `info.schema` contains "collection" |
| cURL | `curl_parser.py` | Text starts with `curl ` |
| URL | `url_parser.py` | Auto-detect URL or raw text |
