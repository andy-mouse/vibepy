"""The executable instance of an AppDefinition.

AppRuntime owns application-scoped state: the resource its definition declares,
the two registries filled from that definition, and the two runtimes over them.
Both channel adapters of one App are built from one AppRuntime, so both reach
that one resource.

The resource is created in the constructor. Runtime lifecycle is a later
milestone, and until a start boundary exists there is nowhere else to create it.
See `docs/architecture/lifecycle.md`, which places dependency initialization at
startup.
"""

from vibepy.app.model import AppDefinition
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime


class AppRuntime[DepsT]:
    """Composes one AppDefinition into a running App.

    Holds no lifecycle state. Constructing an AppRuntime starts no server and no
    adapter; a channel adapter is built from the AppRuntime, not by it.

    The application-scoped resource is not exposed. A Tool handler receives it
    through its ToolContext, and nothing else needs it.
    """

    def __init__(self, definition: AppDefinition[DepsT]) -> None:
        self._definition = definition
        self._dependencies = definition.create_dependencies()

        tool_registry: ToolRegistry[DepsT] = ToolRegistry()
        for tool in definition.tools:
            tool_registry.register(tool)
        self._tool_registry = tool_registry
        self._tool_runtime = ToolRuntime(
            app_id=definition.app_id,
            registry=tool_registry,
            dependencies=self._dependencies,
        )

        page_registry = PageRegistry()
        for page in definition.pages:
            page_registry.register(page)
        self._page_registry = page_registry
        self._page_runtime = PageRuntime(registry=page_registry, tool_runtime=self._tool_runtime)

    @property
    def definition(self) -> AppDefinition[DepsT]:
        return self._definition

    @property
    def tool_registry(self) -> ToolRegistry[DepsT]:
        return self._tool_registry

    @property
    def tool_runtime(self) -> ToolRuntime[DepsT]:
        return self._tool_runtime

    @property
    def page_registry(self) -> PageRegistry:
        return self._page_registry

    @property
    def page_runtime(self) -> PageRuntime:
        return self._page_runtime
