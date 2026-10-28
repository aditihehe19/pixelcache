"""A deliberately simple, single-worker job queue.

Benchmarks are executed strictly one at a time. This is a measurement
requirement, not just a resource limit: two benchmarks running together would
compete for the shared L3 cache and memory bandwidth and corrupt each other's
timings. Job state lives in the database (experiments.status), so the queue
itself only holds ids; after a restart, queued jobs are re-submitted and
jobs that were running are marked failed (see recover()).
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable

log = logging.getLogger("pixelcache.jobs")


class QueueFull(Exception):
    pass


class JobQueue:
    def __init__(self, handler: Callable[[str], None], max_pending: int) -> None:
        self._handler = handler
        self._max_pending = max_pending
        self._pending: deque[str] = deque()
        self._running: str | None = None
        self._cv = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name="pixelcache-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        if self._thread:
            self._thread.join(timeout)

    def submit(self, job_id: str) -> int:
        """Queue a job; returns its 1-based position (1 = next to run)."""
        with self._cv:
            if len(self._pending) >= self._max_pending:
                raise QueueFull(f"{len(self._pending)} jobs are already waiting; try again later")
            self._pending.append(job_id)
            self._cv.notify()
            return len(self._pending)

    def discard(self, job_id: str) -> bool:
        with self._cv:
            try:
                self._pending.remove(job_id)
                return True
            except ValueError:
                return False

    def position(self, job_id: str) -> int | None:
        with self._cv:
            if self._running == job_id:
                return 0
            try:
                return self._pending.index(job_id) + 1
            except ValueError:
                return None

    def snapshot(self) -> dict:
        with self._cv:
            return {"running": self._running, "pending": len(self._pending), "max_pending": self._max_pending,
                    "worker_alive": bool(self._thread and self._thread.is_alive())}

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                job_id = self._pending.popleft()
                self._running = job_id
            try:
                self._handler(job_id)
            except Exception:  # the handler records failures itself; never let the worker die
                log.exception("job %s crashed outside its handler", job_id)
            finally:
                with self._cv:
                    self._running = None
