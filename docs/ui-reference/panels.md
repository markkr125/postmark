# Panels

Collapsible bottom panels for console output and request history.

Source: `src/ui/panels/`

## ConsolePanel

Application log viewer.

### UI

Title bar with "Console" label and a Clear button.  Read-only
`QTextEdit` displaying formatted log lines.

### Log Format

```
HH:MM:SS LEVEL module — message
```

A `_QtLogHandler` is attached to the Python root logger.  Log messages
pass through a `_LogSignalBridge` that emits `log_message(str)` so
the UI update happens on the main thread.

### Limits

Maximum 2000 lines in memory (oldest lines removed first).

## HistoryPanel

Recent HTTP request history.

### UI

Title bar with "History" label and a Clear button.  Scrollable list
of `_HistoryEntry` items.

### Entry Format

```
+------+-----------------------------+-----+--------+
| POST | https://api.example.com/v1  | 200 | 245 ms |
+------+-----------------------------+-----+--------+
```

Each entry shows method (coloured badge), URL, status code, and
elapsed time.

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `entry_clicked` | `str, str` | Entry clicked (method, url) |

### Limits

Maximum 50 entries.
