# Postmark app wiki — agent workflow

## When to call ``postmark_wiki_query``

- Questions about **using Postmark** (UI, workflows, settings, scripting, debugging).
- Before writing **pre-request** or **test** scripts for the user.
- When unsure which button, menu, or shortcut exists.

## How to query

1. Read matches from ``data/app-wiki/index.md`` (built by ``scripts/build_app_wiki.py``).
2. Pass a short ``query`` (keywords) or an explicit ``page`` path from the index.
3. Use excerpts returned — cite the page path in your answer.

## Script generation rules

- Use only documented ``pm`` / ``postman`` members **and** the sandbox global
  helpers listed in the quickref (e.g. ``datetime_now()``, ``uuid_v4()``,
  ``require()``) — globals are called WITHOUT a ``pm.`` prefix.
- Do **not** use raw ``fetch``, axios, ``requests.get``, or Node-only HTTP APIs.
- Prefer ``pm.sendRequest`` for chaining requests inside scripts.
- Do **not** invent menu items, shortcuts, or settings labels.

## Sources (read live)

- ``docs/user-guide/`` — step-by-step user how-to
- Allowlisted ``docs/scripting/`` API prose
- ``data/app-wiki/scripting-api/*-quickref.md`` — compact member lists
