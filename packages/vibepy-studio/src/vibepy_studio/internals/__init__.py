"""What both of Studio's roles share, behind no Tool of its own.

Only what both use: running one command as a child, and reading what an
environment declares. A resource one role owns lives with that role, so nothing
here imports `vibepy_studio.operating` or `vibepy_studio.authoring`.
"""

from vibepy_studio.internals.describing import DescribeFailed, describe
from vibepy_studio.internals.processes import (
    Completed,
    NotRunnable,
    child_environment,
    reported,
    reports,
    run,
)

__all__ = [
    "Completed",
    "DescribeFailed",
    "NotRunnable",
    "child_environment",
    "describe",
    "reported",
    "reports",
    "run",
]
