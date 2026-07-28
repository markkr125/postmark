# Agent workspace edits

In **Agent** mode, the assistant can propose real changes across your workspace — collections, requests, local scripts, environments, snippets, and more — and run sends or scripts. Risky steps pause for your review; **Ask** and **Plan** stay read-only.

## Turn on Agent edits

1. In the AI panel, set the mode pill to **Agent**.
2. Ask for the change or run you want (for example create a collection, edit a local script, or send a request).

**Ask** / **Plan** can explore your workspace but cannot edit or send.

## Approve or reject proposed actions

When Agent proposes a write or send, an **inline tool card** appears in that assistant turn (not above the composer). The card shows a short title (for example **Create collection**) and a detail line (for example the collection name or request URL). Choose:

| Button | What it does |
|--------|----------------|
| **Allow** | Run the pending actions and continue the turn |
| **Reject** | Skip those actions; the assistant continues without applying them |
| **Always allow** | Add this action kind to auto-approve, then Allow |

If several actions are pending together, the cards stack and the footer offers **Allow all** / **Reject all**.

Use **Stop** on the composer if you want to cancel the whole run while a confirmation is waiting.

UI updates (tree refresh, open tabs, Scripts Output, Response viewer) apply as soon as each approved tool finishes — you do not need to wait for the whole turn to end.

## Auto-approved actions

Kinds you trust can skip the Approve card:

1. Open **File → Settings…** → **AI** → **Agents**.
2. Under **Auto-approved Agent actions**, click **Add…** and pick a kind (for example **Create request** or **Send request**).
3. To stop skipping, select a row and click **Remove**, or click **Remove all**.

An empty list means Postmark asks every time. **Always allow** on the card adds the same list.

Auth and environment-secret updates are never eligible for Always allow — they always pause for **Allow**.

## What Agent can do

With your approval (or auto-approve), Agent can:

### Collections and requests

- Create, update, rename, move, or delete **collections** and **requests**
- Rename a **collection** with `rename` or `update` + `name` (folder title)
- Duplicate a **request**
- Replace a request’s **Assertions** rows
- Update method, URL, headers, params, body, description, scripts, and **auth** (placeholders only — see Safety)
- Update **collection variables** (non-secret values and `{{var}}` placeholders)

### Local scripts

- Create, update, rename, move, or delete **local scripts** and script folders
- **Run** a local script and show results in that script tab’s Output panel

### Environments and globals

- Create, rename, update, or delete **environments**
- **Set or clear** the session’s **active environment** (same as the environments sidebar)
- Merge-write **global** variables
- Secret-typed keys and credential-like names accept only empty values or `{{var}}` placeholders — raw tokens are rejected

### Folder scripts, history, versions, debug metadata

- Update **folder / collection scripts** via `events` (pre-request and test), then open the Scripts tab
- **Delete** a request-history entry (refreshes per-request and global history)
- **Restore** a script version into a request, collection, or local script (merges without wiping sibling script bodies)
- Update **breakpoints / watches** metadata on requests, collections, or local scripts (does not start a debug session)

### Import

- **Import** collections/environments from text, cURL, URL, or a file/folder path — including **OpenAPI / Swagger** (JSON or YAML) and **WSDL** (SOAP operations). You can request a suffix in the same operation (for example, “import this OpenAPI and add `10` to the collection name”); Postmark imports once and names the new root accordingly. The import action pauses for **Allow**.
- **Import from messy PDF/DOCX** — in **Agent** mode, attach a PDF or Word doc with the paperclip and ask for a collection. Postmark copies the file into the chat's own storage and converts it to Markdown. If your model supports images, it is shown the screenshots for the part it is reading; if not, Postmark reads the text out of them for it instead. The assistant then works through that copy in chunks, adding the fully described endpoints from each chunk to a draft in one bounded batch; a name in the table of contents is not enough, and a definition that continues onto the next chunk is read through before it is added. Only the final step, which creates the collection, pauses for **Allow**. Working in chunks keeps the document out of your message, while batching each chunk avoids replaying that text once per endpoint and exhausting the model's context.

  Because Postmark reads its own copy, the conversation keeps working if you later move, rename, or delete the original, and editing the original mid-run cannot shift the document under it. Copies are deleted with the chat. Your file path is never sent to the model or the AI provider — it only sees the file name and the contents. Very long documents are sent up to a limit, and the assistant reads any remainder page by page.
- **Links you can trust** — if the assistant mentions a collection it did not actually create in that reply, Postmark removes the link and adds a warning. A link in an assistant message always points at something real.

### Snippets and saved examples

- Create, update, rename, or delete user **snippets** (and rename/delete categories)
- Save, rename, duplicate, or delete **saved response** examples

### Settings

- Update **allowlisted** prefs (Deno/Python path, LSP, format-on-save, history retention, tab UX). Never AI provider credentials.

### Execute

- **Send** a saved request or the dirty open-tab draft (same path as **Send**), including **binary** body paths (file bytes, allowlisted paths only for Agent-set paths)
- **Replay** a history send — after Allow, the Response viewer loads that history entry
- Run pre-request / test **scripts** without an HTTP round-trip — results appear in the request **Scripts** Output panel
- **Run a collection** (folder checklist) — opens the folder **Runs** tab and writes run history
- **Run data-driven iterations** on a request’s test scripts from an `iteration_data` array (mock response by default)
- **Fetch GraphQL schema** (truncated summary; attaches to an open GraphQL tab when possible)
- **Generate code snippets** (auth secrets stay as `{{var}}` placeholders)
- **Export** test results or collection-run CSV/JSON from history / run ids
- **OAuth Get Token** for `client_credentials` / `password` grants — binds the token to an environment `{{var}}` (token never appears in chat). Browser grants (authorization code / implicit) are not supported yet.

Successful sends appear as a **clickable card** in the assistant message. Click the card to open the request tab with that response loaded in the centre pane — the **AI assistant stays open** (the right flyout does not switch to Request History). Script-run cards focus the matching Scripts phase (pre-request or test). Local-script run cards open the script tab. Collection-run cards open the folder **Runs** panel. Iteration-run cards focus Scripts → test.

Successful edits refresh the relevant sidebar (collections, local scripts, environments, snippets, saved examples, history) and any already-open editors (you do not need to reopen the tab). If a tab had unsaved local edits, Allow still applies the Agent change and replaces that editor state.

## What Agent cannot do yet

Agent does **not**:

- Write raw passwords, API tokens, or other secret values into auth or environment fields via mutate (use `{{var}}` or leave empty). OAuth Get Token may bind a token into an environment secret variable without showing it in chat.
- Step-through **debug** (CDP / settrace pause/step/continue)
- OAuth **browser** grants (authorization code / implicit) — use the Auth tab **Get New Access Token** button
- Open a **file picker** dialog for binary bodies (Agent sets an allowlisted path string only)

For those, edit in the normal UI. Use [Workspace explorer](workspace-explorer.md) to ask about them first.

## Safety

- Edits and sends only run in **Agent** mode.
- Deletes, sends, auth changes, and other risky kinds pause for **Allow** unless auto-approved (auth and environment-secret kinds are never auto-approvable).
- Secret values stay redacted in assistant tool output; send results are summarized without dumping credentials.
- Prefer reviewing the card for first-time or destructive actions; reserve auto-approve for kinds you use often.

## Try this

1. Switch the mode pill to **Agent**.
2. Ask: “Create a GET request named Health under my API collection pointing at `{{baseUrl}}/health`.”
3. When the inline card lists the create action, click **Allow**.
4. Confirm the new request appears in the collection tree (and may open in a tab) without restarting.
5. Ask Agent to send it; **Allow** again (or add **Send request** under **Auto-approved Agent actions** if you want to skip next time).
6. Optional: ask Agent to create a local helper script and run it — Allow, then check the script tab Output.
7. Optional: “Make a collection from this OpenAPI URL: …” — Allow the import; the new collection appears in the left tree.

## Tips

1. Keep **Ask** for exploration; switch to **Agent** only when you want writes or sends.
2. Name collections and requests clearly in your prompt — you never need to type numeric ids.
3. Start with an empty auto-approve list; add kinds only after you trust the summaries on the card.
4. Reject a bad proposal, then rephrase — the assistant can try a different approach.
5. For auth and secrets, tell Agent to use `{{variable}}` placeholders rather than pasting tokens into chat.

## Related

- [Chat](chat.md) — modes, sessions, composer
- [Workspace explorer](workspace-explorer.md) — read-only questions about your workspace
- [AI agents settings](../settings/ai/agents.md) — auto-approve, concurrent runs
- [AI assistant hub](README.md)
