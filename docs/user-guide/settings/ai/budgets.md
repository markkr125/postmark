# AI budgets

Set soft and hard spend limits per provider connection and monitor usage over time.

## Steps

1. Open **File → Settings…** → **AI** → **Budgets**.
2. Review the table of provider connections with period and overall spend columns.
3. Click the gear on a row → **Limits** to configure caps.

## Limits dialog

| Field | Purpose |
|-------|---------|
| Soft limit (USD) | Warning threshold for the period |
| Hard limit (USD) | Block or warn when exceeded (enforcement depends on provider setup) |
| Token limits | Optional token caps for the period or overall |
| Reset period | Daily, weekly, monthly, or yearly with local reset time |

Spend rolls up from chat message usage when models report priced tokens.

## View breakdown

Use **View breakdown** (page or row menu) to see per-model spend within a connection.

The chat composer's context ring **Spend** tab shows session-level cost for the active chat when pricing metadata exists.

## Related

- [Models and providers](models-and-providers.md)
- [Chat](../../ai-assistant/chat.md)
