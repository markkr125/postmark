# Overview

A native desktop API client for testing and managing HTTP
requests.  Built with PySide6 and SQLAlchemy, it runs as a standalone
desktop application with a local SQLite database — no cloud account or
external service required.

## Features

- **Collections and folders** — organise requests into nested collections
  with drag-and-drop reordering and in-place rename.
- **Tabbed request editing** — open multiple requests in tabs with
  preview-mode, session persistence, and wrapped multi-row tab deck.
- **HTTP methods** — GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, and
  custom methods.
- **Request body modes** — raw (JSON, XML, text, HTML, JavaScript),
  form-data, x-www-form-urlencoded, binary, GraphQL.
- **Authentication** — 12 built-in auth types: Bearer, Basic, API Key,
  Digest, OAuth 1.0, OAuth 2.0 (4 grant types), Hawk, AWS Signature v4,
  JWT, ASAP, NTLM, Akamai EdgeGrid.  Auth inheritance from parent
  folders.
- **Environment variables** — named variable sets with `{{variable}}`
  substitution in URLs, headers, and bodies.  Collection-level variables
  with inheritance chain.  Per-request local overrides.
- **GraphQL support** — dedicated GraphQL body mode with schema
  introspection, type browser, and syntax highlighting.
- **Response viewer** — syntax-highlighted body with search, JSONPath
  and XPath queries, response beautification.  Status, timing, size, and
  network metadata popups.
- **Saved responses** — save HTTP responses as named examples attached to
  requests.
- **Code snippets** — generate request code in 23 languages (cURL, Python,
  JavaScript, Go, Rust, Java, etc.).
- **Import** — import from Postman collections/environments, cURL commands,
  and raw URLs.
- **Collection runner** — execute all requests in a collection sequentially.
- **Console and history panels** — log panel for HTTP traffic, history of
  sent requests.
- **Theming** — dark and light themes with Fusion and native Qt styles.
- **Code editor** — syntax highlighting, code folding, line numbers,
  bracket matching, search and replace.
- **SQLite persistence** — all data stored locally with WAL journal mode
  for concurrent reads.

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.12+ |
| UI framework | PySide6 (Qt 6) | 6.10+ |
| ORM | SQLAlchemy | 2.0+ |
| HTTP client | httpx | 0.28+ |
| Syntax highlighting | Pygments | 2.19+ |
| JSONPath | jsonpath-ng | 1.8+ |
| XML processing | lxml | 6.0+ |
| Package manager | Poetry | — |
| Linter/formatter | Ruff | 0.9+ |
| Type checker | mypy | 1.14+ |
| Test framework | pytest + pytest-qt | 8.0+ / 4.5+ |

## Source Layout

```text
src/
  database/    SQLAlchemy models, repositories, session management
  services/    Service layer — business logic, HTTP, import, auth
  ui/          PySide6 widgets — all visual components
```

See [Directory Structure](../architecture/directory-structure.md) for the
full annotated tree.
