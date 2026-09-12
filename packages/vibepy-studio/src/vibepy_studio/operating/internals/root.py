"""Studio's root directory, as the operations a handler performs on it.

A Tool handler reaches this through its ToolContext. It holds the path
privately and offers no way to read it, so a handler acts on the root by naming
an operation rather than by holding a path and calling a method of its own. The
paths it returns are `PurePath`, which has no method that touches the file
system (AGENTS.md, Python conventions).

Every operation here is `async` and wraps its blocking work in
`asyncio.to_thread` (`docs/architecture/runtime.md` says why), or is pure.

The one exception is `interpreter`, which computes a path and reads nothing; it
is what `Processes.start` is given, and starting a child is itself async.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path, PurePath

from vibepy_studio.operating.internals.installer import describe as describe_environment
from vibepy_studio.operating.internals.installer import (
    environment,
    environments,
    install,
    installed_facts,
    interpreter,
    purelib,
    read_facts,
    remove_environment,
    write_facts,
)
from vibepy_studio.operating.internals.routing import (
    remove_route,
    write_install_config,
    write_route,
)
from vibepy_studio.operating.internals.state import OperatingState, read_state, write_state
from vibepy_studio.operating.models import AppFacts


class StudioRoot:
    """One Studio root directory and everything a handler does to it."""

    def __init__(self, *, path: Path) -> None:
        """Own `path`, and the lock that serializes changes to the state it holds."""
        self._path = path
        self._state_lock = asyncio.Lock()

    async def prepare(self, *, proxy_port: int) -> None:
        """Make the root and write the half of the proxy's configuration a window owns."""
        await asyncio.to_thread(self._path.mkdir, parents=True, exist_ok=True)
        await write_install_config(self._path, proxy_port=proxy_port)

    async def state(self) -> OperatingState:
        """Return the stored state, or an empty one when nothing readable has been stored."""
        return await read_state(self._path)

    async def update_state(
        self, change: Callable[[OperatingState], OperatingState], /
    ) -> OperatingState:
        """Read, change and store the state, with no other call in between.

        The lock is this root's, which is where application-scoped state belongs.
        """
        async with self._state_lock:
            changed = change(await read_state(self._path))
            await write_state(self._path, changed)
            return changed

    async def installed(self) -> tuple[str, ...]:
        """Return the name of every App this Studio installed, in a stable order."""
        return tuple(env.name for env in await environments(self._path))

    async def is_installed(self, app_name: str, /) -> bool:
        """Whether this App has an environment here."""
        return environment(self._path, app_name) in await environments(self._path)

    async def installed_facts(self, app_name: str, /) -> AppFacts | None:
        """Return what one installed App declared, or nothing when it is not installed."""
        return await installed_facts(self._path, app_name)

    async def facts(self, app_name: str, /) -> AppFacts | None:
        """Return what an environment records about itself, without asking whether it is there."""
        return await read_facts(environment(self._path, app_name))

    async def install(self, app_name: str, /, *, wheel: PurePath, source: PurePath) -> None:
        """Create an environment of its own for this App and install one wheel there."""
        await install(wheel=wheel, source=source, env=environment(self._path, app_name))

    async def describe(self, app_name: str, /) -> tuple[AppFacts, ...]:
        """Return what the Apps in this App's environment declare, read in that environment."""
        return await describe_environment(environment(self._path, app_name))

    async def purelib(self, app_name: str, /) -> PurePath:
        """Return where this App's environment keeps its distribution metadata."""
        return await purelib(environment(self._path, app_name))

    async def write_facts(self, app_name: str, facts: AppFacts, /) -> None:
        """Keep what an App declared beside the environment that holds it."""
        await write_facts(environment(self._path, app_name), facts)

    async def remove_environment(self, app_name: str, /) -> None:
        """Delete one App's environment, if it is there."""
        await remove_environment(environment(self._path, app_name))

    def interpreter(self, app_name: str, /) -> PurePath:
        """Return the Python of this App's environment. Computes a path and reads nothing."""
        return interpreter(environment(self._path, app_name))

    async def write_route(self, app_name: str, /, *, port: int) -> None:
        """Publish one App's route where the proxy's provider is watching."""
        await write_route(self._path, app_name, port=port)

    async def remove_route(self, app_name: str, /) -> None:
        """Withdraw one App's route, if it has one."""
        await remove_route(self._path, app_name)
