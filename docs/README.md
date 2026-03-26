# Documentation

> **Audience:** Human developers and AI agents.
>
> **Navigation tip for AI agents:** Start with
> [Architecture Overview](architecture/overview.md) for the layered design,
> then jump to [API Reference](api-reference/) for function signatures.
> The [TypedDict Catalogue](api-reference/typedicts.md) and
> [Signal Reference](api-reference/signals.md) are the two most commonly
> needed lookup pages.

## Table of Contents

### Getting Started

| Page | Description |
|------|-------------|
| [Overview](getting-started/overview.md) | Application description, feature list, technology stack |
| [Installation](getting-started/installation.md) | Prerequisites, Poetry setup, dev dependencies |
| [Running](getting-started/running.md) | Launch the app, dev commands, VS Code task |

### Architecture

| Page | Description |
|------|-------------|
| [Architecture Overview](architecture/overview.md) | 3-layer stack, dependency flow, communication patterns |
| [Directory Structure](architecture/directory-structure.md) | Full annotated `src/` and `tests/` tree |
| [Data Flow](architecture/data-flow.md) | Sequence diagrams for key operations |
| [Database Layer](architecture/database-layer.md) | SQLite engine, sessions, migration, model relationships |
| [Service Layer](architecture/service-layer.md) | Static method pattern, TypedDict interchange |
| [UI Layer](architecture/ui-layer.md) | MainWindow mixin stack, widget hierarchy, theming |

### API Reference — Database

| Page | Description |
|------|-------------|
| [ORM Models](api-reference/database/models.md) | All 4 models — fields, relationships, JSON columns |
| [Collection Repository](api-reference/database/collection-repository.md) | 14 CRUD functions for collections and requests |
| [Query Repository](api-reference/database/query-repository.md) | 12 read-only tree/breadcrumb/ancestor queries |
| [Import Repository](api-reference/database/import-repository.md) | Atomic bulk-import of parsed data |
| [Environment Repository](api-reference/database/environment-repository.md) | 6 CRUD functions for environments |

### API Reference — Services

| Page | Description |
|------|-------------|
| [CollectionService](api-reference/services/collection-service.md) | Collection/request CRUD, auth chains, breadcrumbs, saved responses |
| [EnvironmentService](api-reference/services/environment-service.md) | Variable maps, substitution, CRUD |
| [HttpService](api-reference/services/http-service.md) | HTTP request execution, timing/network/size capture |
| [ImportService](api-reference/services/import-service.md) | File/folder/text/URL import orchestration |
| [GraphQLSchemaService](api-reference/services/graphql-service.md) | GraphQL introspection and schema parsing |
| [SnippetGenerator](api-reference/services/snippet-generator.md) | Code snippet generation for 23 language targets |
| [Auth Handler](api-reference/services/auth-handler.md) | `apply_auth()` — 12 authentication types |
| [OAuth2Service](api-reference/services/oauth2-service.md) | OAuth 2.0 token exchange — 4 grant types |
| [Import Parsers](api-reference/services/import-parsers.md) | Postman, cURL, and URL parser modules |

### API Reference — Cross-Cutting

| Page | Description |
|------|-------------|
| [TypedDict Catalogue](api-reference/typedicts.md) | All TypedDict schemas grouped by module |
| [Signal Reference](api-reference/signals.md) | All signal declarations grouped by subsystem |

### UI Reference

| Page | Description |
|------|-------------|
| [MainWindow](ui-reference/main-window.md) | MainWindow class + 4 controller mixins |
| [Collections](ui-reference/collections.md) | Collection sidebar — tree, delegate, header, new-item popup |
| [Request Editor](ui-reference/request-editor.md) | Request editing — auth, body search, GraphQL mode |
| [Response Viewer](ui-reference/response-viewer.md) | Response display — search, filter, JSONPath/XPath |
| [Navigation](ui-reference/navigation.md) | Tab manager, breadcrumb bar, wrapped tab deck |
| [Sidebar](ui-reference/sidebar.md) | Right sidebar — variables, snippets, saved responses |
| [Dialogs](ui-reference/dialogs.md) | Import, Save, Settings, Collection Runner |
| [Panels](ui-reference/panels.md) | Console and History panels |
| [Shared Widgets](ui-reference/widgets.md) | Code editor, key-value table, popups, variable widgets |
| [Styling](ui-reference/styling.md) | Theme manager, palettes, global QSS, icon system |

### Guides

| Page | Description |
|------|-------------|
| [Adding an Import Parser](guides/adding-import-parser.md) | Step-by-step guide for new format parsers |
| [Adding an Auth Type](guides/adding-auth-type.md) | New auth type: field specs, handler, UI page |
| [Adding a Widget](guides/adding-widget.md) | New widget checklist and patterns |
| [Writing Tests](guides/writing-tests.md) | Test patterns for each layer |
| [Wiring Signals](guides/wiring-signals.md) | Signal declaration and MainWindow wiring |

### Contributing

| Page | Description |
|------|-------------|
| [Coding Conventions](contributing/coding-conventions.md) | Ruff, mypy, naming rules, file/directory limits |
| [Testing Guide](contributing/testing-guide.md) | Full test workflow, layer boundaries, fixtures |
| [Updating Documentation](contributing/updating-docs.md) | When and how to update these docs |
