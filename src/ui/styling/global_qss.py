"""Global QSS builder — extracted from ThemeManager.

Contains the single build_global_qss function that builds the
application-wide Qt Style Sheet string from a ThemePalette.
"""

from __future__ import annotations

from ui.styling.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    BADGE_MIN_WIDTH,
    DARK_PALETTE,
    LIGHT_PALETTE,
    TREE_ROW_HEIGHT,
    ThemePalette,
)


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

    /* ---- Scroll areas ------------------------------------------- */
    QScrollArea {{
        border: none;
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
    QWidget[objectName="sidebarRail"] {{
        background: {p["bg"]};
        border-left: 1px solid {p["border"]};
    }}
    QToolButton[objectName="sidebarRailButton"] {{
        background: transparent;
        border: none;
        border-radius: 4px;
        margin: 2px 3px;
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
    """
