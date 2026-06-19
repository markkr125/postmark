# Models and providers

Add LLM connections and choose which models appear in the chat composer.

## Open settings

1. **File → Settings…** → **AI** → **Models**.

## Add a provider

1. Click **Add provider** (or the equivalent action on the Models page).
2. Enter display name, base URL, and API key (stored securely, not in plain settings).
3. Click **Test connection** to verify credentials.
4. Refresh or fetch the model list for that provider.
5. Enable checkboxes for models you want in the picker.

## Model list

The tree groups models by provider. Columns may show capabilities (suggest, tools, vision) and an **Enabled** checkbox per row.

Use the search field to filter long provider lists.

## Edit or remove

Use the gear menu on a provider row to edit connection details, refresh models, or remove the provider.

## Chat composer

The model shown on the **AI** panel composer opens a picker listing only **enabled** models. Per-message overrides (context window tier, thinking, reasoning effort) are available from the model button's edit flyout when supported.

## Related

- [AI settings hub](README.md)
- [Budgets](budgets.md)
- [Chat](../../ai-assistant/chat.md)
