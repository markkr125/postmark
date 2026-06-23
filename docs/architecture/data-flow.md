# Data Flow

Sequence diagrams for the most important operations.  These
diagrams show the full call chain from user action through all layers to
the database and back.

## 1. Send HTTP Request

User clicks the Send button on a request tab.

```text
User clicks Send
  --> RequestEditor emits send_requested signal
    --> MainWindow._on_send()
      1. Collect request data from active tab (method, URL, headers, body, auth)
      2. Substitute {{variables}} via EnvironmentService.substitute()
      3. Apply auth via apply_auth(auth_dict, url, headers)
      4. Create HttpSendWorker with resolved request data
      5. Move worker to QThread, connect signals
      6. Start thread
         --> HttpSendWorker.run()  [background thread]
           --> HttpService.send_request(method, url, headers, body)
             --> httpx.Client.request()
             <-- httpx.Response
           <-- HttpResponseDict (status, headers, body, timing, network, sizes)
         <-- worker.finished signal(HttpResponseDict)
      7. MainWindow._on_response_received(response_dict)
         --> ResponseViewer.display_response(response_dict)
         --> Console logs the request/response
```

## 2. Open Request from Collection Tree

User clicks a request item in the collection sidebar.

```text
User clicks request item in CollectionTree
  --> CollectionTree emits item_action_triggered("request", request_id, name)
    --> MainWindow._on_item_action("request", request_id, name)
      --> _TabControllerMixin._open_request(request_id)
        1. Check if request is already open in a tab
           --> if yes, switch to that tab and return
        2. Check preview mode / tab limit settings
        3. Load request from database:
           --> CollectionService.get_request(request_id)
             --> get_request_by_id(request_id)
               --> get_session()
               --> session.get(RequestModel, request_id)
             <-- RequestModel (detached)
           <-- RequestModel
        4. Build RequestLoadDict from model attributes
        5. Load auth chain:
           --> CollectionService.get_request_auth_chain(request_id)
        6. Load variable chain:
           --> EnvironmentService.build_combined_variable_detail_map(env_id, request_id)
        7. Create new tab (or reuse preview tab):
           --> TabManager.add_tab() or reuse existing
           --> RequestEditor.load_request(RequestLoadDict)
           --> BreadcrumbBar.set_breadcrumb(crumbs)
        8. Update sidebar panels for the new tab
```

## 3. Import Collection

User imports a Postman collection file via the Import dialog.

```text
User opens Import dialog, selects files, clicks Import
  --> ImportDialog starts ImportWorker on QThread
    --> ImportWorker.run()  [background thread]
      --> ImportService.import_files([path1, path2, ...])
        For each file:
          1. Read and parse JSON
          2. Detect type via detect_postman_type(data)
          3. Route to appropriate parser:
             --> parse_collection_file(path)
               --> Recursively parse folders and requests
               --> Build ParsedCollection with ParsedFolders and ParsedRequests
             --> or parse_environment_file(path)
               --> Build ParsedEnvironment
          4. Persist parsed data:
             --> import_collection_tree(parsed_collection)
               --> get_session()
               --> Create CollectionModel (root)
               --> Recursively create child CollectionModels (folders)
               --> Create RequestModels for each request
               --> Create SavedResponseModels for saved examples
               --> Commit all in one transaction
             <-- dict mapping parsed names to database IDs
          5. Accumulate ImportSummary counts
        <-- ImportSummary
      <-- ImportWorker.finished signal(ImportSummary)
    --> ImportDialog shows results
    --> ImportDialog emits import_completed signal
  --> MainWindow refreshes the collection tree
```

## 4. Variable Substitution Chain

How `{{variables}}` are resolved when sending a request.

```text
EnvironmentService.build_combined_variable_detail_map(env_id, request_id)

  1. Start with environment variables (lowest priority):
     --> get_environment_by_id(env_id)
     --> Extract key-value pairs from EnvironmentModel.values JSON
     --> Each var: source="environment", source_id=env_id

  2. Walk the collection ancestor chain (overrides environment):
     --> get_request_variable_chain_detailed(request_id)
       --> Find request's collection
       --> Walk parent_id chain to root
       --> Merge variables from each level (child overrides parent)
     --> Each var: source="collection", source_id=collection_id

  3. Apply local overrides from TabContext (highest priority):
     --> TabContext.local_overrides dict
     --> Each var: source="local", source_id=0, is_local=True

  Resolution order (last wins):
    environment vars  <  collection ancestor chain  <  local overrides

  Result: dict[str, VariableDetail]
    {
      "base_url": VariableDetail(value="https://api.example.com",
                                  source="environment", source_id=1),
      "token":    VariableDetail(value="abc123",
                                  source="local", source_id=0, is_local=True),
    }

  At send time:
    EnvironmentService.substitute(url, flat_var_map)
      --> re.sub(r"\{\{(.+?)\}\}", replacement, url)
      --> "https://{{base_url}}/users" becomes "https://api.example.com/users"
```

## 5. Tab Session Save and Restore

How open tabs persist across application restarts.

```text
On application close (MainWindow.closeEvent):
  --> _TabControllerMixin._save_session()
    For each open tab in self._tabs:
      1. Serialize TabContext to dict:
         - tab_type, request_id, collection_id
         - is_dirty, draft_name, local_overrides
         - Editor state (body, method, URL, headers, etc.) for dirty/draft tabs
      2. Record active tab index
    --> QSettings.setValue("session/tabs", serialized_list)
    --> QSettings.setValue("session/active", active_index)

On application start (after MainWindow.__init__):
  --> _TabControllerMixin._restore_session()
    1. Read QSettings("session/tabs") and QSettings("session/active")
    2. For each serialized tab:
       - Store as deferred tab (self._deferred_tabs[index] = dict)
       - Create tab bar entry with name/icon only (no widgets yet)
    3. Activate the previously active tab:
       - Only the active tab materialises immediately
       - Other tabs materialise lazily on first switch (deferred loading)
    4. Deferred tab materialisation (_materialise_deferred_tab):
       - Create RequestEditor + ResponseViewer widgets
       - Load request data from DB (or restore draft state from dict)
       - Wire signals
```

## 6. Draft Tab Lifecycle

How unsaved "draft" requests work.

```text
User clicks New Request (or Ctrl+N)
  --> _DraftControllerMixin._open_draft_tab()
    1. Create new TabContext with:
       - tab_type="request", request_id=None
       - draft_name="Untitled Request"
    2. Create RequestEditor + ResponseViewer widgets
    3. Add tab to tab bar with draft_name as label
    4. Focus the new tab

User edits the request (method, URL, body, etc.)
  --> Tab shows "unsaved" indicator (dirty_changed signal)

User clicks Save (or Ctrl+S)
  --> _DraftControllerMixin._save_draft()
    1. Show SaveRequestDialog -- user picks target collection
    2. CollectionService.create_request(collection_id, method, url, name, ...)
       <-- RequestModel with new ID
    3. Update TabContext: request_id = new_id, draft_name = None
    4. Update tab bar label to show saved name
    5. Update breadcrumb bar
    6. Refresh collection tree to show new request
```

## Script Execution Flow

```text
User clicks Send (with scripts)
  --> _SendPipelineMixin._on_send()
    1. Resolve variables (EnvironmentService)
    2. ScriptService.build_script_chain(request_id)
       <-- (pre_chain, test_chain)
    3. HttpSendWorker.run() [QThread]
       a. load_globals() from data/globals.json
       b. ScriptEngine.run_pre_request_scripts(pre_chain, context)
          <-- ScriptOutput (mutations, variable changes, global changes, console)
       c. save_globals() if global_variable_changes present
       d. apply_request_mutations() -- URL, method, headers, body
       e. HttpService.send_request()
          <-- HttpResponseDict
       f. ScriptEngine.run_test_scripts(test_chain, context)
          <-- ScriptOutput (test results, console, variable/global changes)
       g. save_globals() if global_variable_changes present
       h. Merge outputs into response dict
    <-- finished signal(dict)
  --> ResponseViewer.display_response() + load_test_results()
  --> ConsolePanel.append_message() for each console log
  --> Apply variable_changes to local_overrides
```
