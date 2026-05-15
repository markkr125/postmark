# Collections

Left sidebar containing the collection tree, header bar, and item
creation popup.

Source: `src/ui/collections/`

## CollectionWidget

Main sidebar container.

| Component | Description |
|-----------|-------------|
| `CollectionHeader` | Search input, New button, Import button |
| `CollectionTree` | Hierarchical tree with drag-drop |
| Loading bar | Shown during initial fetch |

Signals forwarded to MainWindow:

| Signal | Parameters | Description |
|--------|------------|-------------|
| `item_action_triggered` | `str, int, str` | Tree item opened or previewed |
| `item_name_changed` | `str, int, str` | Item renamed |
| `load_finished` | *(none)* | Background fetch completed |
| `draft_request_requested` | *(none)* | New draft tab opened |

### Loading Flow

1. `_start_fetch()` spawns a `_CollectionFetcher` worker thread
2. Worker calls `CollectionService.get_collection_tree()`
3. `_on_collections_ready(dict)` populates the tree widget

## CollectionHeader

Header bar above the tree.

| Widget | Action |
|--------|--------|
| Search input | Filters tree via `CollectionTree.filter_items(text)` |
| New (+) button | Opens `NewItemPopup` |
| Import button | Emits `import_requested` |

## NewItemPopup

Modal icon-grid dialog for creating items.

Two tiles:

| Tile | Signal |
|------|--------|
| HTTP Request | `new_request_clicked` |
| Collection | `new_collection_clicked` |

Tile hover updates a description label at the bottom.

## CollectionTree

Hierarchical tree widget built on `DraggableTreeWidget`.

### Data Roles

Stored on each `QTreeWidgetItem`:

| Role | Purpose |
|------|---------|
| `ROLE_ITEM_ID` | Database primary key |
| `ROLE_ITEM_TYPE` | "folder" or "request" |
| `ROLE_METHOD` | HTTP method (requests only) |
| `ROLE_PLACEHOLDER` | Marker for empty-folder placeholder |

### Key Methods

| Method | Description |
|--------|-------------|
| `set_collections(dict)` | Rebuild tree from nested `CollectionDict` |
| `add_request(dict, collection_id)` | Insert request row |
| `add_collection(dict, parent_id)` | Insert folder row |
| `start_rename_by_id(id, type)` | Trigger inline rename |
| `filter_items(text)` | Show/hide rows matching search |
| `select_item_by_id(id, type)` | Navigate to item |

### Context Menus (_TreeActionsMixin)

**Request context menu:** Open, Rename (F2), Delete

**Folder context menu:** Overview, Add request, Add folder, Expand all,
Collapse all, Rename, Delete

Keyboard shortcuts: F2 for rename, Delete key for delete.

### Drag-Drop (DraggableTreeWidget)

Requests can be dragged between folders.  Folders can be moved to a
new parent or to root level.

Validation rules:
- Cannot drop onto a request item
- Cannot drop a request at root level

Emits `request_moved(request_id, new_collection_id)` or
`collection_moved(collection_id, new_parent_id)`.

## CollectionTreeDelegate

Custom `QStyledItemDelegate` for painting method badges on request
rows.

```
+------+- - - - - - - - - -+
| GET  | My API Request     |
+------+- - - - - - - - - -+
```

Badge dimensions from `theme.py` constants: `BADGE_HEIGHT`,
`BADGE_BORDER_RADIUS`, `BADGE_MIN_WIDTH`.

Method colour from `method_color(method)`.

Request row labels use the normal palette text colour when selected (not
`HighlightedText`), so the name matches unselected tree text on the selection
tint. Folder rows rely on the same `QTreeWidget::item:selected` foreground in
global QSS.
