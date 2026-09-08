"""The executable instance of an AppDefinition.

AppRuntime owns application-scoped state: the resource its definition's lifespan
yields, the two registries filled from that definition, and the two runtimes over
them. Both channel adapters of one App are built from one AppRuntime, so both
reach that one resource.

The registries are filled at construction because they are made of declarations.
The resource is acquired at startup, which is where
`docs/architecture/lifecycle.md` places it, so the runtimes over it exist only
while the App is RUNNING.
"""

from contextlib import AsyncExitStack

from vibepy.app.model import AppDefinition
from vibepy.errors import AppRuntimeNotRunningError, AppRuntimeTransitionError
from vibepy.lifecycle import AppRuntimeState
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime


class AppRuntime[DepsT]:
    """Composes one AppDefinition into a running App.

    Constructing an AppRuntime acquires nothing, starts no server and no adapter.
    A channel adapter is built from a started AppRuntime, because it reads the
    runtimes startup produced.

    The application-scoped resource is not exposed. A Tool handler receives it
    through its ToolContext, and nothing else needs it.

    Startup and shutdown unwind through one AsyncExitStack, so a step that did not
    complete has nothing to unwind and later steps register themselves the same
    way.
    """

    def __init__(self, definition: AppDefinition[DepsT]) -> None:
        self._definition = definition
        self._state = AppRuntimeState.CREATED
        self._stack = AsyncExitStack()
        self._tool_runtime: ToolRuntime[DepsT] | None = None
        self._page_runtime: PageRuntime | None = None

        tool_registry: ToolRegistry[DepsT] = ToolRegistry()
        for tool in definition.tools:
            tool_registry.register(tool)
        self._tool_registry = tool_registry

        page_registry = PageRegistry()
        for page in definition.pages:
            page_registry.register(page)
        self._page_registry = page_registry

    @property
    def state(self) -> AppRuntimeState:
        return self._state

    async def start(self) -> None:
        """Acquire the app-scoped resource and build the runtimes over it.

        The transition to STARTING is synchronous and precedes the first await, so
        a second caller observes a state that forbids starting rather than
        entering a second lifespan.
        """
        if self._state is not AppRuntimeState.CREATED:
            raise AppRuntimeTransitionError(self._definition.plugin_id, self._state, "start")
        self._state = AppRuntimeState.STARTING

        try:
            dependencies = await self._stack.enter_async_context(self._definition.lifespan())
        except BaseException:
            await self._stack.aclose()
            self._state = AppRuntimeState.STOPPED
            raise

        tool_runtime = ToolRuntime(
            plugin_id=self._definition.plugin_id,
            registry=self._tool_registry,
            dependencies=dependencies,
        )
        self._tool_runtime = tool_runtime
        self._page_runtime = PageRuntime(registry=self._page_registry, tools=tool_runtime)
        self._state = AppRuntimeState.RUNNING

    async def stop(self) -> None:
        """Unwind what startup acquired, in reverse."""
        if self._state is not AppRuntimeState.RUNNING:
            raise AppRuntimeTransitionError(self._definition.plugin_id, self._state, "stop")
        self._state = AppRuntimeState.STOPPING

        try:
            await self._stack.aclose()
        finally:
            self._tool_runtime = None
            self._page_runtime = None
            self._state = AppRuntimeState.STOPPED

    @property
    def definition(self) -> AppDefinition[DepsT]:
        return self._definition

    @property
    def tool_registry(self) -> ToolRegistry[DepsT]:
        return self._tool_registry

    @property
    def page_registry(self) -> PageRegistry:
        return self._page_registry

    @property
    def tool_runtime(self) -> ToolRuntime[DepsT]:
        if self._tool_runtime is None:
            raise AppRuntimeNotRunningError(self._definition.plugin_id, self._state)
        return self._tool_runtime

    @property
    def page_runtime(self) -> PageRuntime:
        if self._page_runtime is None:
            raise AppRuntimeNotRunningError(self._definition.plugin_id, self._state)
        return self._page_runtime
