"""The states an AppRuntime passes through.

These are the framework's runtime states. Install, upgrade and uninstall belong
to the package control plane and are deliberately absent. See
`docs/decisions/ADR-006-runtime-vs-package-lifecycle.md`.
"""

from enum import StrEnum


class AppRuntimeState(StrEnum):
    """``CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED``.

    A string enum because the value is what an operator reads in a log and what
    a control plane reports.

    STOPPED is terminal. An unwound runtime holds no resource to re-enter, so a
    restart is a new AppRuntime, isolated from its predecessor by default.
    """

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
