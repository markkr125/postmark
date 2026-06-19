# Scripts tab

Pre-request and test scripts automate requests and validate responses.

## Request-level scripts

1. Open a request in the centre editor.
2. Click the **Scripts** tab (next to **Auth**, **Headers**, **Body**).
3. Use the **Pre-request** editor (runs before **Send**) and **Test** editor (runs after
   the response returns).
4. Set the language from the **status bar** under each editor — click the language label
   (e.g. **JavaScript**) to choose JavaScript, TypeScript, Python, or **Auto**.

## Collection or folder scripts

1. Click a collection or folder in the left tree.
2. Edit **Pre-request Script** and **Test Script** in the folder editor.
3. These scripts run for every request inside that collection or folder.

## Run vs Send

| Action | What runs |
|--------|-----------|
| **Send** | Pre-request chain → HTTP request → test chain |
| **Run** (script toolbar) | Scripts only, without sending HTTP (when available in the script pane) |

## Related

- [First JavaScript test script](javascript/first-test-script.md)
- [Execution order](execution-order.md)
- [Debugging](debugging.md)
