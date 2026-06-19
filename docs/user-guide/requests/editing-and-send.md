# Editing and sending a request

Build an HTTP request in the centre editor and send it to your API.

## Open a request

1. In the left **Collections** flyout, double-click a saved request to open it in a tab.
2. Or click **New (+)** → **HTTP Request** to start a draft tab.

## Set method and URL

1. Choose the HTTP method from the method dropdown (e.g. **GET**, **POST**).
2. Enter the URL in the address bar. Use `{{variable}}` for environment or collection variables.
3. Optional: open the **Params** tab to edit query parameters — changes stay in sync with the URL bar.

## Headers and body

1. Click **Headers** to add or edit request headers (key/value table).
2. Click **Body** and pick a body mode (none, raw, form-data, urlencoded, GraphQL, binary, etc.).
3. For **GraphQL**, use the dedicated query editor and optional variables JSON.

## Authentication

1. Click **Auth**.
2. Pick an auth type (Bearer, Basic, API key, OAuth 2.0, and others).
3. Choose **Inherit auth from parent** to use the folder or collection default.

## Send

1. Click **Send** in the toolbar (or use your keyboard shortcut if configured).
2. While the request runs, the response area shows a loading state.
3. When complete, the **Response** viewer shows status, headers, body, timing, and size.

## Inspect the response

| Area | What you see |
|------|----------------|
| Status line | HTTP code, reason phrase, time, size |
| **Body** tab | Response body with syntax highlighting and search |
| **Headers** tab | Response headers |
| **Test Results** | Output from test scripts (if any) |
| **Console** | Script log output from this send |

Click the status, timing, or size badges for breakdown popups.

## Save a draft

Draft tabs are unsaved until you persist them:

1. Click **Save** (or **Save as…** from the menu).
2. Pick a collection or folder and confirm the name.

## Related

- [Variables](../environments/variables.md)
- [Scripts tab](../scripting/scripts-tab.md)
- [Saved responses](saved-responses.md)
