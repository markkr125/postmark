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
  UI (ImportDialog)
    → ImportService.import_files / import_text / import_folder
      → Parser (postman_parser / curl_parser / url_parser / YOUR_PARSER)
        → Returns ParsedCollection / ParsedEnvironment
      → import_repository.import_collection_tree() (DB persist)
    → ImportSummary dict returned to UI
```

## TypedDict schemas (`services/import_parser/models.py`)

All parsers must return data conforming to these TypedDicts:

```python
class ParsedSavedResponse(TypedDict):
    name: str
    status: str | None
    code: int | None
    headers: Any
    body: str | None

class ParsedFolder(TypedDict):
    name: str
    variables: NotRequired[dict[str, str]]
    auth: NotRequired[dict[str, Any]]
    scripts: NotRequired[dict[str, str]]
    items: list[ParsedFolder | ParsedRequest]

class ParsedCollection(TypedDict):
    name: str
    variables: NotRequired[dict[str, str]]
    auth: NotRequired[dict[str, Any]]
    scripts: NotRequired[dict[str, str]]
    items: list[ParsedFolder | ParsedRequest]

class ParsedEnvironment(TypedDict):
    name: str
    values: dict[str, str]

class ImportResult(TypedDict):
    collections: list[ParsedCollection]
    environments: list[ParsedEnvironment]

class ImportSummary(TypedDict):
    collections: int
    requests: int
    environments: int
    errors: list[str]
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

1. Add the file to the architecture tree in `copilot-instructions.md`.
2. Add test file to the test tree in `testing.instructions.md`.
3. Add the parser to the ImportService section in the
   `service-repository-reference` skill.

## Existing parsers

| Parser | File | Detects |
|--------|------|---------|
| Postman | `postman_parser.py` | `info.schema` contains `collection` |
| cURL | `curl_parser.py` | Text starts with `curl ` |
| URL | `url_parser.py` | Auto-detect URL or raw text |
