"""What one Studio window owns, as one value its Tools reach through ToolContext."""

from dataclasses import dataclass

from vibepy_studio.internals.processes import Processes
from vibepy_studio.operating.internals.root import StudioRoot


@dataclass(kw_only=True)
class StudioDeps:
    """Its root directory, its child processes, and the port its proxy listens on.

    Every value here answers with an async or a pure operation. Nothing a handler
    reaches through it carries a blocking method of its own, which is how
    `docs/architecture/runtime.md`'s rule holds without a handler having to
    remember it.
    """

    root: StudioRoot
    processes: Processes
    proxy_port: int
