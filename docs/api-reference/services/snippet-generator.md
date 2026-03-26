# SnippetGenerator

Generate code snippets for HTTP requests in 23 language targets.

Source: `src/services/http/snippet_generator/`

## SnippetGenerator Class

All methods are `@staticmethod`.

### `available_languages`

```python
@staticmethod
def available_languages() -> list[str]
```

Return a list of all registered language names.

### `get_language_info`

```python
@staticmethod
def get_language_info(name: str) -> LanguageEntry | None
```

Look up a language by name.  Returns `None` if not found.

### `generate`

```python
@staticmethod
def generate(
    language: str,
    *,
    method: str,
    url: str,
    headers: str | None = None,
    body: str | None = None,
    auth: dict | None = None,
    options: SnippetOptions | None = None,
) -> str
```

Generate a code snippet for the given language and request.

**Parameters:**
- `language` — language name from the registry (case-sensitive).
- `method` — HTTP method (GET, POST, etc.).
- `url` — request URL.
- `headers` — raw header string.
- `body` — request body.
- `auth` — auth dict (applied via `apply_auth()` before generation).
- `options` — formatting and style options.

## Helper Functions

```python
def resolve_options(options: SnippetOptions | None) -> SnippetOptions
def indent_str(options: SnippetOptions) -> str
def prepare_body(body: str | None, options: SnippetOptions) -> str | None
```

## Language Registry

23 language targets across three modules:

### Shell Languages (`shell_snippets.py`)

| Name | Lexer | Description |
|------|-------|-------------|
| cURL | bash | cURL command line |
| HTTP | http | Raw HTTP request format |
| PowerShell (RestMethod) | powershell | Invoke-RestMethod |
| Shell (HTTPie) | bash | HTTPie command |
| Shell (wget) | bash | wget command |

### Dynamic Languages (`dynamic_snippets.py`)

| Name | Lexer | Description |
|------|-------|-------------|
| Python (requests) | python | requests library |
| Python (http.client) | python | stdlib http.client |
| JavaScript (fetch) | javascript | Fetch API |
| JavaScript (XMLHttpRequest) | javascript | XHR |
| Node.js (axios) | javascript | axios library |
| Node.js (native) | javascript | http/https modules |
| Ruby (net/http) | ruby | stdlib Net::HTTP |
| PHP (cURL) | php | php-curl extension |
| Dart (http) | dart | http package |

### Compiled Languages (`compiled_snippets.py`)

| Name | Lexer | Description |
|------|-------|-------------|
| Go (net/http) | go | stdlib net/http |
| Rust (reqwest) | rust | reqwest crate |
| C (libcurl) | c | libcurl |
| Swift (URLSession) | swift | Foundation URLSession |
| Java (OkHttp) | java | OkHttp library |
| Kotlin (OkHttp) | kotlin | OkHttp library |
| C# (HttpClient) | csharp | System.Net.Http |

## LanguageEntry

```python
class LanguageEntry(NamedTuple):
    display_name: str                    # Human-readable name
    lexer: str                           # Pygments lexer name
    applicable_options: tuple[str, ...]  # SnippetOptions keys used
    generate: Callable[..., str]         # Generator function
```

## SnippetOptions

See [TypedDict Catalogue](../typedicts.md#snippetoptions) for field
definitions.
