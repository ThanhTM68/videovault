import logging
import time
from collections.abc import Callable
from threading import Event, Lock, Thread

from app.core.errors import ConflictError
from app.services.queue.models import Claim, JobView
from app.services.queue.recovery import recover_stale_jobs
from app.services.queue.service import QueueService
from app.workers.download_worker import execute_download, log_failure

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 5.0
POLL_SECONDS = 0.25
SHUTDOWN_SECONDS = 5.0


class WorkerManager:
    def __init__(
        self,
        queue: QueueService,
        concurrency: int,
        *,
        poll_seconds: float = POLL_SECONDS,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
        on_stopped: Callable[[], None] = lambda: None,
    ) -> None:
        self.queue = queue
        self.concurrency = concurrency
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.on_stopped = on_stopped
        self._gate = Lock()
        self._active_lock = Lock()
        self._active: dict[str, tuple[Claim, Event]] = {}
        self._paused = False
        self._stop = Event()
        self._wake = Event()
        self._supervisor_wake = Event()
        self._started = False
        self.threads: list[Thread] = []
        self.supervisor: Thread | None = None

    @property
    def paused(self) -> bool:
        with self._gate:
            return self._paused

    def start(self) -> None:
        with self._gate:
            if self._started:
                raise ConflictError("Worker manager has already started")
            # A missing migration is a startup failure, never a silently idle queue.
            recover_stale_jobs(self.queue)
            self._started = True
            self.threads = [
                Thread(target=self._run, name=f"videovault-worker-{i}", daemon=True)
                for i in range(self.concurrency)
            ]
            self.supervisor = Thread(
                target=self._supervise, name="videovault-heartbeat", daemon=True
            )
            try:
                self.supervisor.start()
                for thread in self.threads:
                    thread.start()
            except Exception:
                self._stop.set()
                self._wake.set()
                self._supervisor_wake.set()
                raise
        logger.info("Worker manager started (%s workers)", self.concurrency)

    def notify(self) -> None:
        self._wake.set()

    def pause(self) -> dict[str, bool]:
        with self._gate:
            self._paused = True
        logger.info("Queue paused")
        return {"paused": True}

    def resume(self) -> dict[str, bool]:
        with self._gate:
            self._paused = False
        self.notify()
        logger.info("Queue resumed")
        return {"paused": False}

    def cancel(self, job_id: str) -> JobView:
        view = self.queue.cancel(job_id)
        with self._active_lock:
            active = self._active.get(job_id)
            if active:
                active[1].set()
        self._supervisor_wake.set()
        return view

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with self._gate:
                    claim = None if self._paused or self._stop.is_set() else self.queue.claim()
                    if claim:
                        signal = Event()
                        with self._active_lock:
                            self._active[claim.id] = (claim, signal)
                if claim is None:
                    self._wake.wait(self.poll_seconds)
                    self._wake.clear()
                    continue
                try:
                    # Read durable cancellation before starting potentially blocking I/O.
                    requested = self.queue.heartbeat(claim)
                    if requested is None or requested:
                        signal.set()
                    execute_download(self.queue, claim, signal)
                finally:
                    with self._active_lock:
                        self._active.pop(claim.id, None)
            except Exception as exc:
                log_failure(exc)
                self._stop.wait(self.poll_seconds)

    def tick(self) -> None:
        """Heartbeat is independent of downloader callbacks, including blocking FFmpeg."""
        with self._active_lock:
            active = list(self._active.values())
        for claim, signal in active:
            try:
                requested = self.queue.heartbeat(claim)
                if requested is None or requested:
                    signal.set()
            except Exception as exc:
                # Fail closed: this attempt must not complete if its lease cannot be maintained.
                signal.set()
                log_failure(exc)
        if not self._stop.is_set():
            recover_stale_jobs(self.queue, exclude_ids=frozenset(claim.id for claim, _ in active))

    def _supervise(self) -> None:
        try:
            while not self._stop.is_set() or any(t.is_alive() for t in self.threads):
                self._supervisor_wake.wait(self.heartbeat_seconds)
                self._supervisor_wake.clear()
                try:
                    self.tick()
                except Exception as exc:
                    log_failure(exc)
        finally:
            try:
                self.on_stopped()
            except Exception as exc:
                log_failure(exc)
            logger.info("Worker manager stopped")

    def stop(self, *, timeout: float = SHUTDOWN_SECONDS) -> bool:
        with self._gate:
            self._stop.set()
            with self._active_lock:
                for _, signal in self._active.values():
                    signal.set()
        self._wake.set()
        self._supervisor_wake.set()
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(max(0, deadline - time.monotonic()))
        self._supervisor_wake.set()
        if self.supervisor and self.supervisor.ident is not None:
            self.supervisor.join(max(0, deadline - time.monotonic()))
        stopped = all(not t.is_alive() for t in self.threads) and (
            self.supervisor is None or not self.supervisor.is_alive()
        )
        if not stopped:
            logger.warning("Shutdown deadline reached; cooperative downloads still stopping")
        return stopped
