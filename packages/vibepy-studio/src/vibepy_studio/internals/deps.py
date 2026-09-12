"""What one Studio window owns, as one value its Tools reach through ToolContext."""

from dataclasses import dataclass

from vibepy_studio.internals.processes import Processes
from vibepy_studio.operating.internals.root import StudioRoot


@dataclass(kw_only=True)
class StudioDeps:
    """Its root directory, its child processes, and the port its proxy listens on.

    Every value here answers with an async or a pure operation, which is the shape
    `docs/architecture/runtime.md` asks a handler's dependencies to have.
    """

    root: StudioRoot
    processes: Processes
    proxy_port: int
