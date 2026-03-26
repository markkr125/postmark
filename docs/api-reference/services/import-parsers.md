# Import Parsers

Three parser modules convert external formats into the internal
`ImportResult` structure.

Source: `src/services/import_parser/`

## Postman Parser

**Module:** `postman_parser.py`

Parses Postman Collection v2.1, Postman Environment, and Postman Data
Dump Archive formats.

### `detect_postman_type`

```python
def detect_postman_type(
    data: dict[str, Any],
) -> Literal["collection", "environment", "archive", "unknown"]
```

Detect the type of a parsed JSON object.

### `parse_collection_file`

```python
def parse_collection_file(path: Path) -> ImportResult
```

Parse a Postman Collection v2.1 JSON file.  Recursively converts
folders (`item` arrays) and requests into `ParsedFolder` and
`ParsedRequest` dicts.  Preserves auth, headers, body, scripts,
variables, and saved responses (`response` arrays).

### `parse_environment_file`

```python
def parse_environment_file(path: Path) -> ImportResult
```

Parse a Postman Environment JSON file.  Extracts variable key-value
pairs.

### `parse_archive_folder`

```python
def parse_archive_folder(path: Path) -> ImportResult
```

Parse a Postman Data Dump archive folder.  Expects `collection/` and
`environment/` subdirectories containing individual JSON files.

### `parse_json_text`

```python
def parse_json_text(text: str) -> ImportResult
```

Parse a JSON string as either a collection or environment.

## cURL Parser

**Module:** `curl_parser.py`

Parses cURL command strings into single-request collections.

### `is_curl`

```python
def is_curl(text: str) -> bool
```

Check if a text string looks like a cURL command.

### `parse_curl`

```python
def parse_curl(text: str) -> ImportResult
```

Parse a cURL command into an `ImportResult` with a single collection
containing one request.  Extracts method, URL, headers, and body from
curl flags (`-X`, `-H`, `-d`, `--data`, etc.).

## URL Parser

**Module:** `url_parser.py`

Parses raw URLs and plain text into requests.

### `parse_raw_text`

```python
def parse_raw_text(text: str) -> ImportResult
```

Auto-detect whether text is JSON (delegate to Postman parser), a cURL
command (delegate to cURL parser), or a raw URL/text.

### `fetch_and_parse_url`

```python
def fetch_and_parse_url(url: str) -> ImportResult
```

Fetch a URL and create a single-request collection from the result.

## Parser TypedDicts

All parsers output `ImportResult` containing `ParsedCollection` and
`ParsedEnvironment` dicts.  See [TypedDict Catalogue](../typedicts.md)
for complete field definitions of:

- `ParsedSavedResponse`
- `ParsedRequest`
- `ParsedFolder`
- `ParsedCollection`
- `ParsedEnvironment`
- `ImportResult`
- `ImportSummary`
