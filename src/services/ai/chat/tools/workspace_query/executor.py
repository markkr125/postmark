"""OpenHands executor and tool registration for workspace queries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.workspace_snapshot import (
    get_workspace_snapshot,
    resolve_workspace_session_id,
)

from .constants import _MAX_OUTPUT_CHARS, _VALID_SCOPES
from .render import (
    _render_active_response,
    _render_active_tab,
    _render_collection,
    _render_collection_tree,
    _render_environments,
    _render_globals,
    _render_history_entry,
    _render_insights,
    _render_local_scripts,
    _render_open_tabs,
    _render_overview,
    _render_recent_history,
    _render_request,
    _render_request_history,
    _render_request_script_versions,
    _render_run,
    _render_runs,
    _render_saved_response,
    _render_saved_responses,
    _render_script,
    _render_script_version,
    _render_script_versions,
    _render_search,
    _render_settings,
    _render_snippet,
    _render_snippets,
    _render_tab,
    _render_variable,
)
from .helpers import _default_collection_id, _default_request_id, _default_script_id

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation


WORKSPACE_QUERY_DESCRIPTION = """Read the user's Postmark workspace on demand (collections, requests,
open tabs, live response, scripts, environments, run history).

Call with ``scope`` set to the slice you need — never guess workspace facts.

``target_id`` id-type per scope: request id for request, request_history, saved_responses,
and request_script_versions; history-entry id (from ``Ids for follow-up calls`` blocks under
``scope=request_history`` / ``recent_history``) for history_entry; collection (folder) id for
collection and runs; run id (from follow-up ids under ``scope=runs``) for run; local-script id
for script and script_versions; saved example id for saved_response; snippet id for snippet;
version id for script_version; environment id for environments drill-down; 1-based tab index
for tab. These five scopes always require ``target_id``: history_entry, saved_response, run,
script_version, snippet. Omit ``target_id`` to use the active tab's entity of the matching
type for other scopes. ``Ids for follow-up calls`` lines are for tool arguments only — never
paste those numeric ids into the user-visible message.

Live GUI state (captured at turn start, may miss mid-turn edits): open_tabs, active_tab,
active_response, tab; overview mixes live tab/env fields with live DB counts. Saved DB (always
live): collection, request, collection_tree, local_scripts, saved_responses, saved_response,
request_history, history_entry, runs, run, recent_history, environments, script,
script_versions, request_script_versions, script_version, globals, snippets, snippet,
insights, settings. For "what is in my open / dirty tab?" prefer ``active_tab`` / ``open_tabs``
(snapshot fields); ``scope=request`` merges dirty open-tab editor state when the snapshot
has a matching dirty tab (``[partial]``), otherwise reads saved DB.
``scope=variable`` looks up one variable key: definitions (globals / environments /
collections), active override chain, and bounded ``{{key}}`` usages.
``search`` whitespace-splits and AND-matches tokens within one item (any order) for
names, methods, URLs, folder names/paths, request bodies/descriptions, request params tables,
headers/auth types, pre_request/test script bodies, folder scripts, local-script
names/bodies (bounded scan), and enabled environment/global variable keys (non-secret values;
disabled keys are not searched).
It also filters scope=snippets (tokenized) and scope=request_history / recent_history
(single-phrase / date tokens — history filters are **not** tokenized; supports
since:YYYY-MM-DD / until:YYYY-MM-DD). History filters
match stored URL/name/method/status only — not response bodies. Search does **not**
cover assertions, history/saved-response bodies, or snippet bodies (use those dedicated
scopes). Bodies and params are matched after secret redaction, so secret-value searches
can return an authoritative empty result. Multi-word empties are marked ``[partial]``
with a retry hint; single-token empties remain ``[authoritative]`` when exhaustive.

Live GUI scopes (open_tabs, active_tab, active_response, tab) and overview live fields are
captured at **turn start** — mid-turn edits may differ until the next run.

Routing — past sends of the open request: ``scope=request_history`` with ``search=…``
(omit ``target_id`` for the active tab). No saved request → ``recent_history`` + ``search=``.
One send detail → ``history_entry``. Do **not** use ``scope=search`` for send history.

Routing — refine a prior list (“that list”, “those requests”, “among those”): extract request
ids from the previous observation's ``postmark://request/<id>`` links (or follow-up ids),
then re-call ``scope=search`` with the new ``search`` and ``within_ids`` set to those ids —
or pass ``within_ids=[-1]`` to reuse the last search hit set stored for this conversation
(survives compaction; covers the full hit set even when the observation was row-capped).
Invalid ``within_ids`` error out (never unrestricted). If prior ids and last-hits are both
unavailable, re-run the original search first.

This tool is read-only — it cannot send requests, edit collections, or change settings.
Unsaved folder or environment editor changes are not captured in the snapshot.

When you don't have an id, call scope=open_tabs or collection_tree to discover
request/collection/script ids in postmark://…/<id> links, scope=overview for active context,
then drill in; or omit target_id to target what the user is viewing.
Use scope=insights to find requests missing test scripts or declarative assertions,
and to list duplicate method+URL groups.

Routing — where is ``{{key}}`` defined / what overrides what / where used?
→ ``scope=variable`` with ``search=<key>``.

If output says a result is **authoritative**, report it and stop. If output flags a **partial**
or **capped** scan, refine once with a narrower scope/search, then stop. Partial/authoritative
markers appear at the **top** of the observation — read them first.

Focus tokens for links: params, headers, body, auth, description, scripts, assertions,
pre_request, test. Focus is fully honored on request links; only pre_request/test on
collection links; ignored on script links.

Tool calls and their outputs are NEVER shown to the user — only your final message
appears in the chat. Answers must be self-contained: never refer to "the search output,"
"above," "the results returned," or any internal step. When many matches exist, group
and summarize in the message and still include named links for items the user may open.

EVERY request, collection, script, open tab, history send, environment, or saved
example you mention MUST be a
``postmark://request|collection|script|tab|history|environment|saved_response/<id>``
markdown link — in prose, lists, AND
tables. Put the link on the item's NAME. Never print a bare numeric id, never add a
separate unlinked 'ID' column, and never ask the user for a numeric id (they cannot see
or provide those). Point at items by linked name and tell the user to click the link.
If you build a table, the Name column must be the link. Copy the links verbatim from the
tool output — do not strip or rewrite them. Example table row:
``| [Availability](postmark://request/<id>) | GET | …/availability?…checkout=… |``.
``open_tabs`` output is already pre-linked (unsaved drafts use ``tab/<n>``); reuse those
links rather than re-deriving them. Optionally append ``?focus=test`` (or pre_request,
body, assertions, etc.) to entity links."""


class WorkspaceQueryAction(Action):
    """Action to fetch one slice of the Postmark workspace."""

    scope: str = Field(
        description=(
            "Which slice to fetch: overview, open_tabs, active_tab, active_response, tab, "
            "collection_tree, collection, local_scripts, recent_history, request, "
            "request_history, history_entry, saved_responses, saved_response, runs, run, "
            "environments, search, variable, script, script_versions, request_script_versions, "
            "script_version, globals, snippets, snippet, insights, settings. "
            "target_id: request id for request/request_history/saved_responses/"
            "request_script_versions; history-entry id for history_entry; collection id for "
            "collection/runs; run id for run; local-script id for script/script_versions; "
            "saved example id for saved_response; snippet id for snippet; version id for "
            "script_version; environment id for environments drill-down; 1-based tab index "
            "for tab. history_entry, saved_response, run, script_version, and snippet always "
            "require target_id; omit for other scopes to use the active tab's matching entity."
        ),
    )
    target_id: int | None = Field(
        default=None,
        description=(
            "Entity id for scopes that need one (see scope description); defaults to the "
            "active tab's id of the matching type."
        ),
    )
    search: str = Field(
        default="",
        description=(
            "Filter string. For scope=search / collection_tree / local_scripts / snippets: "
            "whitespace-split tokens AND-match within one item (any order). For "
            "scope=variable: exact variable key (casefold). For request_history and "
            "recent_history: single-phrase filter on stored URL/name/method/status "
            "(supports since:YYYY-MM-DD / until:YYYY-MM-DD). For past sends of the open "
            "tab use scope=request_history with search=… (not scope=search)."
        ),
    )
    within_ids: list[int] | None = Field(
        default=None,
        description=(
            "Optional request-id allowlist for scope=search only. When refining a prior "
            'result list ("that list" / "those requests"), pass request ids from the '
            "previous observation's postmark://request/<id> links, or pass [-1] to reuse "
            "the last scope=search hit set stored for this conversation (survives "
            "compaction). Invalid/empty within_ids error out — they never widen to a "
            "full-workspace search. Folder/script-only hits are dropped when set."
        ),
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text for the action."""
        content = Text()
        content.append("Workspace query: ", style="bold cyan")
        content.append(self.scope, style="white")
        if self.target_id is not None:
            content.append(f" (id={self.target_id})", style="dim")
        if self.search:
            content.append(f' search="{self.search}"', style="dim")
        if self.within_ids:
            content.append(f" within_ids={len(self.within_ids)}", style="dim")
        return content


class WorkspaceQueryObservation(Observation):
    """Observation with workspace excerpts."""


_TRUNCATION_LEADING = "[truncated] Output capped to fit the assistant's tool-output limit."
_TRUNCATION_MARKER = (
    "\n\n… (workspace output truncated to fit the assistant's tool-output limit — "
    "narrow with a more specific scope, target_id, or search.)"
)


def _truncate_output(text: str) -> str:
    """Cap total tool output below the OpenHands TextContent limit.

    Prepends a leading ``[truncated]`` marker so models that skim the head of
    the observation still see that the body was cut.
    """
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    leading = _TRUNCATION_LEADING + "\n\n"
    budget = _MAX_OUTPUT_CHARS - len(leading) - len(_TRUNCATION_MARKER)
    head = text[: max(budget, 0)]
    tail_window = head[-400:]
    if "\n" in tail_window:
        head = head.rsplit("\n", 1)[0]
    return leading + head.rstrip() + _TRUNCATION_MARKER


def _dispatch_workspace_query(
    scope: str,
    *,
    session_id: str,
    target_id: int | None = None,
    search: str = "",
    within_ids: list[int] | None = None,
) -> str:
    """Run one workspace query scope and return uncapped markdown text."""
    if scope not in _VALID_SCOPES:
        allowed = ", ".join(sorted(_VALID_SCOPES))
        return f"Unknown scope {scope!r}. Use one of: {allowed}."

    snap_raw = get_workspace_snapshot(session_id)
    snap = snap_raw or {}

    _LIVE_SCOPES = frozenset({"overview", "open_tabs", "active_tab", "active_response", "tab"})
    if scope in _LIVE_SCOPES and snap_raw is None:
        return (
            "Live GUI snapshot unavailable for this conversation (it is captured once at "
            "run start). DB-backed scopes (collection_tree, request, environments, "
            "recent_history, …) still work."
        )

    if scope == "overview":
        return _render_overview(snap)
    if scope == "open_tabs":
        return _render_open_tabs(snap)
    if scope == "active_tab":
        return _render_active_tab(snap)
    if scope == "active_response":
        return _render_active_response(snap)
    if scope == "tab":
        if target_id is None:
            return "Set target_id to a 1-based tab index from scope=open_tabs."
        return _render_tab(snap, target_id)
    if scope == "settings":
        return _render_settings()
    if scope == "collection_tree":
        return _render_collection_tree(search)
    if scope == "local_scripts":
        return _render_local_scripts(search)
    if scope == "recent_history":
        return _render_recent_history(search=search)
    if scope == "environments":
        return _render_environments(env_id=target_id)
    if scope == "globals":
        return _render_globals()
    if scope == "snippets":
        return _render_snippets(search)
    if scope == "insights":
        return _render_insights()
    if scope == "search":
        return _render_search(search, snap=snap, within_ids=within_ids, session_id=session_id)
    if scope == "variable":
        return _render_variable(search, snap=snap)

    if scope == "request":
        rid = target_id if target_id is not None else _default_request_id(snap)
        if rid is None:
            return "No request id; open a request tab or set target_id."
        env_raw = snap.get("current_env_id")
        env_id = env_raw if isinstance(env_raw, int) else None
        return _render_request(rid, env_id=env_id, snap=snap)
    if scope == "request_history":
        rid = target_id if target_id is not None else _default_request_id(snap)
        if rid is None:
            return "No request id; open a request tab or set target_id."
        return _render_request_history(rid, search=search)
    if scope == "history_entry":
        if target_id is None:
            return (
                "Set target_id to a history entry id from scope=request_history "
                "(see Ids for follow-up calls → target_id=…)."
            )
        return _render_history_entry(target_id)
    if scope == "saved_responses":
        rid = target_id if target_id is not None else _default_request_id(snap)
        if rid is None:
            return "No request id; open a request tab or set target_id."
        return _render_saved_responses(rid)
    if scope == "saved_response":
        if target_id is None:
            return (
                "Set target_id to a saved example id from scope=saved_responses "
                "(see Ids for follow-up calls → target_id=…)."
            )
        return _render_saved_response(target_id)
    if scope == "runs":
        cid = target_id if target_id is not None else _default_collection_id(snap)
        if cid is None:
            return "No collection id; open a folder tab or set target_id."
        return _render_runs(cid)
    if scope == "collection":
        cid = target_id if target_id is not None else _default_collection_id(snap)
        if cid is None:
            return "No collection id; open a folder tab or set target_id."
        return _render_collection(cid)
    if scope == "run":
        if target_id is None:
            return (
                "Set target_id to a run id from scope=runs "
                "(see Ids for follow-up calls → target_id=…)."
            )
        return _render_run(target_id)
    if scope == "script":
        sid = target_id if target_id is not None else _default_script_id(snap)
        if sid is None:
            return "No script id; open a local script tab or set target_id."
        return _render_script(sid)
    if scope == "script_versions":
        sid = target_id if target_id is not None else _default_script_id(snap)
        if sid is None:
            return "No script id; open a local script tab or set target_id."
        return _render_script_versions(sid)
    if scope == "request_script_versions":
        rid = target_id if target_id is not None else _default_request_id(snap)
        if rid is None:
            return "No request id; open a request tab or set target_id."
        return _render_request_script_versions(rid)
    if scope == "script_version":
        if target_id is None:
            return (
                "Set target_id to a script version id from scope=script_versions "
                "(see Ids for follow-up calls → target_id=…)."
            )
        return _render_script_version(target_id)
    if scope == "snippet":
        if target_id is None:
            return (
                "Set target_id to a snippet id from scope=snippets "
                "(see Ids for follow-up calls → target_id=…)."
            )
        return _render_snippet(target_id)

    return f"Unhandled scope {scope!r}."


def execute_workspace_query(
    scope: str,
    *,
    session_id: str,
    target_id: int | None = None,
    search: str = "",
    within_ids: list[int] | None = None,
) -> str:
    """Run one workspace query and return markdown text."""
    return _truncate_output(
        _dispatch_workspace_query(
            scope,
            session_id=session_id,
            target_id=target_id,
            search=search,
            within_ids=within_ids,
        )
    )


class WorkspaceQueryExecutor(ToolExecutor):
    """Read-only executor for workspace lookups."""

    def __call__(
        self,
        action: WorkspaceQueryAction,
        conversation: BaseConversation | None = None,
    ) -> WorkspaceQueryObservation:
        """Run the workspace query and return excerpts."""
        session_id = ""
        if conversation is not None:
            state = conversation.state
            persistence_dir = getattr(state, "persistence_dir", None)
            session_id = resolve_workspace_session_id(
                str(state.id),
                persistence_dir=persistence_dir,
            )
        text = execute_workspace_query(
            action.scope,
            session_id=session_id,
            target_id=action.target_id,
            search=action.search,
            within_ids=action.within_ids,
        )
        return WorkspaceQueryObservation.from_text(text)


class PostmarkWorkspaceQueryTool(ToolDefinition[WorkspaceQueryAction, WorkspaceQueryObservation]):
    """Postmark workspace query tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single workspace query tool instance."""
        del conv_state
        if params:
            msg = "postmark_workspace_query does not accept parameters"
            raise ValueError(msg)
        return [
            cls(
                description=WORKSPACE_QUERY_DESCRIPTION,
                action_type=WorkspaceQueryAction,
                observation_type=WorkspaceQueryObservation,
                executor=WorkspaceQueryExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


def register_workspace_query_tool() -> None:
    """Register ``postmark_workspace_query`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool("postmark_workspace_query", PostmarkWorkspaceQueryTool)
