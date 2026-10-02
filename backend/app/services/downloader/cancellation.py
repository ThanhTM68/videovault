"""Per-invocation cooperative stop; no process identifiers or shared adapter state."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event

from app.core.errors import AppError


class DownloadCancelledError(AppError):
    code = "DOWNLOAD_CANCELLED"

    def __init__(self) -> None:
        super().__init__("Download was cancelled")


_signal: ContextVar[Event | None] = ContextVar("download_stop", default=None)


def check_cancelled() -> None:
    signal = _signal.get()
    if signal is not None and signal.is_set():
        raise DownloadCancelledError()


@contextmanager
def cancellation_scope(signal: Event | None) -> Iterator[None]:
    token = _signal.set(signal)
    try:
        yield
    finally:
        _signal.reset(token)
