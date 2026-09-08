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
import socket
from collections.abc import Mapping
from pathlib import Path

logger = logging.getLogger(__name__)

STOP_TIMEOUT = 10.0
READY_TIMEOUT = 30.0
READY_INTERVAL = 0.1


class StartFailed(Exception):
    """A started App never answered. Carries what the child did."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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
        """Return once the child answers on its port, or say why it never will.

        Starting means answering: a caller that receives a url can use it, and a
        child that exits — a port taken between the choice and the bind, a
        configuration its window rejected — is reported instead of handed over.
        """
        deadline = asyncio.get_running_loop().time() + READY_TIMEOUT
        while asyncio.get_running_loop().time() < deadline:
            if process.returncode is not None:
                raise StartFailed(f"the App exited with {process.returncode}")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                await asyncio.sleep(READY_INTERVAL)
                continue
            writer.close()
            await writer.wait_closed()
            del reader
            return
        raise StartFailed(f"the App did not answer on port {port} within {READY_TIMEOUT:.0f}s")

    async def start(self, *, app_name: str, interpreter: Path, config: Mapping[str, object]) -> int:
        """Serve one App on a free port, handing it its configuration on stdin.

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
        self._running[app_name] = (process, port)
        logger.info("started %s on port %d", app_name, port)
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
