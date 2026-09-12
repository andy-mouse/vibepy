"""Running one command as a child, and the environment a child is entitled to.

Both of Studio's roles start children: operating serves an installed App, and
authoring runs the framework's own commands inside a project's environment. What
they share is here; the window's own running Apps are operating's, in
`vibepy_studio.operating.internals.processes`.
"""

import asyncio
import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from vibepy_core.app.config import ENV_PREFIX
from vibepy_core.errors import ErrorInfo, read_report_line

logger = logging.getLogger(__name__)

DESCRIBES_THIS_PROCESS = frozenset(
    {
        # the environment this process runs in, which is not the App's
        "VIRTUAL_ENV",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONEXECUTABLE",
        "PYTHONSTARTUP",
        # the test this process is running, if it is running one
        "PYTEST_CURRENT_TEST",
        # the server this process is serving, if it is serving one
        "NICEGUI_HOST",
        "NICEGUI_PORT",
        "NICEGUI_PROTOCOL",
        "NICEGUI_SCREEN_TEST_PORT",
    }
)
"""Variables that describe Studio's own process rather than the App's.

A launcher hands a child the environment the child is entitled to. Passing on
what describes the launcher misdescribes the child: an App told it runs in
Studio's virtual environment, or that it is running Studio's current test, behaves
as something it is not. Removing them is what keeps the isolation Studio exists
to provide. A parent's own configuration belongs to the same category: it
describes the parent, not the child it starts.
"""


def child_environment() -> dict[str, str]:
    """Return the environment a started App is entitled to.

    Also drops every `VIBEPY_`-prefixed variable: that is Studio's own rendered
    configuration, which describes Studio's process, not the child's.
    """
    return {
        name: value
        for name, value in os.environ.items()
        if name not in DESCRIBES_THIS_PROCESS and not name.startswith(ENV_PREFIX)
    }


@dataclass(frozen=True, kw_only=True)
class Completed:
    """What one finished child left: its exit code and both streams, decoded."""

    returncode: int
    stdout: str
    stderr: str


class NotRunnable(Exception):
    """The program a command names is neither on PATH nor a file."""

    def __init__(self, program: str) -> None:
        """Record `program` for the message."""
        super().__init__(f"{program} is not available")
        self.program = program


def is_runnable(program: str, /) -> bool:
    """Whether a program is on PATH or is itself a file, as an environment's Python is."""
    return shutil.which(program) is not None or Path(program).is_file()


async def run(
    command: Sequence[str], /, *, stdin: str | None = None, env: Mapping[str, str] | None = None
) -> Completed:
    """Run one command to completion and return what it left.

    Every child receives `child_environment()` with `env` laid over it, so what
    describes Studio's own process describes no child and what the caller hands
    the child reaches it. Standard output and standard error are returned
    apart, unmerged, so a report a child wrote to standard error stays separate
    from what it wrote to standard output.
    """
    if not await asyncio.to_thread(is_runnable, command[0]):
        raise NotRunnable(command[0])
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL if stdin is None else asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**child_environment(), **(env or {})},
    )
    out, err = await process.communicate(None if stdin is None else stdin.encode())
    return Completed(
        returncode=process.returncode if process.returncode is not None else 0,
        stdout=out.decode(errors="replace"),
        stderr=err.decode(errors="replace"),
    )


def reported(text: str, /) -> ErrorInfo | None:
    """Return the failure a child described in `text`, found by parsing, not position.

    The report is one line among whatever else the child wrote, and a traceback
    the framework writes after it is as much a part of that output as the report.
    Scanning in reverse finds the report regardless of what follows it.
    """
    for line in reversed(text.splitlines()):
        found = read_report_line(line)
        if found is not None:
            return found
    return None
