"""PDF/DOCX document extraction tool for the AI assistant."""

from services.ai.chat.tools.document_import.tool import (
    DOCUMENT_IMPORT_TOOL_NAME,
    DocumentImportAction,
    register_document_import_tool,
)

__all__ = [
    "DOCUMENT_IMPORT_TOOL_NAME",
    "DocumentImportAction",
    "register_document_import_tool",
]
