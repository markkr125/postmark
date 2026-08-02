"""Background prefetch of session tab payloads (read-only DB, worker threads)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal

from services.collection_service import CollectionService, RequestLoadDict
from services.local_script_service import LocalScriptLoadDict, LocalScriptService


def _prefetch_worker_count() -> int:
    """Bound parallel SQLite readers to avoid oversubscription."""
    cpu = os.cpu_count() or 1
    return max(1, min(8, cpu))


def _chunk_ids(ids: list[int], *, workers: int) -> list[list[int]]:
    """Split *ids* into up to *workers* contiguous chunks."""
    if not ids:
        return []
    chunk_size = max(1, (len(ids) + workers - 1) // workers)
    return [ids[i : i + chunk_size] for i in range(0, len(ids), chunk_size)]


@dataclass
class SessionPrefetchResult:
    """Read-only payloads gathered off the GUI thread."""

    requests: dict[int, RequestLoadDict] = field(default_factory=dict)
    breadcrumbs: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    local_scripts: dict[int, LocalScriptLoadDict] = field(default_factory=dict)
    folder_names: dict[int, str] = field(default_factory=dict)


class SessionPrefetchWorker(QObject):
    """Prefetch session tab data using a bounded thread pool.

    Each repository call opens its own SQLite session (WAL mode).  Parallel
    reads are safe; writes never occur on this path.
    """

    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        request_ids: list[int],
        local_script_ids: list[int],
        folder_ids: list[int],
    ) -> None:
        """Store id lists to load when :meth:`run` executes on a worker thread."""
        super().__init__()
        self._request_ids = list(dict.fromkeys(request_ids))
        self._local_script_ids = list(dict.fromkeys(local_script_ids))
        self._folder_ids = list(dict.fromkeys(folder_ids))

    def run(self) -> None:
        """Load all payloads and emit :class:`SessionPrefetchResult`."""
        try:
            result = SessionPrefetchResult()
            workers = _prefetch_worker_count()

            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending: list[tuple[str, Any]] = []

                for part in _chunk_ids(self._request_ids, workers=workers):
                    pending.append(
                        ("requests", pool.submit(CollectionService.fetch_requests_by_ids, part))
                    )
                if self._request_ids:
                    pending.append(
                        (
                            "breadcrumbs",
                            pool.submit(
                                CollectionService.fetch_request_breadcrumbs_by_ids,
                                self._request_ids,
                            ),
                        )
                    )
                for part in _chunk_ids(self._local_script_ids, workers=workers):
                    pending.append(
                        (
                            "local_scripts",
                            pool.submit(
                                LocalScriptService.fetch_local_script_load_dicts_by_ids,
                                part,
                            ),
                        )
                    )
                if self._folder_ids:
                    pending.append(
                        (
                            "folder_names",
                            pool.submit(
                                CollectionService.fetch_collection_names_by_ids,
                                self._folder_ids,
                            ),
                        )
                    )

                for kind, future in pending:
                    payload = future.result()
                    if kind == "requests":
                        result.requests.update(payload)
                    elif kind == "breadcrumbs":
                        result.breadcrumbs.update(payload)
                    elif kind == "local_scripts":
                        result.local_scripts.update(payload)
                    elif kind == "folder_names":
                        result.folder_names.update(payload)

            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


__all__ = ["SessionPrefetchResult", "SessionPrefetchWorker"]
