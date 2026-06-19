# Environment variables

Variables let one request work against dev, staging, and production without duplicating tabs.

## Create an environment

1. Open the left **Environments** flyout.
2. Click **Manage**.
3. Click **New environment** (or edit an existing one).
4. Add rows in the key/value table (e.g. `baseUrl` → `https://api.example.com`).
5. Click **Save Variables**.

## Activate an environment

1. In the environments list, click **Set active** on the row you want.
2. The active row shows a **Clear** control instead — use it to deactivate.

Only one global active environment at a time. Substitution uses its values on **Send** and in the collection runner.

## Use variables in requests

Type double braces anywhere Postmark resolves text:

```text
{{baseUrl}}/users/{{userId}}
```

Common places:

- URL bar and **Params**
- **Headers** and **Body**
- Auth fields that accept text

Hover a `{{name}}` segment in the editor to see where the value comes from (environment, collection, local override, or unresolved).

## Variable scopes (overview)

```text
Local override (this tab only)
  ↓
Iteration data (data-driven runs)
  ↓
Environment (active environment)
  ↓
Collection variables
  ↓
Globals
```

Scripts use the same resolution order through `pm.variables`, `pm.environment`, and related APIs. See [JavaScript variables](../scripting/javascript/variables.md).

## View current values

1. Open the **right rail** **Variables** panel while a request tab is active.
2. Browse resolved names and values (read-only list with source indicators).

To persist a change from the hover popup, use **Update** (writes to collection or environment as appropriate). **Reset** clears a local tab override.

## Dynamic variables

Postmark also supports Postman-style dynamic placeholders such as `{{$guid}}` and `{{$timestamp}}`. These resolve at send time even without an environment selected.

## Related

- [Environments hub](README.md)
- [JavaScript variables](../scripting/javascript/variables.md)
