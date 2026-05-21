"""Configuration for :class:`ScriptEditorPane`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScriptEditorPaneOptions:
    """Feature flags and labels for one script editor stack."""

    script_type: Literal["pre_request", "test"] = "pre_request"
    host_kind: Literal["request", "folder", "local_script"] = "request"
    placeholder: str = ""
    show_inherited_banner: bool = False
    show_run_all: bool = True
    show_version_history: bool = True
    show_auto_save: bool = True
    enable_test_gutter: bool = False
    use_host_version_timer: bool = False
