# Panels

Collapsible bottom panel for console output.

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
