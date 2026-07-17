# Import and save requests

## Import a collection or environment

1. Click **Import** in the collections header (next to **New (+)**).
2. Choose a **file**, **folder**, paste **text**, or paste a **URL**.
3. Follow the import dialog to confirm items.

Supported sources include:

- Postman collection / environment JSON
- cURL commands
- **OpenAPI 3** / **Swagger 2** (JSON or YAML), including a URL to the spec
- **WSDL 1.1** (builds SOAP requests from operations)

Imported collections appear in the left tree.

## Import with the AI assistant

In **Agent** mode, ask in plain language, for example:

- “Make a collection from this OpenAPI URL: https://…”
- “Import this WSDL file: /path/to/service.wsdl”

The assistant proposes the import; click **Allow**. You do not need to open the Import dialog yourself.

See [Agent workspace edits](../ai-assistant/agent-edits.md).

## Import from cURL

Paste a cURL command into the import dialog or use **Import** with raw text. Postmark
creates a request with method, URL, headers, and body filled in.

## Save a draft request to a collection

1. Open a **draft** request tab (unsaved edits).
2. Click **Save** in the toolbar (or use the save flow from the tab).
3. Pick a collection or folder in the save dialog.
4. Confirm the name and location.

## Related

- [Create and organize](create-and-organize.md)
- [Editing and send](../requests/editing-and-send.md)
- [Agent workspace edits](../ai-assistant/agent-edits.md)
