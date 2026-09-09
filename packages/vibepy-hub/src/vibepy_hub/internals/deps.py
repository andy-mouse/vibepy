"""What one Hub window owns, as one value its Tools reach through ToolContext."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from vibepy_hub.internals.processes import Processes


@dataclass
class HubDeps:
    """What one Hub window owns."""

    root: Path
    processes: Processes
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
