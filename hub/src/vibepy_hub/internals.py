"""The Hub's own domain internals, as one value a window owns.

A Tool handler reaches these through its ToolContext and nothing else does.
`docs/architecture.md` places an app's repositories and integrations here, which
is why calling `uv`, reading a folder and holding a child process are not Tools.
"""

from dataclasses import dataclass
from pathlib import Path

from vibepy_hub.processes import Processes


@dataclass
class HubDeps:
    """What one Hub window owns."""

    root: Path
    processes: Processes
