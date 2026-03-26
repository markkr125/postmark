# Wiring Signals

How to add new signal connections to the UI.

## Signal Flow Pattern

```
Child Widget emits signal
  -> MainWindow connects signal in __init__
    -> MainWindow handler calls Service method
      -> Service calls Repository function
        -> Repository writes to database
      -> MainWindow updates other widgets
```

Widgets **emit** signals but never **connect** to each other directly.
All wiring happens in MainWindow.

## Adding a New Signal

### 1. Declare the signal

In the source widget class, add a class-level `Signal`:

```python
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    my_action = Signal(int, str)  # item_id, action_name
```

Use `object` for union types like `int | None`:

```python
item_selected = Signal(object)  # int | None
```

### 2. Emit the signal

In the widget method that triggers the action:

```python
def _on_button_clicked(self) -> None:
    self.my_action.emit(self._item_id, "clicked")
```

### 3. Connect in MainWindow

In `MainWindow.__init__` (or in the appropriate mixin), connect the
signal to a handler:

```python
self._my_widget.my_action.connect(self._on_my_action)
```

### 4. Write the handler

```python
def _on_my_action(self, item_id: int, action: str) -> None:
    # Call service layer
    CollectionService.do_something(item_id, action)
    # Update other widgets
    self._refresh_sidebar()
```

## Signal Forwarding

Composite widgets re-emit child signals so MainWindow only connects
to top-level widgets:

```python
class CollectionWidget(QWidget):
    item_action_triggered = Signal(str, int, str)

    def __init__(self) -> None:
        super().__init__()
        self._tree = CollectionTree()
        # Forward child signal
        self._tree.item_action_triggered.connect(
            self.item_action_triggered.emit
        )
```

## Debounced Signals

For high-frequency changes, use a `QTimer` to debounce:

```python
from PySide6.QtCore import QTimer

class RequestEditorWidget(QWidget):
    request_changed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._change_timer = QTimer()
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(500)  # 500ms debounce
        self._change_timer.timeout.connect(self._emit_change)

    def _on_field_edited(self) -> None:
        self._change_timer.start()  # restart timer

    def _emit_change(self) -> None:
        self.request_changed.emit(self.get_request_data())
```

## Worker Thread Signals

Background workers use a consistent `finished`/`error` pair:

```python
class _MyWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def run(self) -> None:
        try:
            result = do_work()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
```

Connect before starting the thread:

```python
worker.finished.connect(self._on_finished)
worker.error.connect(self._on_error)
worker.finished.connect(thread.quit)
worker.error.connect(thread.quit)
thread.started.connect(worker.run)
thread.start()
```

## Common Patterns

| Pattern | Example |
|---------|---------|
| Action trigger | `item_action_triggered(type, id, action)` |
| State change | `dirty_changed(bool)` |
| Data update | `request_changed(dict)` |
| Selection change | `environment_changed(object)` |
| Request lifecycle | `finished(dict)` / `error(str)` |

## Checklist

1. Declare `Signal(...)` with exact parameter types
2. Emit from the widget that owns the action
3. Connect in MainWindow (not in child widgets)
4. Forward through composite widgets if needed
5. Debounce high-frequency signals with `QTimer`
6. Update the [Signals Reference](../api-reference/signals.md)
7. Update the `signal-flow` skill if wiring changes
