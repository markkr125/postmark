# Adding a Widget

How to create a new PySide6 widget for the application UI.

## Checklist

1. Create the widget class with `from __future__ import annotations`
2. Add a module-level docstring
3. Set `objectName` if the widget needs global QSS styling
4. Use `theme.py` for all colours — never inline hex values
5. Use `phi()` for icons
6. Emit typed signals for cross-widget communication
7. Wire signals in MainWindow (not in child widgets)
8. Write tests with `pytest-qt`
9. Update instruction files

## Widget Template

```python
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.styling.icons import phi
from ui.styling.theme import current_palette


class MyWidget(QWidget):
    """One-line description of the widget."""

    something_happened = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("myWidget")
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # ... add child widgets
```

## Layout Patterns

### Enum Scoping

Always use fully qualified enums:

```python
# Correct
layout.setAlignment(Qt.AlignmentFlag.AlignTop)
widget.setSizePolicy(
    QSizePolicy.Policy.Expanding,
    QSizePolicy.Policy.Fixed,
)

# Wrong — unscoped enum
layout.setAlignment(Qt.AlignTop)
```

### Layout Casts

PySide6 `layout()` returns `QLayout | None`.  Cast when needed:

```python
from PySide6.QtWidgets import QVBoxLayout

layout = self.layout()
assert isinstance(layout, QVBoxLayout)
layout.addWidget(child)
```

## Colour and Icon Usage

All hex colour values belong in `src/ui/styling/theme.py`:

```python
# In theme.py — add to ThemePalette if needed
"my_widget_accent": "#4a90d9",

# In your widget — reference the palette
palette = current_palette()
label.setStyleSheet(f"color: {palette['accent']}")
```

Icons use the Phosphor font via `phi()`:

```python
from ui.styling.icons import phi

button.setIcon(phi("plus"))
action.setIcon(phi("trash", color="#e74c3c", size=16))
```

## Signal Patterns

Declare signals as class attributes with typed parameters:

```python
class MyWidget(QWidget):
    # Use object for union types (int | None)
    item_selected = Signal(object)
    data_changed = Signal(dict)
```

Wire signals in MainWindow, not in child widgets.  The widget emits,
MainWindow connects and routes.

## Background Workers

For long-running operations, use `QThread` + `QObject` worker:

```python
class _MyWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def run(self) -> None:
        try:
            result = expensive_operation()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
```

Create the thread, move the worker, connect signals, start:

```python
thread = QThread()
worker = _MyWorker()
worker.moveToThread(thread)
thread.started.connect(worker.run)
worker.finished.connect(self._on_finished)
worker.finished.connect(thread.quit)
thread.start()
```

## File Limits

- **5 files per directory** (excluding `__init__.py`).  When a
  directory reaches this limit, group related files into a sub-package.
- **600 lines per file**.  Extract cohesive groups into sub-modules.

## Testing

See [Writing Tests](writing-tests.md) for widget test patterns using
`pytest-qt`.
