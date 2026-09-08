"""What one Hub window owns, as one value its Tools reach through ToolContext."""

from dataclasses import dataclass
from pathlib import Path

from vibepy_hub.internals.processes import Processes


@dataclass
class HubDeps:
    """What one Hub window owns."""

    root: Path
    processes: Processes
