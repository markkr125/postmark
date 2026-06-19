# Script execution order

Scripts inherit from parent collections and folders. Order is fixed so behaviour matches Postman-style runners.

## Pre-request scripts (top → bottom)

Before **Send**, scripts run from the collection root down to the request:

```text
Collection pre-request
  → Folder A pre-request
    → Folder B pre-request
      → Request pre-request
        → HTTP send
```

Variable changes in an earlier script are visible to later scripts in the same chain.

## Test scripts (bottom → top)

After the response returns, test scripts run in reverse order:

```text
HTTP response received
  → Request test
    → Folder B test
      → Folder A test
        → Collection test
```

## Example

Request path: `My API > Users > Get user`

```text
1. Collection: set {{apiVersion}} = v2
2. Folder Users: add header X-Tenant
3. Request: set {{userId}} from prior response
4. --- Send GET /users/{{userId}} ---
5. Request test: status is 200
6. Folder Users test: body has id field
7. Collection test: log summary
```

## Collection and folder editors

1. Click a collection or folder in the left tree.
2. Edit **Pre-request Script** and **Test Script** in the folder editor (same inheritance rules for all requests inside).

## Related

- [Scripts tab](scripts-tab.md)
- [Pre-request scripts (JavaScript)](javascript/pre-request-scripts.md)
- [Collection runner](../collection-runner/run-a-collection.md)
