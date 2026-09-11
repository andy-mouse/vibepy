"""What one Studio window owns, as one value its Tools reach through ToolContext."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from vibepy_studio.internals.processes import Processes


@dataclass
class StudioDeps:
    """What one Studio window owns."""

    root: Path
    processes: Processes
    proxy_port: int
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
