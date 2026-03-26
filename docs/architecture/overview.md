# Architecture Overview

The application follows a strict **three-layer architecture**.  Every layer may
only call the layer directly below it — skipping layers is not allowed.

```text
+-------------------------------------------------------------+
|                        UI Layer                              |
|  PySide6 widgets, signals, MainWindow, dialogs, panels       |
|  src/ui/                                                     |
+------------------------------+------------------------------+
                               | signals / method calls
                               v
+-------------------------------------------------------------+
|                     Service Layer                            |
|  Static-method classes, TypedDict interchange, business logic|
|  src/services/                                               |
+------------------------------+------------------------------+
                               | function calls
                               v
+-------------------------------------------------------------+
|                   Repository Layer                           |
|  SQLAlchemy ORM, session management, raw queries             |
|  src/database/                                               |
+------------------------------+------------------------------+
                               |
                               v
                        [ SQLite DB ]
                     data/database/main.db
```

## Layer Rules

1. **UI never imports from `database/`** — all data access goes through
   services.
2. **Services never import from `ui/`** — services are pure logic with
   no Qt dependency.
3. **Repository functions use `get_session()`** — never create sessions
   manually.
4. **Cross-layer data uses TypedDicts** — not ORM instances.  Models are
   detached from the session before they leave repository functions.

## Communication Patterns

### UI to Service

Widgets call service static methods directly:

```text
RequestEditor
  --> CollectionService.update_request(request_id, body=new_body)
```

### Service to Repository

Services call repository functions, which manage their own sessions:

```text
CollectionService.update_request(request_id, **fields)
  --> update_request(request_id, **fields)
    --> get_session() context manager
      --> session.get(RequestModel, request_id)
      --> setattr(...) for each field
      --> auto-commit on exit
```

### UI to UI (Signals)

Widgets communicate through Qt signals for decoupled event propagation:

```text
CollectionTree emits item_action_triggered("request", 42, "My API")
  --> MainWindow receives signal
    --> _TabControllerMixin._on_item_action("request", 42, "My API")
      --> opens/focuses the request tab
```

### Background Work (QThread)

Long-running operations use QThread workers to keep the UI responsive:

```text
MainWindow._on_send()
  --> creates HttpSendWorker
  --> moves worker to QThread
  --> thread.started connects to worker.run
  --> worker.finished signal carries HttpResponseDict
  --> MainWindow._on_response_received(dict)
    --> ResponseViewer.display_response(dict)
```

## Key Design Decisions

- **Static-method services** — no instance state, all methods are
  `@staticmethod`.  The class exists only for namespace grouping.
- **TypedDict interchange** — typed dicts cross module boundaries instead
  of ORM model instances.  This keeps layers decoupled and ensures type
  safety.
- **Signal-driven UI** — widgets emit signals; `MainWindow.__init__`
  wires them together.  Widgets never reference each other directly.
- **Session-per-function** — each repository function creates and closes
  its own session via `get_session()`.  No long-lived sessions.
- **Detached ORM objects** — `expire_on_commit=False` allows returned
  model instances to be read after the session closes.

## Entry Point

`src/main.py` initialises the application:

```text
main.py
  1. QApplication()
  2. init_db()          -- creates engine, runs DDL, prepares session factory
  3. MainWindow()       -- builds the entire widget tree
  4. window.show()
  5. app.exec()
```

## Further Reading

- [Directory Structure](directory-structure.md) — full annotated source tree
- [Data Flow](data-flow.md) — sequence diagrams for key operations
- [Database Layer](database-layer.md) — engine, sessions, migration
- [Service Layer](service-layer.md) — static methods, TypedDict patterns
- [UI Layer](ui-layer.md) — widget hierarchy, mixin stack, theming
