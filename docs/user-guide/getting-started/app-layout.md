# App layout

Postmark divides the window into a **left activity rail**, a **centre work area**
with request tabs, and a **right activity rail** for tools such as the AI assistant,
variables, and history.

## Window layout

```text
+------------------------------------------------------------------+
|  Menu bar (File, Edit, View, …)                                    |
+--------+-------------------------------------------+-------------+
| Left   |  Centre — request / folder / script tabs  | Right rail  |
| rail   |  (editor + response viewer)               | (flyouts)   |
|        |                                           |             |
+--------+-------------------------------------------+-------------+
|  Status bar (optional script language, etc.)                       |
+------------------------------------------------------------------+
```

## Left rail

Click an icon on the left rail to open a flyout panel:

| Icon area | Panel |
|-----------|--------|
| Collections | Collection tree — folders and HTTP requests |
| Environments | Global environment list |
| Local scripts | Reusable script modules |
| History | Workspace-wide send history |

Use **New (+)** in the collections header to create a collection or HTTP request.

## Centre area

- **Request tabs** — open saved requests, drafts, folders, or local scripts as tabs.
- **Request editor** — URL, method, **Auth**, **Headers**, **Body**, **Scripts**, and more.
- **Response viewer** — appears after you click **Send** (status, body, timing).

Double-click a request in the collection tree to open it in a permanent tab. A single
click may open a preview tab depending on your tab settings.

## Right rail

| Icon area | Panel |
|-----------|--------|
| AI | AI assistant chat |
| Variables | Read-only variable values for the active context |
| Snippets | Code snippet generator |
| Saved responses | Examples attached to the active request |
| History | Send history for the **active saved request** |

## Console

Open the application console with **View → Toggle Console** or **Ctrl+J**. Script
`console.log()` / `print()` output appears here and in the script output panel.

## Related

- [Create and organize collections](../collections/create-and-organize.md)
- [Send a request](../requests/editing-and-send.md)
- [AI assistant](../ai-assistant/chat.md)
