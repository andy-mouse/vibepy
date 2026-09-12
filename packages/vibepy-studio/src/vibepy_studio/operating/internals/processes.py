"""The child processes this window started.

Only a parent observes its own children: `subprocess` documents `poll`, `wait`,
`terminate` and `kill`, and documents no way to observe an arbitrary pid. So a
child is this window's resource, released when the window closes, and status
answers for what this window started.

A child is owned from the moment it exists, so nothing between the spawn and the
first answer can leave one this window cannot release.
"""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from vibepy_core.app.config import environment_for
from vibepy_core.errors import ErrorInfo
from vibepy_studio.internals.processes import child_environment, reported

logger = logging.getLogger(__name__)

STOP_TIMEOUT = 10.0
READY_TIMEOUT = 30.0
READY_INTERVAL = 0.1


class StartFailed(Exception):
    """A started App never answered. Carries what the child did."""

    def __init__(self, reason: str, *, reported: ErrorInfo | None = None) -> None:
        """Record `reason` and what the child, if any, `reported`."""
        super().__init__(reason)
        self.reason = reason
        self.reported = reported


class AlreadyStarted(StartFailed):
    """This window already holds a child under that name.

    A `StartFailed`, because it is a start that did not happen, and its own type
    because a caller answers it differently: nothing is wrong with the App, and
    the App it names is the one already there.
    """


def _log_path(logs: Path, known_as: str, /) -> Path:
    logs.mkdir(parents=True, exist_ok=True)
    return logs / f"{known_as}.log"


def _reported(path: Path, /) -> ErrorInfo | None:
    """Read the child's log and return what `reported` finds in it."""
    try:
        written = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return reported(written)


@dataclass(kw_only=True)
class _Child:
    """One started App: the process, and whether it has answered.

    The port is not here. It belongs to the installation and the Hub holds it;
    this window is told which port to serve on and needs no memory of it.
    """

    process: asyncio.subprocess.Process
    answering: bool = False


class Processes:
    """One window's running Apps."""

    def __init__(self, *, logs: Path) -> None:
        """Start with no App running, writing child output under `logs`."""
        self._running: dict[str, _Child | None] = {}
        self._logs = logs

    def _forget_if_gone(self, app_name: str, /) -> None:
        """Drop a name whose child has exited.

        A child that left is not this window's to hold, and forgetting it here
        rather than in each caller is what keeps one name addressing one live
        child: an App that crashed can be started again.
        """
        child = self._running.get(app_name)
        if child is not None and child.process.returncode is not None:
            del self._running[app_name]

    def _held(self, app_name: str, /) -> _Child | None:
        """Return the child filed under a name, once there is one to hold."""
        self._forget_if_gone(app_name)
        return self._running.get(app_name)

    def running(self, app_name: str, /) -> bool:
        """Whether an App is serving.

        The port it serves on is the Hub's fact, held in its state and published
        as an address; this window only knows whether the child has answered.
        """
        child = self._held(app_name)
        return child is not None and child.answering

    def taken(self, app_name: str, /) -> bool:
        """Whether this window has claimed a name.

        A name is claimed from before the spawn until its child leaves, so this
        is wider than `running`, which reports nothing for a child that has not
        answered yet. The claim is the key's presence: the
        entry holds nothing until there is a child to put in it.
        """
        self._forget_if_gone(app_name)
        return app_name in self._running

    def owned(self, app_name: str, /) -> asyncio.subprocess.Process | None:
        """Return the child this window holds for an App, serving or not yet serving.

        `running` answers only for a child that has answered. Ownership begins
        earlier, and a caller that must not start a second child under one name
        -- or a test that must see the first -- asks this.
        """
        child = self._held(app_name)
        return None if child is None else child.process

    async def _release(self, known_as: str, /) -> None:
        """Give up a claimed name, killing and reaping its child if it got one."""
        child = self._running.pop(known_as, None)
        if child is None:
            return
        if child.process.returncode is None:
            child.process.kill()
        await child.process.wait()

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
        config: Mapping[str, JsonValue],
        known_as: str,
        port: int,
    ) -> None:
        """Serve one App on the port it was given, in an environment of its own.

        `app_name` is the name the App declares itself under, which is what its
        environment answers to; `known_as` is what this Hub filed it under. The
        two need not match, because a folder's name is not a declaration.

        One name holds one child. The name is claimed with nothing awaited
        between the test and the claim, which is what makes it hold: the loop
        cannot reach a second caller in between. The entry holds nothing until
        the child exists.

        The configuration reaches the child as `VIBEPY_<FIELD>` variables,
        rendered by `environment_for`, laid over the environment the child is
        entitled to (`docs/architecture/packaging.md`, Configuration).

        The child's standard error goes to a file of its own, which is what a
        process supervisor does (<http://supervisord.org/configuration.html>). A
        pipe would have to be drained for as long as the child lives, because a
        child that fills the buffer blocks.
        """
        if self.taken(known_as):
            raise AlreadyStarted(f"{known_as!r} is already started here")
        self._running[known_as] = None
        path = await asyncio.to_thread(_log_path, self._logs, known_as)
        handle = await asyncio.to_thread(path.open, "wb")
        try:
            process = await asyncio.create_subprocess_exec(
                str(interpreter),
                "-m",
                "vibepy_core.serve",
                app_name,
                "--port",
                str(port),
                stdin=asyncio.subprocess.DEVNULL,
                stderr=handle,
                env={**child_environment(), **environment_for(config)},
            )
        finally:
            await asyncio.to_thread(handle.close)
        child = _Child(process=process)
        self._running[known_as] = child
        try:
            await self._wait_until_answering(process, port)
        except StartFailed as failure:
            await self._release(known_as)
            raise StartFailed(
                failure.reason, reported=await asyncio.to_thread(_reported, path)
            ) from failure
        except BaseException:
            await self._release(known_as)
            raise
        child.answering = True
        logger.info("started %s on port %d", known_as, port)

    async def stop(self, app_name: str, /) -> bool:
        """Terminate one App, then kill it if it does not leave."""
        child = self._running.pop(app_name, None)
        if child is None:
            return False
        process = child.process
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
