"""Status code popup — shows the HTTP status description on click.

Displays the status code badge (coloured) and a human-readable
explanation of what the code means.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from ui.info_popup import InfoPopup
from ui.theme import COLOR_WHITE

# -- Status descriptions -----------------------------------------------
# Coverage of common HTTP status codes with concise Postman-style text.
STATUS_DESCRIPTIONS: dict[int, str] = {
    # 1xx Informational
    100: "The server has received the request headers and the client should proceed to send the request body.",
    101: "The server is switching protocols as requested by the client.",
    102: "The server is processing the request but no response is available yet.",
    103: "The server is sending preliminary hints before the final response.",
    # 2xx Success
    200: "The request was successful. The server has responded as required.",
    201: "The request was successful and a new resource has been created.",
    202: "The request has been accepted for processing but is not yet complete.",
    204: "The server has successfully processed the request with no content to return.",
    206: "The server is delivering only part of the resource due to a range header sent by the client.",
    207: "The response conveys information about multiple resources where multiple status codes might be appropriate.",
    # 3xx Redirection
    301: "The requested resource has been permanently moved to a new URL.",
    302: "The requested resource resides temporarily under a different URL.",
    303: "The response can be found under a different URL using a GET method.",
    304: "The resource has not been modified since the last request.",
    307: "The request should be repeated with the same method to a different URL.",
    308: "The request and all future requests should be directed to the given URL.",
    # 4xx Client Error
    400: "The server cannot process the request due to a client error (e.g. malformed syntax).",
    401: "Authentication is required and has failed or has not been provided.",
    403: "The server understood the request but refuses to authorise it.",
    404: "The requested resource could not be found on the server.",
    405: "The request method is not allowed for the requested resource.",
    406: "The server cannot produce a response matching the list of acceptable values.",
    408: "The server timed out waiting for the request.",
    409: "The request could not be completed due to a conflict with the current state of the resource.",
    410: "The requested resource is no longer available and has been permanently removed.",
    413: "The request entity is larger than the server is willing or able to process.",
    415: "The media type of the request data is not supported by the server.",
    422: "The server understands the content type but was unable to process the contained instructions.",
    429: "The user has sent too many requests in a given amount of time (rate limiting).",
    # 5xx Server Error
    500: "The server encountered an unexpected condition that prevented it from fulfilling the request.",
    501: "The server does not support the functionality required to fulfil the request.",
    502: "The server received an invalid response from an upstream server.",
    503: "The server is currently unavailable (overloaded or down for maintenance).",
    504: "The server did not receive a timely response from an upstream server.",
}

_RANGE_DESCRIPTIONS: dict[int, str] = {
    1: "Informational response — the request was received and is being processed.",
    2: "Successful response — the request was received, understood, and accepted.",
    3: "Redirection — further action is needed to complete the request.",
    4: "Client error — the request contains bad syntax or cannot be fulfilled.",
    5: "Server error — the server failed to fulfil a valid request.",
}


def _status_description(code: int) -> str:
    """Return a human-readable description for *code*."""
    if code in STATUS_DESCRIPTIONS:
        return STATUS_DESCRIPTIONS[code]
    prefix = code // 100
    return _RANGE_DESCRIPTIONS.get(prefix, "Unknown status code.")


class StatusPopup(InfoPopup):
    """Popup showing HTTP status code meaning."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise layout with code badge and description label."""
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)

        self._code_label = QLabel()
        self._code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self._code_label)

        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setObjectName("mutedLabel")
        self.content_layout.addWidget(self._desc_label)

    def update_status(self, code: int, text: str, color: str) -> None:
        """Populate the popup with status *code*, *text*, and badge *color*."""
        self._code_label.setText(f"{code} {text}")
        self._code_label.setStyleSheet(
            f"font-weight: bold; font-size: 14px; padding: 4px 12px;"
            f" border-radius: 4px; color: {COLOR_WHITE}; background: {color};"
        )
        self._desc_label.setText(_status_description(code))
