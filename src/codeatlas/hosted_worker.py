"""In-process background sync worker for the hosted control plane.

Webhook handlers must return fast (GitHub times out and redelivers slow
responses), so cloning and indexing run off the request path here. A single
worker thread serializes writes per process, so two deliveries cannot race the
same per-repo graph DB. Each job opens its own ``HostedStore`` (its own SQLite
connection) to stay clear of cross-thread connection sharing.

This is deliberately an in-process queue, not Celery/Redis — enough for MVP
scale, and it keeps deployment to a single FastAPI process.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from pathlib import Path

from codeatlas.hosted import HostedStore, SyncResult

logger = logging.getLogger(__name__)


class SyncJobWorker:
    """Runs hosted sync jobs in a background thread pool."""

    def __init__(self, db_path: Path | str, *, max_workers: int = 1) -> None:
        self.db_path = Path(db_path)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="stratum-sync",
        )
        self._lock = threading.Lock()
        self._futures: set[Future[SyncResult]] = set()

    def enqueue(
        self,
        repo_id: str,
        *,
        delivery_id: str | None = None,
        github_provider_repo_id: str | None = None,
    ) -> Future[SyncResult]:
        """Mark the repo pending and schedule its sync off the request path."""
        store = HostedStore(self.db_path)
        try:
            store.set_sync_status(repo_id, "pending")
        finally:
            store.close()
        future = self._executor.submit(
            self._run,
            repo_id,
            delivery_id,
            github_provider_repo_id,
        )
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._discard)
        return future

    def _discard(self, future: Future[SyncResult]) -> None:
        with self._lock:
            self._futures.discard(future)

    def _run(
        self,
        repo_id: str,
        delivery_id: str | None,
        github_provider_repo_id: str | None,
    ) -> SyncResult:
        store = HostedStore(self.db_path)
        try:
            return store.run_sync_pipeline(
                repo_id,
                delivery_id=delivery_id,
                github_provider_repo_id=github_provider_repo_id,
            )
        except Exception:
            # The pipeline already recorded a failed sync event + status; log so
            # the failure is visible in process logs as well as the dashboard.
            logger.exception("hosted sync job failed for repo %s", repo_id)
            raise
        finally:
            store.close()

    def wait_for_idle(self, timeout: float | None = None) -> None:
        """Block until all in-flight jobs finish (used by tests and shutdown)."""
        with self._lock:
            pending = set(self._futures)
        if pending:
            futures_wait(pending, timeout=timeout)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
