from app.core.errors import ConflictError
from app.models.enums import JobStatus as S

ACTIVE = frozenset({S.RESOLVING, S.DOWNLOADING, S.PROCESSING, S.UPLOADING})
TERMINAL = frozenset({S.COMPLETED, S.FAILED, S.CANCELLED, S.SKIPPED_DUPLICATE})
TRANSITIONS = {
    S.QUEUED: frozenset({S.RESOLVING, S.CANCELLED}),
    S.RESOLVING: frozenset({S.DOWNLOADING, S.FAILED, S.CANCELLED}),
    S.DOWNLOADING: frozenset({S.PROCESSING, S.FAILED, S.CANCELLED}),
    S.PROCESSING: frozenset({S.COMPLETED, S.FAILED, S.CANCELLED}),
    # Reserved for later upload handlers; Phase 05 never enters this state.
    S.UPLOADING: frozenset({S.COMPLETED, S.FAILED, S.CANCELLED}),
    S.COMPLETED: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
    S.SKIPPED_DUPLICATE: frozenset(),
}


def validate_transition(source: S, target: S, *, operation: str = "execute") -> None:
    allowed = target in TRANSITIONS[source]
    if operation == "retry":
        allowed = source == S.FAILED and target == S.QUEUED
    elif operation == "recover":
        allowed = source in ACTIVE and target in {S.QUEUED, S.FAILED, S.CANCELLED}
    if not allowed:
        raise ConflictError("Job state does not permit this operation")
