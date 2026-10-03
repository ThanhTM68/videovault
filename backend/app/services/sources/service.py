import logging
import secrets
import time
from collections.abc import Callable
from threading import BoundedSemaphore, RLock

from app.repositories.library import LibraryRepository
from app.schemas.queue import SubmittedJob
from app.schemas.sources import (
    BatchDownloadRequest,
    BatchDownloadResult,
    BatchOutcome,
    PreviewStatistics,
    SourcePreview,
    SourceResolveRequest,
)
from app.services.queue.service import QueueService
from app.services.sources.adapters import SourceAdapterRegistry
from app.services.sources.errors import SourceError
from app.services.sources.urls import source_url

logger = logging.getLogger(__name__)


class SourceService:
    def __init__(
        self,
        queue: QueueService,
        registry: SourceAdapterRegistry | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.queue, self.registry, self.clock = queue, registry or SourceAdapterRegistry(), clock
        self.previews: dict[str, tuple[float, SourcePreview]] = {}
        self.lock = RLock()
        self.enumerations = BoundedSemaphore(2)

    def _prune(self) -> None:
        self.previews = {
            key: value for key, value in self.previews.items() if value[0] > self.clock()
        }

    def resolve(self, request: SourceResolveRequest) -> SourcePreview:
        adapter, canonical = self.registry.select(request.url)
        caps = adapter.capabilities
        if not caps.list_profile_or_channel:
            raise SourceError("SOURCE_LIST_UNSUPPORTED")
        if request.ordering != "source" and not getattr(caps, "sort_" + request.ordering):
            raise SourceError("SOURCE_SORT_UNSUPPORTED")
        for requested, supported in (
            (request.min_views is not None or request.max_views is not None, caps.filter_views),
            (request.date_from is not None or request.date_to is not None, caps.filter_date),
            (
                request.min_duration is not None or request.max_duration is not None,
                caps.filter_duration,
            ),
        ):
            if requested and not supported:
                raise SourceError("SOURCE_FILTER_UNSUPPORTED")
        if not self.enumerations.acquire(blocking=False):
            raise SourceError("SOURCE_BUSY")
        try:
            summary, entries = adapter.resolve_source(canonical)
        finally:
            self.enumerations.release()
        # Capabilities are immutable per adapter; no request mutates global flags.
        seen: set[str] = set()
        candidates = []
        rejected = duplicate = unavailable = filtered = 0
        for item in entries[:100]:
            if item is None:
                rejected += 1
                continue
            if item.platform_video_id in seen:
                duplicate += 1
                continue
            seen.add(item.platform_video_id)
            if request.min_duration is not None or request.max_duration is not None:
                if item.duration_seconds is None:
                    unavailable += 1
                    continue
                if (
                    request.min_duration is not None
                    and item.duration_seconds < request.min_duration
                ) or (
                    request.max_duration is not None
                    and item.duration_seconds > request.max_duration
                ):
                    filtered += 1
                    continue
            candidates.append(item)
        candidates = candidates[: request.n]
        with self.queue.sessions() as session:
            states = LibraryRepository(session).identity_states(
                summary.platform, [item.platform_video_id for item in candidates]
            )
        candidates = [
            item.model_copy(
                update={
                    "has_download_history": states.get(item.platform_video_id, (False, False))[0],
                    "has_file": states.get(item.platform_video_id, (False, False))[1],
                }
            )
            for item in candidates
        ]
        preview = SourcePreview(
            preview_id=secrets.token_urlsafe(24),
            source=summary,
            candidates=candidates,
            ordering=request.ordering,
            statistics=PreviewStatistics(
                enumerated_count=min(len(entries), 100),
                rejected_count=rejected,
                duplicate_count=duplicate,
                metadata_unavailable_count=unavailable,
                filtered_count=filtered,
                returned_count=len(candidates),
                already_downloaded_count=sum(item.has_download_history for item in candidates),
            ),
        )
        with self.lock:
            self._prune()
            if len(self.previews) >= 32:
                self.previews.pop(next(iter(self.previews)))
            self.previews[preview.preview_id] = (self.clock() + 600, preview.model_copy(deep=True))
        logger.info("Source preview resolved (%s candidates)", len(candidates))
        return preview

    def submit(self, request: BatchDownloadRequest) -> BatchDownloadResult:
        with self.lock:
            self._prune()
            pending = self.previews.get(request.preview_id)
            if pending is None:
                raise SourceError("SOURCE_PREVIEW_EXPIRED")
            preview = pending[1]
            platform, canonical = source_url(preview.source.canonical_url)
            self.registry.select(canonical)
            by_id = {item.platform_video_id: item for item in preview.candidates}
            if any(identity not in by_id for identity in request.selected_ids):
                raise SourceError("BATCH_SELECTION_INVALID")
            selected = list(dict.fromkeys(request.selected_ids))
            settings = self.queue.downloader.settings
            payloads = request.download_payloads(
                [by_id[identity].canonical_url for identity in selected],
                settings.download_max_height,
                settings.storage_provider,
            )
            # Validate all selections/options/availability before any Job write, even
            # when history will exclude the entire batch. No network I/O at submission.
            for payload in payloads:
                self.queue.downloader.prepare_request(
                    **payload.model_dump(exclude={"force", "storage_target"})
                )
                self.queue.storage.check_available(payload.storage_target)
            with self.queue.sessions() as session:
                states = LibraryRepository(session).identity_states(platform, selected)
            eligible = [
                payload
                for identity, payload in zip(selected, payloads, strict=True)
                if request.force or not states.get(identity, (False, False))[0]
            ]
            jobs = self.queue.submit(eligible) if eligible else []
            job_ids = iter(job.id for job in jobs)
            outcomes = []
            seen = set()
            for identity in request.selected_ids:
                if identity in seen:
                    outcomes.append(
                        BatchOutcome(
                            platform_video_id=identity, outcome="skipped_duplicate_selection"
                        )
                    )
                elif not request.force and states.get(identity, (False, False))[0]:
                    outcomes.append(
                        BatchOutcome(platform_video_id=identity, outcome="skipped_history")
                    )
                else:
                    outcomes.append(
                        BatchOutcome(
                            platform_video_id=identity, outcome="queued", job_id=next(job_ids)
                        )
                    )
                seen.add(identity)
            del self.previews[request.preview_id]
            logger.info("Batch submitted (%s jobs)", len(jobs))
            return BatchDownloadResult(
                jobs=[SubmittedJob(id=job.id) for job in jobs],
                outcomes=outcomes,
                requested_count=len(request.selected_ids),
                created_count=len(jobs),
                skipped_history_count=sum(item.outcome == "skipped_history" for item in outcomes),
                skipped_duplicate_selection_count=sum(
                    item.outcome == "skipped_duplicate_selection" for item in outcomes
                ),
            )
