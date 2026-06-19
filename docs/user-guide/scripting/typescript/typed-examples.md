# Typed examples (TypeScript)

Annotations help document expected shapes; they are erased before Deno runs the script.

## Response JSON

```typescript
interface User {
    id: number;
    email: string;
}

pm.test("User shape", () => {
    const data = pm.response.json() as User;
    pm.expect(data.id).to.be.a("number");
    pm.expect(data.email).to.include("@");
});
```

## Request helpers

```typescript
type TokenResponse = { access_token: string; expires_in: number };

async function fetchToken(): Promise<TokenResponse> {
    const res = await pm.sendRequest({
        url: pm.variables.replaceIn("{{authUrl}}/token"),
        method: "POST",
        header: { "Content-Type": "application/json" },
        body: {
            mode: "raw",
            raw: JSON.stringify({ grant_type: "client_credentials" }),
        },
    });
    return res.json() as TokenResponse;
}

const token = await fetchToken();
pm.environment.set("accessToken", token.access_token);
```

## pm.require with types

When you load an npm package, TypeScript may infer `any` unless Deno LSP has cached types:

```typescript
const z = pm.require("npm:zod@3.23.8");
// Use z.parse(...) at runtime; add manual interfaces if needed for strict typing
```

## Tips

- Prefer `interface` or `type` for API payloads you assert in tests.
- Use `as` sparingly — validate with `pm.expect` rather than trusting casts alone.
- Arrow functions in `pm.test` work the same as in JavaScript.

## Related

- [Tests and assertions (JavaScript)](../javascript/tests-and-assertions.md)
- [Getting started](getting-started.md)
