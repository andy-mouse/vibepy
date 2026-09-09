"""The Hub's own domain internals, behind its Tools.

`docs/architecture.md` places an App's models, policies, repositories and
integrations here, which is why calling `uv`, reading a project file, holding a
child process and storing state are not Tools. A Tool handler reaches them
through its ToolContext and nothing else does.
"""

from vibepy_hub.internals.configuration import is_configured, masked, secret_fields
from vibepy_hub.internals.deps import HubDeps
from vibepy_hub.internals.installer import (
    AppNameInvalid,
    InstallFailed,
    describe,
    environment,
    environments,
    install,
    installed_facts,
    interpreter,
    purelib,
    read_facts,
    remove_environment,
    write_facts,
)
from vibepy_hub.internals.processes import Processes, StartFailed
from vibepy_hub.internals.projects import Candidate, candidates, readable
from vibepy_hub.internals.state import HubState, read_state, write_state

__all__ = [
    "AppNameInvalid",
    "Candidate",
    "HubDeps",
    "HubState",
    "InstallFailed",
    "Processes",
    "StartFailed",
    "candidates",
    "describe",
    "environment",
    "environments",
    "install",
    "installed_facts",
    "interpreter",
    "is_configured",
    "masked",
    "purelib",
    "read_facts",
    "read_state",
    "readable",
    "remove_environment",
    "secret_fields",
    "write_facts",
    "write_state",
]
