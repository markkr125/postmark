# Debugging scripts

Step through pre-request or test scripts with breakpoints, watches, and a call stack — similar to an IDE debugger.

## Start a debug session

1. Open the **Scripts** tab.
2. In the pre-request or test editor, set breakpoints by clicking the gutter (or use the breakpoint toolbar).
3. Click **Debug** in the script toolbar (not **Send** for script-only debugging).
4. Or click **Send** while breakpoints are set — the send pipeline pauses when a breakpoint hits.

## While paused

| Control | Action |
|---------|--------|
| **Continue** | Run until the next breakpoint |
| **Step over** | Execute the current line |
| **Step into** | Enter a function call |
| **Step out** | Finish the current function |
| **Stop** | End the debug session |

The **Debugger** tab in the script output area shows:

- **Call stack** — switch frames to inspect locals at each level
- **Watches** — add expressions to re-evaluate on each pause
- **Scopes** — locals, `pm`, globals, and related bindings

Hover a variable in the editor during pause for an expandable value popup.

## Breakpoints dialog

1. Open the breakpoints manager from the script toolbar.
2. Review all breakpoints across the current script.
3. Enable, disable, or remove breakpoints; jump to the source line from the preview pane.

## Tips

- Pre-request scripts: `pm.response` is not available — do not read the response while debugging pre-request code.
- Nested callbacks (e.g. inside `pm.test`) support breakpoints when the runtime maps them to pausable lines.
- End debug with **Stop** or when the script finishes — LSP and editing resume automatically.

## Related

- [Scripts tab](scripts-tab.md)
- [Console and output](console-and-output.md)
