# ImportService

Orchestrates the import pipeline: parse input → persist to database →
return summary.  All methods are `@staticmethod`.

Source: `src/services/import_service.py`

## Methods

### `import_files`

```python
@staticmethod
def import_files(paths: list[Path]) -> ImportSummary
```

Import one or more files.  Each file is detected as either a Postman
collection, Postman environment, or Postman data dump archive.  Calls
the appropriate parser and persists results.

### `import_folder`

```python
@staticmethod
def import_folder(path: Path) -> ImportSummary
```

Import a folder as a Postman data dump archive.

### `import_text`

```python
@staticmethod
def import_text(text: str) -> ImportSummary
```

Import from raw text.  Auto-detects whether the text is JSON (Postman
collection/environment) or another format, and routes to the
appropriate parser.

### `import_curl`

```python
@staticmethod
def import_curl(text: str) -> ImportSummary
```

Import from a cURL command string.

### `import_url`

```python
@staticmethod
def import_url(url: str) -> ImportSummary
```

Fetch a URL and import the response.  Creates a single request in a
new collection.

## Pipeline

```text
import_files(paths)
  For each path:
    1. Read file contents
    2. detect_postman_type(data) --> "collection" | "environment" | "archive" | "unknown"
    3. Route to parser:
       - "collection" --> parse_collection_file(path)
       - "environment" --> parse_environment_file(path)
       - "archive" --> parse_archive_folder(path)
    4. Parser returns ImportResult:
       - collections: list[ParsedCollection]
       - environments: list[ParsedEnvironment]
       - errors: list[str]
    5. For each ParsedCollection:
       --> import_collection_tree(parsed) --> creates DB records
    6. For each ParsedEnvironment:
       --> create_environment(name, values)
    7. Accumulate counts into ImportSummary

Returns ImportSummary:
  collections_imported: int
  requests_imported: int
  responses_imported: int
  environments_imported: int
  errors: list[str]
```

## TypedDicts

See [TypedDict Catalogue](../typedicts.md) for `ImportResult` and
`ImportSummary` field definitions.

See [Import Parsers](import-parsers.md) for parser-level TypedDicts
(`ParsedCollection`, `ParsedRequest`, etc.).
