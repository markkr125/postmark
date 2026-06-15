# Signals Reference

Complete catalogue of all PySide6 `Signal` declarations grouped by
subsystem.  ~83 custom signals across the codebase.

## Collection Tree

### CollectionTree

Source: `ui/collections/tree/collection_tree.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `item_action_triggered` | `str, int, str` | Action type, item ID, value |
| `item_name_changed` | `str, int, str` | Item type, item ID, new name |
| `collection_rename_requested` | `int, str` | Collection ID, new name |
| `collection_delete_requested` | `int` | Collection ID |
| `request_rename_requested` | `int, str` | Request ID, new name |
| `script_rename_requested` | `int, str, str, str` | Local script ID, basename, language, module_format (`esm` \| `commonjs`) |
| `new_script_clicked` (popup) | `str, str` | Language code, module_format |
| `new_script_requested` (header) | `object, str, str` | Parent folder ID or `None`, language, module_format |
| `request_delete_requested` | `int` | Request ID |
| `request_duplicate_requested` | `int` | Request ID to clone |
| `request_moved` | `int, int` | Request ID, new collection ID |
| `collection_moved` | `int, object` | Collection ID, new parent ID (int or None) |
| `new_collection_requested` | `object` | Parent ID (int or None) |
| `new_request_requested` | `object` | Parent collection ID (int or None) |
| `selected_collection_changed` | `object` | Collection ID (int or None) |

### DraggableTreeWidget

Source: `ui/collections/tree/draggable_tree_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `request_moved` | `int, int` | Request ID, new collection ID |
| `collection_moved` | `int, object` | Collection ID, new parent ID |

## Collection Widget and Header

### CollectionWidget

Source: `ui/collections/collection_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `item_action_triggered` | `str, int, str` | Forwarded from CollectionTree |
| `item_name_changed` | `str, int, str` | Forwarded from CollectionTree |
| `load_finished` | *(none)* | Background fetch of collections completed |
| `draft_request_requested` | *(none)* | User opened a draft request |

### CollectionHeader

Source: `ui/collections/collection_header.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `new_collection_requested` | `object` | Parent ID (int or None) |
| `new_request_requested` | `object` | Parent collection ID (int or None) |
| `search_changed` | `str` | Search text changed |
| `import_requested` | *(none)* | Import button clicked |

### NewItemPopup

Source: `ui/collections/new_item_popup.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `new_request_clicked` | *(none)* | HTTP Request tile selected |
| `new_collection_clicked` | *(none)* | Collection tile selected |
| `hovered` (inner `_Tile`) | *(none)* | Mouse entered tile |

## Request Tab Deck

### RequestTabBar

Source: `ui/request/navigation/request_tabs/bar.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `currentChanged` | `int` | Current tab index changed |
| `tabCloseRequested` | `int` | Close button clicked on tab |
| `tab_close_requested` | `int` | Alias for tabCloseRequested |
| `tab_double_clicked` | `int` | Tab double-clicked |
| `new_tab_requested` | *(none)* | New blank tab requested |
| `close_others_requested` | `int` | Close all tabs except given index |
| `close_all_requested` | *(none)* | Close all tabs |
| `force_close_all_requested` | *(none)* | Force-close all tabs |
| `tab_reordered` | `int, int` | Tab indices swapped during drag |

### TabButton

Source: `ui/request/navigation/request_tabs/tab_button.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `clicked` | `int` | Tab selected |
| `close_requested` | `int` | Close button clicked |
| `double_clicked` | `int` | Tab double-clicked |
| `reorder_requested` | `int, int` | Drag-reorder source and dest |
| `context_requested` | `int, QPoint` | Right-click context menu |

## Request Editor

### RequestEditorWidget

Source: `ui/request/request_editor/editor_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `send_requested` | *(none)* | Send button clicked |
| `save_requested` | *(none)* | Ctrl+S pressed |
| `dirty_changed` | `bool` | Modified state changed |
| `request_changed` | `dict` | Any field modified (debounced 500ms) |

## Response Viewer

### ResponseViewerWidget

Source: `ui/request/response_viewer/viewer_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_response_requested` | `dict` | Save current response as example |
| `save_availability_changed` | `bool` | Response became saveable/unsaveable |

## Folder Editor

### FolderEditorWidget

Source: `ui/request/folder_editor/editor_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `collection_changed` | `dict` | Any field modified (debounced 800ms) |

## Breadcrumb Navigation

### BreadcrumbBar and _EditableLabel

Source: `ui/request/navigation/breadcrumb_bar.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `rename_requested` | `str` | Last segment renamed |
| `item_clicked` | `str, int` | Non-last segment clicked |
| `last_segment_renamed` | `str` | Final segment rename confirmed |

## Worker Threads

### HttpSendWorker

Source: `ui/request/http_worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Request completed (HttpResponseDict) |
| `error` | `str` | Request failed |

### SchemaFetchWorker

Source: `ui/request/http_worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Schema fetch completed (SchemaResultDict) |
| `error` | `str` | Fetch failed |

### SnippetGeneratorWorker

Source: `ui/request/http_worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Snippet generation completed |
| `error` | `str` | Generation failed |

## Environment Widgets

### EnvironmentSelector

Source: `ui/environments/environment_selector.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environment_changed` | `object` | Selection changed (int or None) |
| `manage_requested` | *(none)* | "Manage Environments" selected |

### EnvironmentSidebarPanel

Source: `ui/environments/environment_sidebar_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environment_changed` | `object` | Global active environment changed (`int` or `None`) |
| `manage_requested` | *(none)* | **Manage** clicked — opens or focuses the **Environments** tab in the main tab deck |

### EnvironmentEditorWidget

Source: `ui/environments/environment_editor.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environments_changed` | *(none)* | Environment created, renamed, deleted, or modified |

### EnvironmentEditorDialog

Source: `ui/environments/environment_editor.py`

Modal wrapper around `EnvironmentEditorWidget` (tests and legacy callers).

| Signal | Parameters | Description |
|--------|------------|-------------|
| `environments_changed` | *(none)* | Forwarded from the embedded widget |

## Right Sidebar

### RightSidebar

Source: `ui/sidebar/sidebar_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `ai_settings_requested` | *(none)* | Flyout title-bar gear clicked while the AI panel is open |
| `ai_new_chat_requested` | *(none)* | Flyout title-bar "New chat" clicked while the AI panel is open |
| `ai_session_history_requested` | *(none)* | Flyout title-bar session-history clock clicked while the AI panel is open |
| `ai_session_title_renamed` | `str` | User committed an inline rename of the active session title (Enter, Escape, or click-away) |

Wired in `MainWindow.__init__`: `ai_settings_requested` → `_on_open_ai_settings` (Settings **AI** category, then refresh chat model picker). `ai_new_chat_requested` / `ai_session_history_requested` / `ai_session_title_renamed` → `_AiChatControllerMixin` (`ai_chat_controller.py`).

### AiModelPickerPopup

Source: `ui/sidebar/ai/model_picker_popup.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `model_picked` | `str` | Model id selected from the picker list |
| `manage_requested` | *(none)* | Manage-models gear clicked in the picker search row |
| `effort_changed` | `str`, `str` | Model id and reasoning effort after Edit menu pick |

## AI Chat Panel

### AiChatPanel

Source: `ui/sidebar/ai/chat_panel/panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `message_submitted` | `str` | User sent a message (prompt text only; model/mode/attachments read from panel API) |
| `stop_requested` | *(none)* | User clicked Stop while a chat run is in flight |
| `assistant_fork_requested` | `int` | Fork chat from assistant message footer — message id to branch at |
| `mode_changed` | `str` | Agent mode changed (`agent`, `ask`, or `plan`) — not consumed yet |
| `attachments_changed` | `list` | Attached file paths changed — not consumed yet |
| `manage_models_requested` | *(none)* | Manage-models gear in the model picker → opens Settings → AI → Models |
| `context_requested` | *(none)* | Context ring clicked — toggles ``AiChatContextUsagePopup`` |

Public getters (not signals): `current_model_id()`, `current_model_entry()`, `current_mode()`, `current_reasoning_effort()`, `current_run_context_tokens()`, `current_thinking_enabled()`, `streaming_assistant_thinking()`, `streaming_assistant_text()`. Context usage: `set_context_breakdown`, `refresh_context_usage`, `set_context_session_id`, `on_context_compacted`. ``ContextUsageBreakdown`` may include ``is_estimated``, ``transcript_larger_than_sdk``, and diagnostic fields from ``context_usage_sdk``; the popup shows honesty hints when usage ≥70%. Streaming API: `load_transcript`, `begin_assistant_stream` (shows ``aiChatActivityRow`` with spinner + ``Thinking…``), `append_assistant_chunk(thinking_delta, content_delta)` (hides activity on first token), `set_activity_status(raw)` (SDK status while activity visible), `end_assistant_stream(content, thinking=…)` (always clears activity), `apply_assistant_final(content, thinking=…)`, `set_run_busy`, `set_send_enabled` (idle only). Worker signals: `chunk_received`, `status_changed`, `assistant_finished`, `failed`, `usage_updated`, `context_compacted` — connect to ``AiChatPanel.deliver_assistant_chunk`` / ``deliver_activity_status`` and ``MainWindow`` ``_deliver_*`` handlers with **QueuedConnection**. ``usage_updated`` carries post-run SDK metrics; ``context_compacted`` fires on OpenHands ``Condensation`` events. ``status_changed`` must emit **Summarizing earlier messages…** during compaction. Streaming markdown uses ``StreamingMarkdownCache`` with ``StreamingTableRenderer`` so GFM pipe tables render incrementally during an open stream (header, committed rows, one muted provisional tail row) with cached inline markdown in cells (bold, italic, code, links, strikethrough); ``end_assistant_stream`` still upgrades to full Qt markdown for final fidelity. Off-thread callbacks re-emit through internal queued signals (``_assistant_chunk_delivery_requested``, ``_context_usage_metrics_delivery_requested``, ``_context_usage_schedule_requested``, ``_ai_assistant_finish_requested``, etc.). User messages use a full-width ``aiChatMessageUser`` bubble; assistant replies render markdown in ``aiChatAssistantText`` with optional ``aiChatThoughtBlock`` (`Thought for Ns`).

Wired via `_AiChatControllerMixin._init_ai_chat_controller`: `message_submitted` → `_on_ai_message_submitted` (starts `AiChatWorker`, streams reply); `stop_requested` → `_on_ai_chat_stop` (`AiChatWorker.cancel` → `Conversation.interrupt`); `assistant_fork_requested` → `_on_assistant_fork_requested` (`AiChatSessionService.fork_session_at_message` + session switch); `manage_models_requested` → `_on_open_ai_models_settings`. Connect ``usage_updated`` to ``AiChatPanel.deliver_context_usage_metrics`` (stashes per-turn SDK metrics for ``record_assistant_message``) and ``context_compacted`` refresh to ``deliver_context_usage_refresh`` (not lambdas). Completed assistant rows show ``aiChatAssistantMessageFooter`` (model/cost + ⋯ menu with Fork chat / Copy message). Worker/thread cleanup uses generation-guarded ``_release_*_thread`` handlers. `AiChatWorker.failed(str, str)` carries `(error, partial_assistant_text)`; the controller persists the full streamed text plus a `---` footer on failure.

## Saved Responses Panel

### SavedResponsesPanel

Source: `ui/sidebar/saved_responses/panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `save_current_requested` | *(none)* | "Save Current" clicked |
| `refresh_requested` | *(none)* | Refresh clicked |
| `rename_requested` | `int` | Rename clicked (response ID) |
| `duplicate_requested` | `int` | Duplicate clicked (response ID) |
| `delete_requested` | `int` | Delete clicked (response ID) |

## Auth Widgets

### OAuth2Page

Source: `ui/request/auth/oauth2_page.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `field_changed` | *(none)* | Any OAuth field changed |
| `get_token_requested` | *(none)* | "Get New Access Token" clicked |

## Dialogs

### ImportDialog (_ImportWorker)

Source: `ui/dialogs/import_dialog.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `finished` | `dict` | Import completed (ImportSummary) |
| `error` | `str` | Import failed |
| `files_dropped` (`_DropZone`) | `list` | Files drag-dropped onto zone |

### `_RunnerPanel` (folder inline runner)

Source: `ui/request/folder_editor/runner_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `run_finished` | *(none)* | Run completed, cancelled, or errored (host refreshes history) |

### `RunnerWorker` (collection batch)

Source: `ui/dialogs/collection_runner/worker.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `progress` | `int, dict` | Request completed (index, result) |
| `finished` | `list` | All requests completed |
| `error` | `str` | Fatal error |

## Shared Widgets

### CodeEditorWidget

Source: `ui/widgets/code_editor/editor_widget.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `cursor_position_changed` | `int, int` | 1-based line and column of the cursor |
| `validation_changed` | `list` | Validation errors changed |

### KeyValueTableWidget

Source: `ui/widgets/key_value_table.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `data_changed` | *(none)* | Grid cell/checkbox changed, or bulk text applied back to the grid |

Bulk serialize/parse: `ui/widgets/key_value_bulk.py`

### ClickableLabel (in InfoPopup)

Source: `ui/widgets/info_popup.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `clicked` | *(none)* | Label clicked |

## Theme and Settings

### ThemeManager

Source: `ui/styling/theme_manager.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `theme_changed` | *(none)* | Theme switched |

### TabSettingsManager

Source: `ui/styling/tab_settings_manager.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `settings_changed` | *(none)* | Any tab setting changed |

## Panels

### ConsolePanel (_LogSignalBridge)

Source: `ui/panels/console_panel.py`

| Signal | Parameters | Description |
|--------|------------|-------------|
| `log_message` | `str` | New log message received |

## Signal Patterns

**Worker threads** use a consistent `finished`/`error` pair.  The
`finished` signal carries a typed dict payload, while `error` carries
a plain string message.

**Debounced change signals** prevent excessive updates: `request_changed`
fires 500ms after the last edit, `collection_changed` fires after 800ms.

**Signal forwarding** is used in composite widgets.  `CollectionWidget`
re-emits `CollectionTree` signals so that `MainWindow` only connects to
the top-level widget.

**`object` parameter type** is used when the value is a union such as
`int | None`, since PySide6 `Signal` does not support `Union` types
directly.
