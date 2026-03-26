# Import Repository

Atomic bulk-import of parsed collection trees into the database.

Source: `src/database/models/collections/import_repository.py`

## `import_collection_tree`

```python
def import_collection_tree(parsed: dict[str, Any]) -> dict[str, int]
```

Persist a parsed collection tree (from any import parser) into the
database.  All inserts happen in a single transaction — if any step
fails, the entire import is rolled back.

**Parameters:**
- `parsed` — a `ParsedCollection` dict containing the collection name,
  items (folders and requests), and optional metadata.

**Returns:** A dict mapping item identifiers to their new database IDs.

**Process:**
1. Create root `CollectionModel` from the parsed collection name.
2. Recursively walk `items`:
   - For `ParsedFolder` entries: create child `CollectionModel`, set
     `parent_id`, then recurse into `children`.
   - For `ParsedRequest` entries: create `RequestModel` with all fields
     (method, URL, body, headers, auth, scripts, etc.).
   - For `ParsedSavedResponse` entries on requests: create
     `SavedResponseModel` linked to the request.
3. Commit the entire tree in one transaction.

**See also:** [Import Parsers](../services/import-parsers.md) for the
TypedDict schemas of parsed data.
