"""Global QSS builder — extracted from ThemeManager.

Contains the single build_global_qss function that builds the
application-wide Qt Style Sheet string from a ThemePalette.
"""

from __future__ import annotations

from ui.styling.theme import (BADGE_BORDER_RADIUS, BADGE_FONT_SIZE,
                              BADGE_HEIGHT, BADGE_MIN_WIDTH, DARK_PALETTE,
                              LIGHT_PALETTE, TREE_ROW_HEIGHT, ThemePalette)


def build_global_qss(p: ThemePalette) -> str:
    """Return the global stylesheet string for the entire application."""
    return f"""
    /* ---- Global resets ------------------------------------------ */
    QMainWindow, QDialog {{
        background: {p["bg"]};
        color: {p["text"]};
    }}

    /* ---- Splitters ---------------------------------------------- */
    QSplitter::handle {{
        background: {p["bg"]};
    }}
    QSplitter::handle:horizontal {{
        width: 5px;
        border-left: none;
        border-right: 1px solid {p["border"]};
    }}
    QSplitter[objectName="gqlSplitter"]::handle:horizontal {{
        border-right: none;
    }}
    QSplitter::handle:vertical {{
        height: 4px;
        background: transparent;
        border-bottom: 1px solid {p["border"]};
        margin-top: 0px;
        margin-bottom: 3px;
    }}
    QSplitter[objectName="scriptEditorOutputSplitter"]::handle:vertical {{
        height: 4px;
        background: transparent;
        border: none;
        margin-top: 0px;
        margin-bottom: 0px;
    }}
    QFrame#scriptSplitFullWidthLine {{
        background-color: {p["border"]};
        border: none;
        min-height: 1px;
        max-height: 1px;
    }}

    /* ---- Labels ------------------------------------------------- */
    QLabel {{
        color: {p["text"]};
    }}
    QLabel[objectName="mutedLabel"] {{
        color: {p["text_muted"]};
        font-size: 11px;
    }}
    QLabel[objectName="emptyStateLabel"] {{
        color: {p["text_muted"]};
        font-style: italic;
        font-size: 13px;
    }}
    QLabel[objectName="titleLabel"] {{
        font-size: 14px;
        font-weight: bold;
        color: {p["text"]};
    }}
    QLabel[objectName="sectionLabel"] {{
        color: {p["text"]};
        font-size: 12px;
    }}
    QLabel[objectName="panelTitle"] {{
        font-weight: bold;
        font-size: 12px;
        color: {p["text"]};
        padding: 8px;
    }}

    QLabel#savedResponseStatusBadge {{
        margin-top: 6px;
    }}

    /* ---- Inputs ------------------------------------------------- */
    QLineEdit, QComboBox {{
        background: {p["input_bg"]};
        border: 1px solid {p["border"]};
        padding: 6px 10px;
        color: {p["text"]};
        border-radius: 4px;
    }}
    QLineEdit:focus, QComboBox:focus {{
        border-color: {p["accent"]};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 4px solid {p["text_muted"]};
        margin-right: 8px;
    }}

    /* ---- Text editors ------------------------------------------- */
    QTextEdit {{
        background: {p["input_bg"]};
        border: 1px solid {p["border"]};
        color: {p["text"]};
        font-size: 12px;
    }}
    QTextEdit[objectName="monoEdit"] {{
        font-family: monospace;
    }}
    QTextEdit[objectName="consoleOutput"] {{
        background: {p["console_bg"]};
        color: {p["console_text"]};
        font-family: monospace;
        font-size: 11px;
        border: none;
    }}

    /* ---- Plain text code editors -------------------------------- */
    QPlainTextEdit[objectName="codeEditor"] {{
        background: {p["input_bg"]};
        border: 1px solid {p["border"]};
        color: {p["text"]};
        font-family: monospace;
        font-size: 12px;
    }}

    /* Read-only inherited-script preview: light paper even in a dark app */
    QPlainTextEdit[objectName="codeEditorInheritedRead"] {{
        background: {LIGHT_PALETTE["input_bg"] if p is DARK_PALETTE else p["input_bg"]};
        border: 1px solid {p["border"]};
        color: {LIGHT_PALETTE["text"] if p is DARK_PALETTE else p["text"]};
        font-family: monospace;
        font-size: 12px;
    }}

    /* ---- Buttons ------------------------------------------------ */
    QPushButton[objectName="primaryButton"] {{
        background: {p["accent"]};
        color: {p["bg"]};
        border: none;
        padding: 6px 20px;
        font-weight: bold;
        border-radius: 4px;
    }}
    QPushButton[objectName="primaryButton"]:hover {{
        opacity: 0.85;
    }}
    QPushButton[objectName="primaryButton"]:disabled {{
        background: {p["bg_alt"]};
        color: {p["text_muted"]};
    }}
    QPushButton[objectName="dangerButton"] {{
        background: {p["danger"]};
        color: {p["bg"]};
        border: none;
        padding: 6px 20px;
        font-weight: bold;
        border-radius: 4px;
    }}
    QPushButton[objectName="dangerButton"]:hover {{
        opacity: 0.85;
    }}
    QPushButton[objectName="dangerButton"]:disabled {{
        background: {p["bg_alt"]};
        color: {p["text_muted"]};
    }}
    QPushButton[objectName="smallPrimaryButton"] {{
        background: {p["accent"]};
        color: {p["bg"]};
        border: none;
        padding: 4px 12px;
        font-size: 11px;
        border-radius: 4px;
    }}
    QPushButton[objectName="outlineButton"] {{
        border: 1px solid {p["border"]};
        padding: 4px 12px;
        font-size: 11px;
        border-radius: 4px;
        background: transparent;
        color: {p["text"]};
    }}
    QPushButton[objectName="outlineButton"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
    }}
    QPushButton[objectName="saveButton"] {{
        border: 1px solid {p["accent"]};
        padding: 4px 12px;
        font-size: 11px;
        border-radius: 4px;
        background: transparent;
        color: {p["accent"]};
    }}
    QPushButton[objectName="saveButton"]:hover {{
        background: {"rgba(52,152,219,0.12)" if p is DARK_PALETTE else "rgba(52,152,219,0.08)"};
    }}
    QPushButton[objectName="saveButton"]:disabled {{
        border-color: {p["border"]};
        color: {p["text_muted"]};
    }}
    QPushButton[objectName="iconButton"] {{
        border: 1px solid {p["border"]};
        padding: 0px;
        border-radius: 4px;
        background: transparent;
        color: {p["text"]};
    }}
    QPushButton[objectName="iconButton"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
    }}
    QPushButton[objectName="iconButton"]:checked {{
        background: {"rgba(255,255,255,0.12)" if p is DARK_PALETTE else "rgba(0,0,0,0.10)"};
        border-color: {p["accent"]};
    }}
    QPushButton[objectName="iconDangerButton"] {{
        border: 1px solid {p["border"]};
        padding: 0px;
        border-radius: 4px;
        background: transparent;
        color: {p["text_muted"]};
    }}
    QPushButton[objectName="iconDangerButton"]:hover {{
        background: {"rgba(244,71,71,0.12)" if p is DARK_PALETTE else "rgba(231,76,60,0.10)"};
        color: {p["danger"]};
        border-color: {p["danger"]};
    }}
    QPushButton[objectName="linkButton"] {{
        color: {p["accent"]};
        border: none;
        font-size: 11px;
        padding: 8px;
        background: transparent;
    }}
    QPushButton[objectName="flatAccentButton"] {{
        padding: 4px 12px;
        font-size: 12px;
        font-weight: 500;
        color: {p["accent"]};
        border: none;
        background: transparent;
        border-radius: 4px;
    }}
    QPushButton[objectName="flatAccentButton"]:hover {{
        background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.04)"};
    }}
    QPushButton[objectName="flatMutedButton"] {{
        padding: 4px 12px;
        font-size: 12px;
        font-weight: 500;
        color: {p["text_muted"]};
        border: none;
        background: transparent;
        border-radius: 4px;
    }}
    QPushButton[objectName="flatMutedButton"]:hover {{
        background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.04)"};
        color: {p["text"]};
    }}
    QPushButton[objectName="rowDeleteButton"] {{
        border: none;
        background: transparent;
        color: {p["text_muted"]};
        font-size: 14px;
        font-weight: bold;
        padding: 0;
    }}
    QPushButton[objectName="rowDeleteButton"]:hover {{
        color: {p["danger"]};
    }}
    QPushButton[objectName="importLinkButton"] {{
        color: {p["accent"]};
        text-decoration: underline;
        border: none;
        font-weight: bold;
        background: transparent;
    }}
    QPushButton[objectName="dismissButton"] {{
        padding: 6px 20px;
        border: 1px solid {p["border"]};
        border-radius: 4px;
        background: {p["bg_alt"]};
        font-weight: bold;
        color: {p["text"]};
    }}
    QPushButton[objectName="dismissButton"]:hover {{
        background: {p["border"]};
    }}

    /* ---- Status bar --------------------------------------------- */
    QStatusBar#appStatusBar {{
        background: {p["bg_alt"]};
        border-top: 1px solid {p["border"]};
        min-height: 24px;
        padding: 0px;
    }}
    QStatusBar#appStatusBar::item {{
        border: none;
    }}
    QPushButton[objectName="statusBarButton"] {{
        border: none;
        background: transparent;
        padding: 0px 6px;
        margin: 0px;
        color: {p["text_muted"]};
        border-radius: 3px;
    }}
    QPushButton[objectName="statusBarButton"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
        color: {p["text"]};
    }}

    /* ---- Tab bars (underline style) ----------------------------- */
    QTabWidget::pane {{
        border: none;
        background: {p["bg"]};
        border-radius: 0px;
    }}
    QTabWidget > QTabBar::tab {{
        padding: 8px 16px;
        color: {p["text_muted"]};
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 500;
    }}
    QTabWidget > QTabBar::tab:hover {{
        color: {p["text"]};
        background: {p["bg_alt"]};
    }}
    QTabWidget > QTabBar::tab:selected {{
        color: {p["accent"]};
        border-bottom: 2px solid {p["accent"]};
    }}
    QTabWidget#scriptSubTabs::pane {{
        border-top: 1px solid {p["border"]};
    }}
    QTabWidget#scriptSubTabs > QTabBar {{
        background: {p["bg_alt"]};
    }}
    QFrame#scriptSubTabsSep {{
        background: {p["border"]};
        border: none;
    }}
    QTabWidget#scriptOutputTabs::pane {{
        border-top: 1px solid {p["border"]};
        padding: 6px 0 0 0;
        margin: 0px;
    }}
    QTabWidget#scriptOutputTabs > QTabBar {{
        background: {p["bg_alt"]};
    }}
    QListWidget[objectName="scriptLspProblemsList"],
    QFrame[objectName="scriptLspProblemsEmptyFrame"] {{
        border: 1px solid {p["border"]};
        background: {p["input_bg"]};
        outline: none;
    }}
    QListWidget[objectName="scriptLspProblemsList"]::item {{
        padding: 4px 8px;
        font-family: monospace;
        font-size: 11px;
    }}
    /* Tab overflow scroll buttons — input_bg box, 1px border,
       sharp corners, accent border on hover.  Keep for all QTabBars. */
    QTabBar QToolButton {{
        background: {p["input_bg"]};
        border: 1px solid {p["border"]};
        border-radius: 0px;
    }}
    QTabBar QToolButton:hover {{
        border-color: {p["accent"]};
    }}

    /* ---- Progress bars ------------------------------------------ */
    QProgressBar {{
        border: none;
        background: transparent;
    }}
    QProgressBar::chunk {{
        background: {p["accent"]};
    }}

    /* ---- Table widgets ------------------------------------------ */
    QTableWidget {{
        background: {p["input_bg"]};
        border: 1px solid {p["border"]};
        gridline-color: {"rgba(0,0,0,0.05)" if p is LIGHT_PALETTE else "rgba(255,255,255,0.05)"};
        color: {p["text"]};
        border-radius: 4px;
    }}
    QHeaderView::section {{
        background: {p["bg_alt"]};
        border: none;
        border-bottom: 1px solid {p["border"]};
        border-right: 1px solid {"rgba(0,0,0,0.05)" if p is LIGHT_PALETTE else "rgba(255,255,255,0.05)"};
        padding: 6px 8px;
        font-size: 12px;
        font-weight: 500;
        color: {p["text_muted"]};
    }}

    /* ---- List widgets ------------------------------------------- */
    QListWidget {{
        border: 1px solid {p["border"]};
        background: {p["input_bg"]};
    }}
    QListWidget[objectName="versionList"] {{
        border: none;
        border-top: 1px solid {p["border"]};
        outline: none;
    }}
    QListWidget[objectName="versionList"]::item {{
        padding: 4px 8px;
    }}
    QListWidget[objectName="versionList"]::item:selected {{
        background: {p["selected_bg"]};
    }}
    QListWidget[objectName="versionList"]::item:hover:!selected {{
        background: {p["hover_tree_bg"]};
    }}

    /* ---- Version history dialog --------------------------------- */
    QTabWidget#versionTabs::pane {{
        border-bottom: 1px solid {p["border"]};
    }}
    QWidget[objectName="diffToolbar"] {{
        background: {p["bg_alt"]};
        border-bottom: 1px solid {p["border"]};
    }}
    QLabel[objectName="diffColumnHeader"] {{
        background: {p["diff_header_bg"]};
        color: {p["text_muted"]};
        font-size: 11px;
        padding: 2px 8px;
        border-top: 1px solid {p["border"]};
        border-bottom: 1px solid {p["border"]};
    }}
    QLineEdit[objectName="versionSearch"] {{
        border: 1px solid {p["border"]};
        border-radius: 3px;
        padding: 3px 6px;
    }}

    /* ---- Scroll bars (app-wide) -----------------------------------
       Full rules for every sub-control so the style does not fall back
       to faint platform defaults. Handle has a 1px border for contrast. */
    QScrollBar:vertical {{
        background: {p["bg_alt"]};
        width: 12px;
        margin: 0px;
        border: none;
    }}
    QScrollBar:horizontal {{
        background: {p["bg_alt"]};
        height: 12px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {p["muted"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
        min-height: 28px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p["text_muted"]};
        border-color: {p["text_muted"]};
    }}
    QScrollBar::handle:vertical:pressed {{
        background: {p["text_muted"]};
    }}
    QScrollBar::handle:horizontal {{
        background: {p["muted"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
        min-width: 28px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {p["text_muted"]};
        border-color: {p["text_muted"]};
    }}
    QScrollBar::handle:horizontal:pressed {{
        background: {p["text_muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        width: 0px;
        border: none;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
        height: 0px;
        border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
    QAbstractScrollArea::corner {{
        background: {p["bg_alt"]};
    }}

    /* ---- Scroll areas ------------------------------------------- */
    QScrollArea {{
        border: none;
    }}
    /* Script editor output — match codeEditor (input surface + border) */
    QScrollArea[objectName="scriptOutputScroll"] {{
        border: 1px solid {p["border"]};
        background-color: {p["input_bg"]};
    }}
    QWidget[objectName="scriptOutputSection"],
    QWidget[objectName="scriptMockResponseSection"] {{
        border-bottom: 1px solid {p["border"]};
    }}
    QWidget[objectName="scriptOutputInner"] {{
        background-color: {p["input_bg"]};
    }}

    /* ---- Tree widgets ------------------------------------------- */
    QTreeWidget::item {{
        height: {TREE_ROW_HEIGHT}px;
        padding: 0px 0px;
    }}
    QTreeWidget::item:hover {{
        background-color: {p["hover_tree_bg"]};
    }}
    QTreeWidget::item:selected {{
        background-color: {p["selected_bg"]};
    }}

    /* ---- Request tab bar ---------------------------------------- */
    RequestTabBar {{
        border-bottom: 1px solid {p["border"]};
        background: {p["bg_alt"]};
    }}
    RequestTabBar::tab {{
        height: 34px;
        max-width: 200px;
        padding: 0 16px;
        border: none;
        border-right: 1px solid {p["border"]};
        background: {p["bg_alt"]};
        color: {p["text_muted"]};
    }}
    RequestTabBar::tab:selected {{
        background: {p["bg"]};
        color: {p["text"]};
        border-top: 2px solid {p["accent"]};
        border-bottom: none;
    }}
    RequestTabBar::tab:hover:!selected {{
        background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.04)"};
    }}
    RequestTabBar::close-button {{
        subcontrol-position: right;
        margin: 4px;
        padding: 2px;
        width: 12px;
        height: 12px;
    }}

    /* ---- Menus -------------------------------------------------- */
    QMenu {{
        background: {p["bg"]};
        border: 1px solid {p["border"]};
        color: {p["text"]};
    }}
    QMenu::item {{
        padding: 4px 12px;
    }}
    QMenu::item:selected:enabled {{
        background-color: {p["accent"]};
        color: {p["bg"]};
    }}

    /* ---- Toolbar buttons ---------------------------------------- */
    QToolButton {{
        background: {p["bg"]};
    }}
    QToolButton[objectName="scriptLanguageLinkButton"] {{
        background: transparent;
        border: none;
        color: {p["accent"]};
        font-size: 12px;
        font-weight: normal;
        /* top, right, bottom, left — extra right room so label and menu arrow are not cramped */
        padding: 0px 18px 0px 6px;
        text-decoration: underline;
    }}
    QToolButton[objectName="scriptLanguageLinkButton"]::menu-indicator {{
        width: 12px;
        height: 12px;
        subcontrol-position: right center;
        subcontrol-origin: padding;
        right: 4px;
    }}
    QToolButton[objectName="scriptLanguageLinkButton"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
    }}
    QToolButton[objectName="scriptHistoryLinkButton"] {{
        background: transparent;
        border: none;
        color: {p["accent"]};
        font-size: 12px;
        font-weight: normal;
        padding: 0px 6px;
        text-decoration: underline;
    }}
    QToolButton[objectName="scriptHistoryLinkButton"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
    }}

    /* ---- Sidebar flat buttons ----------------------------------- */
    QToolButton[objectName="sidebarToolButton"] {{
        background: transparent;
        border: none;
        color: {p["accent"]};
        font-size: 12px;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 4px;
    }}
    QToolButton[objectName="sidebarToolButton"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
    }}

    /* ---- Sidebar section label ---------------------------------- */
    QLabel[objectName="sidebarSectionLabel"] {{
        font-weight: bold;
        font-size: 13px;
        color: {p["text"]};
    }}

    /* ---- Badge (method badge in tree + tabs) -------------------- */
    QLabel[objectName="methodBadge"] {{
        font-size: {BADGE_FONT_SIZE}px;
        font-weight: bold;
        font-family: monospace;
        border-radius: {BADGE_BORDER_RADIUS}px;
        min-width: {BADGE_MIN_WIDTH}px;
        max-width: {BADGE_MIN_WIDTH}px;
        min-height: {BADGE_HEIGHT}px;
        max-height: {BADGE_HEIGHT}px;
    }}

    /* ---- Import dialog drop zone ------------------------------- */
    _DropZone {{
        background: {p["drop_zone_bg"]};
        border: 2px dashed {p["drop_zone_border"]};
        border-radius: 8px;
    }}

    /* ---- Import dialog tab widget (box-style tabs) -------------- */
    QTabWidget[objectName="importTabs"]::pane {{
        border: 1px solid {p["border"]};
        border-top: none;
    }}
    QTabWidget[objectName="importTabs"] > QTabBar::tab {{
        padding: 6px 16px;
        border: 1px solid {p["border"]};
        border-bottom: none;
        background: {p["bg_alt"]};
    }}
    QTabWidget[objectName="importTabs"] > QTabBar::tab:selected {{
        background: {p["bg"]};
        font-weight: bold;
        border-bottom: none;
    }}

    /* ---- Info popup (response breakdowns) ----------------------- */
    QFrame[objectName="infoPopup"] {{
        background: {p["bg"]};
        border: 1px solid {p["border"]};
    }}
    QLabel[objectName="infoPopupTitle"] {{
        font-weight: bold;
        font-size: 12px;
        color: {p["text"]};
        padding: 0px;
    }}
    QLabel[objectName="infoPopupSeparator"] {{
        background: {p["border"]};
        max-height: 1px;
        min-height: 1px;
    }}
    QTreeWidget#debugHoverValueTree {{
        border: none;
        background: {p["input_bg"]};
    }}
    QTreeWidget#debugHoverValueTree::item:selected {{
        background: {p["selected_bg"]};
    }}
    QTreeWidget#debugVariablesTree {{
        border: none;
        background: {p["input_bg"]};
    }}
    /* Section titles use bold ``setFont`` on top-level items (see ``debug_panel._add_section``). */
    QTreeWidget#debugVariablesTree::item:selected {{
        background: {p["selected_bg"]};
    }}
    /* Foreground inherits the tree viewport palette (sharper than forcing ``color`` here). */
    QTreeWidget#debugVariablesTree QLabel#debugTreeCellLabel,
    QTreeWidget#debugHoverValueTree QLabel#debugTreeCellLabel {{
        background: transparent;
        border: none;
        padding: 0px;
        margin: 0px;
    }}

    /* ---- Variable popup (hover tooltip for {{variables}}) ------- */
    QFrame[objectName="variablePopup"] {{
        background: {p["bg"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
    }}
    QLabel[objectName="variablePopupName"] {{
        font-weight: bold;
        font-size: 12px;
        color: {p["warning"]};
        padding: 0px;
    }}
    QLineEdit[objectName="variablePopupValue"] {{
        background: {p["input_bg"]};
        border: 1px solid {p["border"]};
        border-radius: 3px;
        padding: 3px 6px;
        font-size: 12px;
        color: {p["text"]};
    }}
    QLabel[objectName="variablePopupBadge"] {{
        font-size: 10px;
        font-weight: bold;
        padding: 1px 6px;
        border-radius: 3px;
        color: {p["bg"]};
        background: {p["accent"]};
    }}
    QLabel[objectName="variablePopupBadge"][varSource="collection"] {{
        background: {p["success"]};
    }}
    QLabel[objectName="variablePopupBadge"][varSource="environment"] {{
        background: {p["accent"]};
    }}
    QLabel[objectName="variablePopupBadge"][varSource="unresolved"] {{
        background: {p["warning"]};
    }}
    QLabel[objectName="variablePopupBadge"][varSource="local"] {{
        background: {p["success"]};
    }}
    QPushButton[objectName="variablePopupUpdateBtn"] {{
        background: {p["accent"]};
        color: {p["bg"]};
        border: none;
        border-radius: 3px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton[objectName="variablePopupUpdateBtn"]:hover {{
        background: {p["selected_bg"]};
    }}
    QPushButton[objectName="variablePopupResetBtn"] {{
        background: transparent;
        color: {p["muted"]};
        border: 1px solid {p["border"]};
        border-radius: 3px;
        padding: 2px 8px;
        font-size: 11px;
    }}
    QPushButton[objectName="variablePopupResetBtn"]:hover {{
        color: {p["text"]};
        border-color: {p["muted"]};
    }}
    QFrame[objectName="variablePopupAddPanel"] {{
        border: 1px solid {p["border"]};
        border-top: none;
        border-radius: 0px 0px 4px 4px;
        background: {p["input_bg"]};
        padding: 2px 0px;
    }}
    QPushButton[objectName="variablePopupAddSelect"] {{
        background: {p["input_bg"]};
        color: {p["muted"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
    }}
    QPushButton[objectName="variablePopupAddSelect"]:hover {{
        border-color: {p["accent"]};
        color: {p["text"]};
    }}
    QPushButton[objectName="variablePopupTarget"] {{
        background: transparent;
        color: {p["text"]};
        border: none;
        border-radius: 0px;
        padding: 6px 8px;
        font-size: 12px;
        text-align: left;
    }}
    QPushButton[objectName="variablePopupTarget"]:hover {{
        background: {p["selected_bg"]};
        color: {p["bg"]};
    }}
    QPushButton[objectName="variablePopupTarget"]:disabled {{
        color: {p["muted"]};
    }}
    QLabel[objectName="variablePopupNoEnv"] {{
        color: {p["variable_unresolved_text"]};
        background: {p["variable_unresolved_highlight"]};
        border: none;
        border-radius: 0px;
        padding: 6px 8px;
        font-size: 11px;
    }}

    /* ---- New-item dialog (icon grid) ------------------------------ */
    QDialog[objectName="newItemPopup"] {{
        background: {p["bg"]};
    }}
    QLabel[objectName="newItemTitle"] {{
        font-size: 14px;
        font-weight: 600;
        color: {p["text"]};
    }}
    QPushButton[objectName="newItemTile"] {{
        background: {p["bg_alt"]};
        border: 1px solid {p["border"]};
        border-radius: 8px;
    }}
    QPushButton[objectName="newItemTile"]:hover {{
        border-color: {p["accent"]};
        background: {"rgba(79,193,255,0.08)" if p is DARK_PALETTE else "rgba(52,152,219,0.06)"};
    }}
    QLabel[objectName="newItemTileLabel"] {{
        font-size: 12px;
        font-weight: 500;
        color: {p["text"]};
    }}
    QLabel[objectName="newItemDescription"] {{
        font-size: 11px;
        color: {p["text_muted"]};
        padding: 8px 4px 0px 4px;
    }}

    /* ---- Save-request dialog ------------------------------------ */
    QTreeWidget[objectName="collectionTree"] {{
        border: 1px solid {p["border"]};
        background: {p["input_bg"]};
        border-radius: 4px;
        outline: none;
    }}
    QTreeWidget[objectName="collectionTree"]::item {{
        padding: 6px 8px;
        border: none;
    }}
    QTreeWidget[objectName="collectionTree"]::item:hover {{
        background: {p["hover_tree_bg"]};
    }}
    QTreeWidget[objectName="collectionTree"]::item:selected {{
        background: {p["selected_bg"]};
        color: {p["text"]};
    }}

    /* ---- Right sidebar ------------------------------------------ */
    QWidget[objectName="sidebarPanelArea"] {{
        background: {p["bg"]};
        border-right: 1px solid {p["border"]};
    }}
    /* Scroll area inside expanded sidebar must not override parent's right border */
    QWidget[objectName="sidebarPanelArea"] QScrollArea {{
        border: none;
        border-right: 1px solid {p["border"]};
    }}
    QWidget[objectName="sidebarRail"] {{
        background: {p["bg"]};
        border-left: 1px solid {p["border"]};
    }}
    QToolButton[objectName="sidebarRailButton"] {{
        background: transparent;
        border: none;
        border-radius: 4px;
        margin: 2px 1px;
        color: {p["text_muted"]};
    }}
    QToolButton[objectName="sidebarRailButton"]:hover {{
        background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.05)"};
    }}
    QToolButton[objectName="sidebarRailButton"]:checked {{
        background: {"rgba(255,255,255,0.10)" if p is DARK_PALETTE else "rgba(0,0,0,0.08)"};
        color: {p["text"]};
    }}
    QToolButton[objectName="sidebarRailButton"]:disabled {{
        color: {p["text_muted"]};
        opacity: 0.4;
    }}
    QLabel[objectName="sidebarTitleLabel"] {{
        font-weight: bold;
        font-size: 13px;
        color: {p["text"]};
    }}
    QLabel[objectName="variableKeyLabel"] {{
        font-family: monospace;
        font-size: 12px;
        color: {p["text"]};
    }}
    QLabel[objectName="variableValueLabel"] {{
        font-family: monospace;
        font-size: 12px;
        color: {p["text_muted"]};
    }}
    QLineEdit[objectName="variableKeyLabel"] {{
        font-family: monospace;
        font-size: 12px;
        color: {p["text"]};
        background: transparent;
        border: none;
        padding: 1px 0px;
    }}
    QLineEdit[objectName="variableValueLabel"] {{
        font-family: monospace;
        font-size: 12px;
        color: {p["text_muted"]};
        background: transparent;
        border: none;
        padding: 1px 0px;
    }}
    QPlainTextEdit[objectName="variableValueEditor"] {{
        font-family: monospace;
        font-size: 12px;
        color: {p["text_muted"]};
        background: transparent;
        border: none;
        padding: 2px 0px;
    }}
    QToolButton[objectName="kvValueExpandToggle"] {{
        background: transparent;
        border: none;
        padding: 4px;
    }}
    QToolButton[objectName="kvValueExpandToggle"]:hover {{
        background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
        border-radius: 4px;
    }}
    QLabel[objectName="sidebarSourceDot"] {{
        font-size: 16px;
        font-weight: bold;
    }}
    QLabel[objectName="sidebarSourceDot"][varSource="environment"] {{
        color: {p["accent"]};
    }}
    QLabel[objectName="sidebarSourceDot"][varSource="collection"] {{
        color: {p["success"]};
    }}
    QLabel[objectName="sidebarSourceDot"][varSource="local"] {{
        color: {p["warning"]};
    }}
    QLabel[objectName="sidebarSeparator"] {{
        background: {p["border"]};
        margin-top: 4px;
        margin-bottom: 4px;
    }}

    /* ---- Completion popup (code editor autocomplete) ------------ */
    QFrame[objectName="completionPopup"] {{
        background: {p["bg"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
    }}
    QListWidget[objectName="completionPopupList"] {{
        background: transparent;
        border: none;
        outline: none;
        font-size: 12px;
    }}
    QListWidget[objectName="completionPopupList"]::item {{
        padding: 1px 4px;
    }}
    QListWidget[objectName="completionPopupList"]::item:selected {{
        background: {p["selected_bg"]};
    }}
    QListWidget[objectName="completionPopupList"]::item:hover {{
        background: {p["hover_bg"]};
    }}
    QLabel[objectName="completionPopupDoc"] {{
        color: {p["text_muted"]};
        font-size: 11px;
        padding: 2px 8px;
        border-bottom: 1px solid {p["border"]};
    }}

    /* ---- Parameter hint (code editor call signatures) ----------- */
    QFrame[objectName="parameterHintPopup"] {{
        background: {p["bg"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
    }}
    QLabel[objectName="parameterHintPopupLabel"] {{
        color: {p["text_muted"]};
        font-family: monospace;
        font-size: 12px;
    }}

    QFrame[objectName="symbolDocPopup"] {{
        background: {p["bg"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
    }}
    QLabel[objectName="symbolDocPopupLabel"] {{
        color: {p["text"]};
        font-family: monospace;
        font-size: 12px;
    }}

    /* ---- Runtime download banner -------------------------------- */
    QFrame[objectName="RuntimeBanner"] {{
        background: {p["bg_alt"]};
        border: 1px solid {p["border"]};
        border-radius: 4px;
    }}
    QLabel[objectName="bannerMessage"] {{
        color: {p["text"]};
        font-size: 12px;
    }}
    QLabel[objectName="bannerMessage"] a {{
        color: {p["accent"]};
        text-decoration: none;
    }}
    QLabel[objectName="bannerMessage"] a:hover {{
        text-decoration: underline;
    }}
    QPushButton[objectName="bannerDownloadBtn"] {{
        background: {p["accent"]};
        color: #ffffff;
        border: none;
        border-radius: 3px;
        padding: 4px 12px;
        font-size: 12px;
    }}
    QPushButton[objectName="bannerDownloadBtn"]:hover {{
        opacity: 0.9;
    }}
    QPushButton[objectName="bannerDownloadBtn"]:disabled {{
        opacity: 0.5;
    }}
    """
