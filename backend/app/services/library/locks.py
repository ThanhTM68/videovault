from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, RLock

from app.services.downloader.cancellation import DownloadCancelledError

_LOCKS = tuple(RLock() for _ in range(256))


@contextmanager
def identity_lock(
    platform: str, identity: str, cancellation: Event | None = None
) -> Iterator[None]:
    lock = _LOCKS[hash((platform, identity)) % len(_LOCKS)]
    while not lock.acquire(timeout=0.1):
        if cancellation and cancellation.is_set():
            raise DownloadCancelledError()
    try:
        if cancellation and cancellation.is_set():
            raise DownloadCancelledError()
        yield
    finally:
        lock.release()
