"""The operating role's own internals: its window's resource, and its domain work.

A Tool handler reaches its domain work through its ToolContext, and `entry.py`
reaches `StudioDeps` to build the window. The exception is a host operation --
something Studio's process does with the machine it is installed on, such as
opening a folder dialog on its desktop. That is not channel-neutral and so is
not a Tool (ADR-042), and the operating role's Web implementation calls it
directly. Every operation exported
here is `async` or pure (`docs/architecture/runtime.md`).
"""

from vibepy_studio.operating.internals.configuration import (
    held_secrets,
    is_configured,
    secret_fields,
    without_secrets,
)
from vibepy_studio.operating.internals.deps import StudioDeps
from vibepy_studio.operating.internals.dialogs import (
    FolderDialogFailed,
    PlatformUnsupported,
    choose_folder,
)
from vibepy_studio.operating.internals.installer import (
    ENV_DIR,
    AppNameInvalid,
    InstallFailed,
    app_folder,
    declarations,
    describe,
    environment,
    environments,
    install,
    installed_facts,
    interpreter,
    purelib,
    read_facts,
    remove_app_folder,
    remove_environment,
    write_facts,
)
from vibepy_studio.operating.internals.processes import (
    AlreadyStarted,
    Processes,
    StartFailed,
)
from vibepy_studio.operating.internals.root import StudioRoot
from vibepy_studio.operating.internals.routing import (
    address,
    allocate,
    remove_route,
    write_route,
)
from vibepy_studio.operating.internals.state import OperatingState, read_state, write_state
from vibepy_studio.operating.internals.wheels import Candidate, candidates, readable

__all__ = [
    "ENV_DIR",
    "AlreadyStarted",
    "AppNameInvalid",
    "Candidate",
    "FolderDialogFailed",
    "InstallFailed",
    "OperatingState",
    "PlatformUnsupported",
    "Processes",
    "StartFailed",
    "StudioDeps",
    "StudioRoot",
    "address",
    "allocate",
    "app_folder",
    "candidates",
    "choose_folder",
    "declarations",
    "describe",
    "environment",
    "environments",
    "held_secrets",
    "install",
    "installed_facts",
    "interpreter",
    "is_configured",
    "purelib",
    "read_facts",
    "read_state",
    "readable",
    "remove_app_folder",
    "remove_environment",
    "remove_route",
    "secret_fields",
    "without_secrets",
    "write_facts",
    "write_route",
    "write_state",
]
