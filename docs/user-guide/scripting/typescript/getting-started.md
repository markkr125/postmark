# Getting started with TypeScript

Write request scripts with optional type annotations for clarity — behaviour matches JavaScript.

## Enable TypeScript

1. Open a request → **Scripts** tab.
2. Click the language label in the status bar under **Pre-request** or **Test**.
3. Choose **TypeScript**.

## First test script

```typescript
pm.test("Status is 200", () => {
    pm.expect(pm.response.code).to.equal(200);
});
```

4. Click **Send** and check **Test Results**.

## Requirements

- **Deno** must be installed or downloaded — see **File → Settings… → Scripting**.
- TypeScript linting in the editor is lighter than JavaScript until a dedicated TS parser is available; runtime errors still surface in **Output**.

## Local scripts

When creating files in the **Local scripts** tree, pick **TypeScript** from **+ New**. Use `.ts` paths and ESM `import` between local files the same way as JavaScript modules.

## Related

- [Typed examples](typed-examples.md)
- [JavaScript first test script](../javascript/first-test-script.md)
- [Choosing a language](../choosing-a-language.md)
