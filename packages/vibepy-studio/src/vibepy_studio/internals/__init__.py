"""What both of Studio's roles share, behind no Tool of its own."""

from vibepy_studio.internals.deps import StudioDeps
from vibepy_studio.internals.describing import DescribeFailed, describe
from vibepy_studio.internals.processes import (
    AlreadyStarted,
    ChildFailure,
    Completed,
    NotRunnable,
    Processes,
    StartFailed,
    child_environment,
    is_runnable,
    reported,
    run,
)

__all__ = [
    "AlreadyStarted",
    "ChildFailure",
    "Completed",
    "DescribeFailed",
    "NotRunnable",
    "Processes",
    "StartFailed",
    "StudioDeps",
    "child_environment",
    "describe",
    "is_runnable",
    "reported",
    "run",
]
