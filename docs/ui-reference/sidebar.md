# Sidebar

Icon rails with collapsible flyout panels: **LeftSidebar** hosts the
collections and environment picker on one stacked page, **Local scripts &
snippets** on another (Phosphor **code** icon), and workspace **History** on a
third (Phosphor **clock-counter-clockwise**); **RightSidebar** hosts variables,
snippets, saved responses, per-request History, and the AI assistant chat.

Source: `src/ui/sidebar/`

## LeftSidebar

VS Code–style **activity bar** on the outer left edge.  The rail is a
fixed-width `QWidget` (`objectName` ``leftSidebarRail``); width and Phosphor
icon size follow ``LEFT_RAIL_WIDTH_EM`` and ``LEFT_RAIL_ICON_EM`` in ``theme.py``
(multiples of the primary font height).  Its background uses palette
``status_bar_bg`` (same as ``QStatusBar#appStatusBar``).  The checked
icon’s left accent is **painted** in ``_LeftRailButton.paintEvent`` at full
widget height (``LEFT_RAIL_ACCENT_STRIPE_WIDTH_PX`` wide) because Fusion-style
``QToolButton`` stylesheets often clip ``border-left`` to the content box.  The flyout uses
``objectName`` ``leftSidebarFlyout``; unlike the right rail flyout it has **no**
built-in title row (the injected ``CollectionWidget`` already owns the
``CollectionHeader`` heading).  The flyout body is a ``QStackedWidget``: page
0 is ``MainWindow``'s vertical ``_left_nav_splitter`` (collections above
environments); page 1 is a vertical splitter: ``CollectionWidget(variant="local_scripts")``
(script/folder tree) above ``SnippetsSidebarPanel`` (user snippet list with **New** /
row click → edit dialog).  Horizontal inset for the collections and environment bodies uses
``LEFT_NAV_PANEL_MARGIN_H_LEFT_PX`` /
``LEFT_NAV_PANEL_MARGIN_H_RIGHT_PX`` in ``theme.py``, applied inside
``CollectionWidget`` and ``EnvironmentSidebarPanel`` so the vertical splitter
between them stays full flyout width (only the pane content is inset).
When the splitter width is 0, the flyout applies a **local** ``setStyleSheet``
to remove borders so they are not painted on top of the main splitter handle.
When open, the flyout uses a **left** border only (vs the rail); the **right**
edge is the main horizontal splitter handle only, so there is no double line
beside the editor.  Page 0 is installed via :meth:`LeftSidebar.set_content`; page
1 via :meth:`LeftSidebar.set_local_scripts_panel` (which also reveals the second
rail icon); page 2 via :meth:`LeftSidebar.set_history_panel` (workspace send
history, ``objectName`` ``globalHistoryPanel``).

### Rail Buttons

| Button | Icon (Phosphor) | Panel |
|--------|-----------------|-------|
| Collections | `files` | Collections tree + environment rows (``_left_nav_splitter``) |
| Local scripts & snippets | `code` | Local scripts tree + ``SnippetsSidebarPanel`` (vertical splitter) |
| History | `clock-counter-clockwise` | ``HistoryPanel`` in global mode — all sends; Open navigates to editor |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `panel_state_changed` | `bool` | ``True`` when flyout width becomes non-zero, ``False`` when collapsed to zero |

### Public API

| Method | Description |
|--------|-------------|
| `set_content(widget)` | Install page ``"collections"`` (collections + environments splitter) |
| `set_local_scripts_panel(widget)` | Register page ``"local_scripts"`` and show its rail icon |
| `install_in_splitter(splitter)` | Insert rail then flyout as the first two splitter children |
| `open_panel(key="collections")` | Expand flyout and activate the rail button (no-op if *key* is not registered) |
| `close_panel()` | Collapse flyout to zero width (same end state as dragging the handle closed) |
| `toggle_panel(key)` | Toggle the named panel |
| `is_open` | Property: flyout width is non-zero |

**View → Toggle Sidebar** (``Ctrl+B``) calls :meth:`close_panel` when the flyout
is open and :meth:`open_panel` when it is closed — it does not hide the
activity rail, so it matches a manual resize of the flyout to zero width.

## SnippetsSidebarPanel

User-authored script snippets in a **tree** (same interaction model as local
scripts): **JavaScript**, **TypeScript**, and **Python** as separate top-level
nodes (not grouped), each containing category folders, then snippet leaves.
**New** opens ``SnippetCaptureDialog`` in sidebar-create mode (language defaults
from the selected branch); clicking a snippet opens edit (save only — use
**Remove snippet** in the tree context menu to delete).  Create and edit dialogs open at **720×580** with a
``CodeEditorWidget`` body (syntax highlighting, folding, and language-aware
completion for JavaScript, TypeScript, or Python).  Header layout matches local scripts (**Snippets** title, section
**(i)** for panel help, **Search snippets**, **New**).  Snippet leaves use the same row height and indentation as local script files.

Right-click context menus:

| Node | Actions |
|------|---------|
| Language | **Add new category** (name prompt, then create-snippet dialog with that category) |
| Category | **Add new snippet**, **Rename category**, **Remove category** (deletes all snippets in the category) |
| Snippet | **Edit snippet**, **Rename snippet** (in-place overlay, like local scripts), **Remove snippet** |

Language roots show a muted trailing count (e.g. ``3 snippets``). Snippet leaves show a
muted context tag (**Pre-request**, **Post-response**, or **Any**) on the right.
Category **Rename** uses the tree's in-place folder editor.

The snippet picker (``SnippetsPopup``) is insert-only — no delete control on
user rows.

Source: ``src/ui/sidebar/snippets_sidebar_panel.py``.

## LocalScriptsSidebarPanel (legacy)

Unused legacy shell — still re-exported from ``src/ui/sidebar/__init__.py`` but
**not** installed by ``MainWindow``.  The live local-scripts flyout top pane is
``CollectionWidget(variant="local_scripts")``.  See [Local scripts](local-scripts.md).
Source: ``src/ui/sidebar/local_scripts_sidebar_panel.py``.

## RightSidebar

Always-visible fixed-width icon rail.

### Rail Buttons

| Button | Icon | Panel |
|--------|------|-------|
| AI assistant | sparkle | `AiChatPanel` — multi-session chat (transcript + composer + streaming) |
| Variables | `{}` | Read-only variable list |
| Code Snippet | `<>` | Code snippet generator |
| Saved Responses | `[]` | Saved response browser |
| History | clock (counter-clockwise) | Per-request send log (read-only) |

Panel key for session restore / `open_panel`: `"ai"`. The AI rail button is always
enabled; `_toggle_panel("ai")` opens without checking `_available_panels`, while
`open_panel("ai")` requires `"ai"` in `_available_panels` (always true after
`clear()`, and included in request/folder contexts). The flyout title bar shows
**session history** (clock), **new chat** (note-pencil), and **gear** buttons
(left of close) when the AI panel is open. History opens ``AiSessionHistoryPopup``
(search + relative-time list); new chat clears the transcript and persisted
``ai/chat_session_id`` (SQLite row created on first send). On startup,
``MainWindow`` reloads the last active session from ``ai/chat_session_id`` when
set. The gear emits ``RightSidebar.ai_settings_requested``; ``MainWindow``
opens Settings on the **AI** category and refreshes the model picker when the
dialog closes.

#### AI composer input (auto-grow)

Source: ``ui/sidebar/ai/chat_panel/composer.py`` — class ``_ComposerInput`` (``QPlainTextEdit``),
``objectName="aiChatInput"``, styled in ``global_qss.py``.

**Problem solved.** The prompt used to call ``setFixedHeight(72)`` (~3 visible lines).
Long messages scrolled inside a tiny box. The fixed height was removed; height is
recomputed from content instead.

**User-visible behavior (matches the auto-grow plan).**

| State | Behavior |
|-------|----------|
| Empty / short text | Minimum **3 lines** tall (comfortable default, same ballpark as the old 72px box). |
| Typing or wrapping | Grows line-by-line with content (word wrap at widget width). |
| More than 15 visual lines | Height stops at **15 lines**; vertical scrollbar appears; content still scrolls inside. |
| Delete text / send | Shrinks back down (``clear()`` after send triggers the same resize path). |
| Submit | **Enter** emits ``submit_requested`` → ``AiChatPanel._on_send`` (Shift+Enter inserts a newline). |

#### User messages

User prompts render in ``aiChatMessageUser`` (``ChatMessageBubble`` user row) with
wrapped text in ``aiChatUserMessageText``. A muted ``aiChatUserMessageTime`` label
inside the bubble below the prompt shows when the message was sent (local date and
clock, e.g. ``Jun 7, 2:39 PM``). New sends pass ``sent_at=datetime.now(UTC)``;
``load_transcript`` restores user rows from persisted ``created_at``.

#### Assistant answer markdown

Source: ``ui/sidebar/ai/message_bubble/markdown_content.py`` (``MarkdownContent``,
``objectName="aiChatAssistantText"``) and ``ui/sidebar/ai/markdown/``.

Finalized assistant rows are lightweight ``QWidget`` instances that paint an owned
``QTextDocument`` (not per-row ``QTextBrowser`` widgets), so long transcripts scroll
without repainting heavyweight browser chrome on every tick. The active streaming
bubble uses the same widget and document with the incremental cache below.

Prose (bold, lists, links) is converted with Qt ``QTextDocument.setMarkdown``.
Fenced code blocks are split out and rendered as themed HTML: Pygments syntax
highlighting (palette editor token colours), line numbers, language label, and
``pre-wrap`` wrapping for long one-liners. The block chrome is a sharp-cornered
``1px`` table frame (``ThemePalette`` ``border`` on all sides, header rule under
the language label). Inline `` `code` `` spans get a muted pill style. Inner block
chrome uses inline styles from ``ThemePalette`` (QSS does not apply inside
rich-text HTML). ``ThemeManager.theme_changed`` re-renders stored markdown on live
assistant rows.

**Streaming performance.** Worker ``chunk_received`` deltas are coalesced on the
GUI thread (~50ms) before updating the active bubble. Rich markdown stays live
during streaming via an incremental segment renderer: stable prose and closed code
blocks are reused; only the changed tail is re-rendered. Open (unclosed) fenced
code uses a cheap provisional monospace block; full Pygments highlighting applies
when the fence closes or the stream finalizes. The transcript scroll area
(``aiChatScroll``) uses **smooth wheel scrolling** via ``SmoothScroller``
(``chat_panel/smooth_scroll.py``): a viewport event filter intercepts wheel input
forwarded from message rows, accumulates a target scrollbar offset, and animates
``verticalScrollBar`` movement at ~60Hz with a time-based OutCubic ease;
mouse ``angleDelta`` uses browser-like notch distance, while trackpad ``pixelDelta``
is amplified and animated through the same path. Streaming auto-follow and turn-boundary
scrolls stay **instant** through ``_set_bar_value`` (signal-blocked), which also
cancels any in-flight smooth animation. Sticky overlay sync is deferred until the
animation settles so per-frame work stays light. ``aiChatScroll`` also uses a
two-phase scroll model:

1. **Turn boundary (Send)** — ``begin_assistant_stream`` calls
   ``_request_turn_bottom_scroll()`` once: re-arms scroll-lock, then a coalesced
   ``singleShot(0)`` scroll to the **last user bubble** (turn-start anchor via
   ``mapTo``), not ``setValue(maximum)``.
2. **Streaming growth** — ``rangeChanged``, chunk flush, and deferred
   markdown/bubble height changes call ``_queue_stream_follow_passes()`` while
   scroll-lock is on: at most one coalesced ``_flush_stream_follow_frame`` (0ms)
   per burst applies ``_apply_stream_follow()``; a ``_flush_stream_follow_retry``
   (16ms) is scheduled only when the frame pass is still off-target or scrollbar
   range grew (no synchronous follow on queue; no ``processEvents`` in the follow
   path). Chunk flush defers ``MarkdownContent.height_changed`` and
   ``ChatMessageBubble.layout_height_changed`` until one batched
   ``flush_stream_layout()`` at the end of the flush; in-flush layout hook is
   suppressed. Follow target is
   ``_stream_follow_target()``: ``bar.maximum()`` once the turn exceeds one
   viewport; while the turn still fits in one viewport, ``min(maximum,
   turn_start)`` so the user bubble keeps its 8px top margin.

Scroll-lock (2px threshold): while streaming, any **upward** user scrollbar
movement (even 1px from the bottom) detaches follow immediately; reaching the
real bottom re-arms it. Outside streaming, lock tracks ``value >= maximum - 2``.
The initial value is **off** so opening a session at the top of history does not
yank the viewport. ``aiChatScrollDown`` / ``_scroll_to_bottom`` re-arms follow.
A new user turn (``begin_assistant_stream``) re-arms lock via
``_request_turn_bottom_scroll``. Programmatic scrolls (``_set_bar_value``) do not
update lock. Coalesced follow scheduler callbacks no-op once detached. The floating
``aiChatScrollDown`` button appears when detached
and jumps to the bottom on click. Monotonic height floors on the assistant body
and row prevent mid-stream layout shrink (reset when thinking collapses at
answer start). While a stream is open, a sibling spacer widget
(``aiChatStreamingViewportSpacer``) below the assistant row is sized dynamically
as ``max(0, viewport_h - turn_extent)`` via ``_apply_streaming_viewport_spacer``
so ``turn_extent + spacer == viewport_h`` while the turn is shorter than one
viewport; panel ``resizeEvent`` and chunk flush refresh spacer height when the
flyout is resized or content grows.

**Pane resize coalescing.** Continuous flyout/splitter resize used to relayout
every assistant ``MarkdownContent`` row on each mouse move. The right-sidebar
splitter handle now marks ``AiChatPanel`` as ``_resize_active`` on mouse press,
before Qt asks transcript children for height-for-width layout. While active,
historical ``MarkdownContent`` rows keep their previous ``QTextDocument`` width
and height; ``heightForWidth()``, ``resizeEvent()``, and ``_sync_height()`` return
cached/current values without calling ``QTextDocument.setTextWidth()`` or
``documentSize()``. The active streaming assistant row still reflows so live
output remains correct. Sticky extent invalidation still runs each resize step;
``_schedule_sticky_sync()`` is deferred until a 75ms settle timer
(``_RESIZE_SETTLE_MS``) fires ``_on_resize_settled()``, which batch-flushes
deferred rows and runs one sticky pass. Hidden panels skip resize work.
``MarkdownContent`` caches measured height per text width to avoid duplicate
``QTextDocument`` layout during ``heightForWidth`` and ``_sync_height``.

**Sticky turn prompt.** While scrolling through any turn in the transcript,
``_sync_sticky_turn_prompt()`` picks the closest eligible user/assistant pair for
the current viewport (not just the latest turn) and shows a read-only clone
(``aiChatStickyTurnPrompt``) pinned to the top of ``aiChatScroll``'s viewport.
The clone copies the anchor user prompt and ``sent_at`` timestamp, compacts row
margins to pin flush to the viewport top, keeps at least 3px inset from the
viewport right edge, and sits up to 4px further left than the in-transcript
user bubble.
Sticky overlay logic lives in ``chat_panel/sticky_prompt.py``
(``_ChatPanelStickyPromptMixin``). Turn pairs are cached in ``_sticky_turn_pairs`` with
a dirty flag; scroll-independent Y extents per pair live in ``_sticky_turn_extents``
(indexed by turn identity) and are rebuilt lazily when layout, resize, or transcript
mutations mark them dirty. Viewport selection uses arithmetic
(``messages_y - scroll_value``) instead of per-tick ``mapTo``. Event-driven updates
call ``_schedule_sticky_sync()`` (one coalesced ``singleShot(0)`` pass per frame;
deferred while smooth scroll animates or pane resize is coalescing);
explicit paths (turn scroll, load finalize, stream end, resize settle) call
``_sync_sticky_turn_prompt()`` synchronously. When anchor, geometry, and height cap are
unchanged, sticky sync skips all overlay widget mutation. The overlay uses
``WA_TransparentForMouseEvents``, does not change scroll range,
and is clamped to 35% of viewport height for tall prompts (``aiChatUserMessageFade``
gradient at the clipped bottom). It hides when the real user bubble is visible near
the top, when the turn answer has scrolled fully above the viewport, or when the
assistant bottom no longer extends below the sticky overlay height. ``_turn_scroll_anchor``
remains the streaming turn-start anchor; ``_sticky_turn_anchor`` is the visual
overlay source selected from viewport position. ``load_transcript`` +
``_finish_load_transcript_layout`` re-lays out markdown at the real viewport width
and hooks all assistant rows for sticky resync. ``aiChatScrollDown`` stays above
the sticky overlay.

**Interaction.** Assistant markdown supports drag-select, double-click word select,
Ctrl+C / Ctrl+A, and a context-menu **Copy** for the selection. External links open
via document ``anchorAt`` when the click does not create a selection. Right-click
**Copy message** copies the full markdown source. User prompts, timestamps, thought
text, and activity captions use selectable labels.

**Wheel routing.** ``MarkdownContent`` (``aiChatAssistantText``) and
``_WrappingLabel`` (``aiChatUserMessageText``, ``aiChatThoughtText``) forward
wheel events to the ancestor transcript ``QScrollArea`` viewport so scrolling over
assistant/thinking/user text does not trap input in inner widgets.

#### Streaming activity indicator

While waiting for the first assistant token, the transcript shows
``aiChatActivityRow`` — a braille spinner (``aiChatActivitySpinner``, shared with
script run busy chips) and a muted caption (``aiChatActivityLabel``; default
``Thinking…``). ``begin_assistant_stream`` shows the row and schedules
``_request_turn_bottom_scroll`` (turn-start anchor scroll); the first
thinking or answer chunk hides it. SDK ``status_changed`` events
update the caption only while the row is visible (sanitized via
``format_activity_status`` in ``chat_panel_streaming.py``). After 15 seconds
without a token, the caption escalates to ``Taking longer than expected…``.

**Implementation (Qt-specific).** Web chat UIs often use ``textarea`` + ``scrollHeight``;
here the equivalent is:

1. Listen to ``document().documentLayout().documentSizeChanged`` (and ``resizeEvent``,
   because changing width changes wrap and thus line count).
2. Read **visual line count** from ``documentLayout().documentSize().height()``.
   For ``QPlainTextEdit`` this value is **not pixels** — it is the number of
   wrap-aware visual lines (Qt ``QPlainTextDocumentLayout`` reports line count in the
   height component of ``documentSize()``).
3. Convert to pixels: ``visual_lines * fontMetrics().lineSpacing() + vertical_chrome``.
4. Clamp between ``_COMPOSER_MIN_LINES`` (3) and ``_COMPOSER_MAX_LINES`` (15), then
   ``setFixedHeight(target)``.
5. If content exceeds the cap, set vertical scrollbar policy to ``ScrollBarAsNeeded``;
   otherwise ``ScrollBarAlwaysOff``.

**Vertical chrome** (must stay in sync with QSS) is computed in ``_vertical_chrome()``:

- ``_COMPOSER_QSS_VERTICAL_PADDING = 12`` — mirrors ``padding: 6px`` top+bottom on
  ``aiChatInput`` in ``global_qss.py``.
- Plus frame width and ``2 * document().documentMargin()``.

**Constants** (change these to tune the composer, then adjust tests if needed):

```python
_COMPOSER_MIN_LINES = 3
_COMPOSER_MAX_LINES = 15
_COMPOSER_QSS_VERTICAL_PADDING = 12
```

**Tests:** ``tests/ui/sidebar/test_sidebar.py`` — ``test_ai_composer_grows_with_lines``,
``test_ai_composer_caps_at_max_lines``, ``test_ai_composer_shrinks_back``.

**Plan checklist (all implemented).**

- [x] ``_ComposerInput.__init__`` — wrap, scrollbar defaults, ``documentSizeChanged`` hook.
- [x] ``_adjust_height`` / ``_vertical_chrome`` / ``resizeEvent``.
- [x] Removed ``setFixedHeight(72)`` from ``AiChatPanel.__init__``.
- [x] Unit/UI tests for grow, cap, shrink.
- [x] ``src/ui/AGENTS.md`` ``aiChatInput`` row; this section in ``sidebar.md``.

The composer **mode** control is a compact pill (``aiChatModeButton``): mode icon,
label, and caret on a **darker** background (``composer_pill_dark_bg`` in
``theme.py``; ``QFrame`` + ``WA_StyledBackground`` so Qt paints rounded fill). Clicking opens ``AiAgentModePopup`` (``agent_mode_popup.py``) **above**
the pill with **Agent**, **Ask**, and **Plan** rows (icon + checkmark + soft hover).
Click outside, press Escape, or click the pill again to dismiss.

The composer's **model** control is a compact pill (``ModelPickerButton`` /
``aiChatModelButton``) with the lighter ``bg_alt`` fill (rounded border, 12px label,
caret on the right). It shows the current model and opens
``AiModelPickerPopup`` (``model_picker_popup.py``)
— a frameless popover with a search field, an enabled-model list grouped by
provider (bold provider heading, indented model rows with **context** and
**reasoning effort** tags), hover **Edit** on configurable rows (opens
``AiModelPickerEditPanel`` — opens **to the left** of the picker (side-by-side,
Cursor composer style) with **Context**, **Options** (thinking toggle), **Reasoning**,
and checkmarks on list options). Click **Edit** again or
outside the flyout to dismiss.
Context presets for cloud models follow LiteLLM pricing tiers (e.g. 272k vs 1M for
GPT-5.5); Ollama keeps stepped presets. A **gear** icon beside the search field opens
Settings → AI → Models. The model button label shows ``<name> · <ctx> · <Effort>`` when
applicable. Picking a row updates the button and ``current_model_id()``; per-model
settings persist via ``AiConfig`` (``context_limit``, ``thinking_enabled``,
``reasoning_effort``) and survive provider refresh (matched by ``model`` string).
The manage control emits
``AiChatPanel.manage_models_requested`` → ``MainWindow`` opens Settings → AI →
**Models** and refreshes the picker.

A **chart-pie-slice** icon button (shared ``iconButton`` styling) shows context
usage in its tooltip via ``set_context_usage()``; clicking emits
``context_requested`` (not wired yet).

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `_flyout` | `_FlyoutPanel` | Collapsible content panel |
| `_active_panel` | `str \| None` | Currently visible panel name |
| `_available_panels` | `set[str]` | Panels usable for current request |

### Public API

| Method | Description |
|--------|-------------|
| `load_variables(variables, local_overrides)` | Refresh variables panel |
| `load_snippet_for_request(request_id)` | Refresh snippet (live on change) |
| `load_saved_responses(request_id)` | Refresh saved responses list |
| `set_request_history_context(...)` | Configure History panel for active request |
| `install_in_splitter(splitter)` | Place flyout and rail as splitter children |

## FlyoutPanel

Collapsible content area as a splitter child (`objectName` ``sidebarPanelArea``).

Contains five stacked panels with a title bar and close button.
The flyout can snap closed via its splitter handle.  The **left** edge against
the editor is the ``mainWindowHorizontalSplitter`` handle only (no flyout
``border-left`` — a full-height left border was hidden under ``QScrollArea``
children and looked like a stray line beside the title row).  The **right**
edge uses a flyout ``border-right`` (and the same on inner ``QScrollArea``
widgets, including ``aiChatScroll``, plus ``aiChatComposer`` below the transcript,
so opaque children do not paint over the seam) before
the icon rail. The rail has no ``border-left`` so the seam is a single line.

## VariablesPanel

Read-only display of resolved variables grouped by source.

### Sections (collapsible)

| Section | Content |
|---------|---------|
| Environment | Variables from active environment |
| Collection | Variables from selected collection |
| Local Overrides | Per-request temporary overrides |

Each row shows key and value as read-only line edits (selectable text); the key
column is wider than before with the full name on hover. Very long values start
collapsed behind a Phosphor caret icon (same ``data/fonts/phosphor.ttf`` set as
elsewhere via ``phi()``) to expand the full text.

### Key Method

`load_variables(variables, local_overrides, has_environment)` —
populate sections from `VariableDetail` dicts.

## Script debug widgets (`debug_inspector_split`, `debug_call_stack_panel`, `debug_watch_in_tree`)

Source: `src/ui/sidebar/debug_inspector_split.py` (horizontal **Call stack |
Watches strip + unified tree**), `debug_call_stack_panel.py`, `debug_scopes_panel.py`,
`debug_watch_in_tree.py`.  Composed into `ScriptOutputPanel` during inline script
debug (see [Request Editor — Inline debug inspector](request-editor.md#inline-debug-inspector-debugger-tab)).
`DebugPanel` in `debug_panel.py` bundles step controls and
:class:`DebugInspectorSplit`.

### DebugInspectorSplit layout

```text
+------------------+---------------------------+
| Call stack       | Watches (expression strip)|
| (full height)    +---------------------------+
|                  | debugScopesTree           |
|                  |  Watches / Locals / pm …  |
+------------------+---------------------------+
```

| `objectName` | Description |
|--------------|-------------|
| `debugInspectorSplitter` | Horizontal splitter (~200px call stack \| values column) |
| `debugCallStackList` | Frame list (left column, full height) |
| `debugWatchAddEdit` | Watch expression field above the tree (+ / − icon buttons) |
| `debugScopesTree` | **Watches** section + locals / `pm` / `globalThis` / env (one tree) |

While **paused**, `DebugWatchesPane.refresh_watches()` calls
`DebugProtocol.submit_evaluate(expr)` (non-blocking). Value cells show
`cached_evaluate(expr)` immediately (placeholder `—` until the first result).
`DebugProtocol.evaluated` updates the tree when the background worker or batch
evaluator returns.  Expressions persist across `set_idle` and `clear_session`;
`set_idle` clears the eval cache and prunes orphan `pm.require` LSP workspace keys.

### CallStackPanel

| Signal | Parameters | Description |
|--------|------------|-------------|
| `frame_selected` | `int` | Stack frame index; host calls `select_frame` and refreshes variables |

| `objectName` | Description |
|--------------|-------------|
| `debugCallStackList` | Frame labels `index: name  @ line N` (1-based line in UI) |

## SnippetPanel

Inline code snippet generator.

### UI Components

| Component | Description |
|-----------|-------------|
| Language dropdown | 23 languages in 3 categories |
| Code editor | Read-only `CodeEditorWidget` |
| Copy button | Copy snippet to clipboard |
| Settings gear | Per-language option popup |

### Language Categories

| Category | Languages |
|----------|-----------|
| Shell | cURL, HTTP raw, wget, HTTPie, PowerShell |
| Dynamic | Python, JavaScript, Node.js, Ruby, PHP, Dart |
| Compiled | Go, Rust, C, Swift, Java, Kotlin, C# |

### Settings Popup Options

Indent count (1-8), indent type (space/tab), trim body, follow
redirects, timeout.  Language-specific: async/await (JS), ES6 (JS),
multiline (cURL), long-form flags, quote style, etc.

Snippets regenerate live as the request changes.

## SavedResponsesPanel

List/detail flyout for browsing saved response examples.

Source: `src/ui/sidebar/saved_responses/`

### Layout

```
+-----------------------+-----------------------+
| Saved Responses List  | Detail View           |
| (filtered by request) |                       |
|                       | Status badge + name   |
| [Response 1]          | Tabs:                 |
| [Response 2]          |   Body | Headers |    |
| [Response 3]          |   Request Body        |
+-----------------------+-----------------------+
| Refresh | Save Current                        |
+-------------------------------------------+
```

### List Item Delegate

`SavedResponseDelegate` renders each row with a coloured status code,
response name, and timestamp.

### Detail View Tabs

| Tab | Content |
|-----|---------|
| Response body | Code editor with mode selector |
| Response headers | Read-only key-value list |
| Request body | Original request body snapshot |

### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_current_requested` | *(none)* | Save current response |
| `rename_requested` | `int` | Rename response |
| `duplicate_requested` | `int` | Duplicate response |
| `delete_requested` | `int` | Delete response |

### Search and Filter (_PanelSearchFilterMixin)

Filter by name and search within response bodies.

## HistoryPanel

Read-only list/detail UI for HTTP **send history**. The same widget class is
used twice:

| Instance | `objectName` | Rail | Data source |
|----------|--------------|------|-------------|
| Per-request | `requestHistoryPanel` | Right (4th button) | `RequestHistoryService.list_for_request(request_id)` |
| Workspace global | `globalHistoryPanel` | Left (3rd button) | `RequestHistoryService.list_for_sidebar()` |

Source: `src/ui/sidebar/history/` (`panel.py`, `global_mode/`).

See also [RequestHistoryService](../api-reference/services/request-history-service.md).

### objectNames

| Widget | objectName | Mode |
|--------|------------|------|
| Panel (request) | `requestHistoryPanel` | Right rail |
| Panel (global) | `globalHistoryPanel` | Left rail |
| Global header row | `globalHistoryHeader` | Left rail only (title + date filter + refresh) |
| Date filter button | `iconButton` (funnel) | Global header; per-request search row |
| Date filter popup | `infoPopup` | From/To pickers, presets (Today, 7/30 days, All), Apply, Clear |
| Date editors | `historyDateFilterEdit` | Inside the filter popup |
| Search field | `requestHistorySearch` | Both |
| List stack | `requestHistoryList` | Both |
| Tree | `requestHistoryTree` | Both |
| Replay | `requestHistoryReplayButton` | Request mode only |
| Open | `requestHistoryOpenButton` | Unused in UI (hidden); global open is single-click on tree |

**Refresh:** On the right, `RightSidebar` reparents `refresh_button()` into the
flyout title bar. On the left, refresh stays in `globalHistoryHeader`.

### Shared behaviour

- `QTreeWidget` groups sends under local calendar days (Today, Yesterday, or a
  formatted date).
- `requestHistorySearch` filters by URL, request name, and method (substring) and
  by **exact** HTTP status when the term is all digits (e.g. `200`, `400` — `40`
  does not match `400`).
- **Date range** (funnel): inline popup with local-calendar From/To dates and
  presets; filters at query time via `executed_from` / `executed_to` on
  `list_for_sidebar` / `list_for_request`. Active filter shows a checked funnel
  and a summary tooltip.
- `refresh_requested` → `refresh()` reloads metadata.

### Per-request detail (right rail only)

- Detail tabs: Body, Headers, Request Headers, Request Body (from stored snapshot).
- Full payloads load on selection in **request** mode only.
- Row meta may include `(deleted)` or `(draft)` when `request_id` is null (see
  `was_persisted_request` in the service docs).

### Request mode (right rail)

- Active **saved** request tab only; draft tabs disable the rail icons with a tooltip
  (“save the request first”, or “original request was deleted” for tabs opened from
  deleted-request history).
- Empty copy: no sends yet for this request.
- **Replay** (detail header): HTTP from stored snapshot; updates centre response only.
- Context menu: **Replay this request**, **Delete item**.
- `replay_requested` / `delete_requested` → `MainWindow` handlers.
- After replay, `responseReplayIndicator` links back to this panel (`focus_entry`).

### Global mode (left rail)

- **List only** — no Body/Headers detail stack on the left (preview lives on the
  right History panel after **Open**).
- Lists all workspace sends (including draft-tab sends and orphaned rows after
  request delete). Default cap: 500 rows (search applies the same limit).
- Empty copy: no send history yet (with hint to send a request).
- **Open** on **single-click** of a send row (also context menu and **Enter**):
  emits `entry_open_requested(entry_id)` → `MainWindow._open_from_global_history`.
  - **Existing request** (`request_id` set and still in DB): open/focus request tab,
    open right History, select the send, then load detail asynchronously (loading bar).
    Centre response viewer is unchanged.
  - **Deleted / orphan / draft history row**: new draft tab prefilled from snapshot,
    stored response in viewer; right History and Saved Responses stay disabled (hover
    the greyed rail icons for why).
- No replay/delete on the global instance (use the right panel after navigating).

### Signals

| Signal | Parameters | Mode | Description |
|--------|------------|------|-------------|
| `refresh_requested` | *(none)* | Both | Reload list for current scope |
| `entry_open_requested` | `entry_id: int` | Global | Open send in editor + right History |
| `replay_requested` | `entry_id: int` | Request | Replay selected send |
| `delete_requested` | `entry_id: int` | Request | Delete selected send |
