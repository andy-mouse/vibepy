"""The child processes this window started.

Only a parent observes its own children: `subprocess` documents `poll`, `wait`,
`terminate` and `kill`, and documents no way to observe an arbitrary pid. So a
child is this window's resource, released when the window closes, and status
answers for what this window started — the same reading
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` gives the Agent
channel's processes.
"""

import asyncio
import json
import logging
import os
import socket
from collections.abc import Mapping
from pathlib import Path

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
"""Variables that describe the Hub's own process rather than the App's.

A launcher hands a child the environment the child is entitled to. Passing on
what describes the launcher misdescribes the child: an App told it runs in the
Hub's virtual environment, or that it is running the Hub's current test, behaves
as something it is not. Removing them is what keeps the isolation the Hub exists
to provide — see
`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`.
"""

STOP_TIMEOUT = 10.0
READY_TIMEOUT = 30.0
READY_INTERVAL = 0.1


class StartFailed(Exception):
    """A started App never answered. Carries what the child did."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def child_environment() -> dict[str, str]:
    """The environment a started App is entitled to."""
    return {name: value for name, value in os.environ.items() if name not in DESCRIBES_THIS_PROCESS}


def free_port() -> int:
    """A port nothing is listening on, chosen by the operating system.

    NiceGUI documents no way to report back the port it chose, so the Hub
    chooses one and passes it. A port taken between the choice and the bind is a
    child that exits, which `running` then reports as not running.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Processes:
    """One window's running Apps."""

    def __init__(self) -> None:
        self._running: dict[str, tuple[asyncio.subprocess.Process, int]] = {}

    def running(self, app_name: str, /) -> int | None:
        """The port an App is serving on, or nothing when it is not running."""
        found = self._running.get(app_name)
        if found is None:
            return None
        process, port = found
        if process.returncode is not None:
            del self._running[app_name]
            return None
        return port

    async def _wait_until_answering(
        self, process: asyncio.subprocess.Process, port: int, /
    ) -> None:
        """Return once the child answers a request, or say why it never will.

        A request rather than a connection: a server binds its socket before it
        opens the App's window, so an accepted connection proves only that the
        port is held. An answer proves the window opened, which is what makes a
        configuration the window refuses a failed start rather than a url that
        never works. Any status counts — the Hub asks for a path no App has to
        declare.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + READY_TIMEOUT
        while loop.time() < deadline:
            if process.returncode is not None:
                raise StartFailed(f"the App exited with {process.returncode}")
            if await self._answers(port):
                return
            await asyncio.sleep(READY_INTERVAL)
        raise StartFailed(f"the App did not answer on port {port} within {READY_TIMEOUT:.0f}s")

    @staticmethod
    async def _answers(port: int, /) -> bool:
        """Whether the server on this port answers an HTTP request at all."""
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            return False
        try:
            writer.write(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            await writer.drain()
            answered = await asyncio.wait_for(reader.read(12), timeout=READY_TIMEOUT)
        except (OSError, TimeoutError):
            return False
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        return answered.startswith(b"HTTP/")

    async def start(
        self,
        *,
        app_name: str,
        interpreter: Path,
        config: Mapping[str, object],
        known_as: str,
    ) -> int:
        """Serve one App on a free port, handing it its configuration on stdin.

        `app_name` is the name the App declares itself under, which is what its
        environment answers to; `known_as` is what this Hub filed it under. The
        two need not match, because a folder's name is not a declaration.

        Standard input carries the configuration so that a secret reaches the
        child without a file, an environment variable or an argument vector.
        """
        port = free_port()
        process = await asyncio.create_subprocess_exec(
            str(interpreter),
            "-m",
            "vibepy.serve",
            app_name,
            "--port",
            str(port),
            stdin=asyncio.subprocess.PIPE,
            env=child_environment(),
        )
        if process.stdin is not None:
            process.stdin.write(json.dumps(dict(config)).encode())
            await process.stdin.drain()
            process.stdin.close()
        try:
            await self._wait_until_answering(process, port)
        except StartFailed:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        self._running[known_as] = (process, port)
        logger.info("started %s on port %d", known_as, port)
        return port

    async def stop(self, app_name: str, /) -> bool:
        """Terminate one App, then kill it if it does not leave."""
        found = self._running.pop(app_name, None)
        if found is None:
            return False
        process, _ = found
        if process.returncode is not None:
            return True
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=STOP_TIMEOUT)
        except TimeoutError:
            logger.warning("%s did not stop; killing it", app_name)
            process.kill()
            await process.wait()
        return True

    async def aclose(self) -> None:
        """Release every child this window started."""
        for app_name in list(self._running):
            await self.stop(app_name)
