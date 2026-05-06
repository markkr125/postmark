# ScriptService

Script chain resolution from database ancestry.

**Module:** `services/script_service.py`
**Re-exported from:** `services/__init__.py`

## Class: `ScriptService`

All methods are `@staticmethod`.

### `build_script_chain`

```python
@staticmethod
def build_script_chain(
    request_id: int,
) -> tuple[list[ScriptEntry], list[ScriptEntry]]
```

Build the complete script inheritance chain for a request.

Walks the collection/folder ancestry tree from root to request and
collects all scripts with their language metadata.

**Returns:** `(pre_request_chain, test_chain)` where each chain is a
list of `ScriptEntry` dicts ordered by execution priority.

- Pre-request chain: collection → folder(s) → request (top-down).
- Test chain: request → folder(s) → collection (bottom-up).

### `build_collection_script_chain`

```python
@staticmethod
def build_collection_script_chain(
    events: Any,
) -> tuple[list[ScriptEntry], list[ScriptEntry]]
```

Build script chains from raw events data (without database lookup).
Used for standalone collection/folder script execution.

## TypedDict: `ScriptEntry`

Defined in `services/scripting/__init__.py`:

```python
class ScriptEntry(TypedDict):
    code: str         # Script source code
    language: str     # "javascript", "typescript", or "python"
    source_name: str  # Display name of the source (collection/folder/request)
```
