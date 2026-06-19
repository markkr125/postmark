# Folder scripts and inheritance

Collections and folders can run scripts for every child request automatically.

## Open a folder or collection editor

1. Click a **collection** or **folder** in the left collections tree (not a request).
2. The centre area shows the folder editor with **Pre-request Script** and
   **Test Script** editors.

Scripts here run for **all requests** inside that collection or folder.

## Execution order

```text
Pre-request:  Collection → Folder(s) → Request   (top-down)
--- HTTP Send ---
Test:         Request → Folder(s) → Collection   (bottom-up)
```

See [Execution order](../scripting/execution-order.md) for a full example.

## Related

- [Scripts tab](../scripting/scripts-tab.md)
- [Create and organize](create-and-organize.md)
