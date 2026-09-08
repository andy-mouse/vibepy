"""The window in which one channel of one Plugin is running.

A declaration is paired with a lifespan here and nowhere else. What the pairing
produces exists for the duration of an ``async with`` block and cannot be reached
outside it, so the framework needs no lifecycle state and no error for a runtime
that is not running. See
`docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md`.

Each function yields the one runtime its channel needs. Registries are built from
declarations alone, so they are made once, before the resource is acquired.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime
from vibepy.plugin.model import PluginDefinition
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime

type Lifespan[DepsT] = Callable[[], AbstractAsyncContextManager[DepsT]]
"""A factory returning the plugin's resource for the life of one window.

What precedes the ``yield`` runs as the window opens and what follows runs as it
closes. Acquisition and release cannot be declared apart, which is what lets a
channel release a resource whose type it does not know. See
`docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md`.
"""


def tool_registry_for[DepsT](definition: PluginDefinition[DepsT], /) -> ToolRegistry[DepsT]:
    """Fill a ToolRegistry from declarations. Reads no resource."""
    registry: ToolRegistry[DepsT] = ToolRegistry()
    for tool in definition.tools:
        registry.register(tool)
    return registry


def page_registry_for[DepsT](definition: PluginDefinition[DepsT], /) -> PageRegistry:
    """Fill a PageRegistry from declarations. Reads no resource."""
    registry = PageRegistry()
    for page in definition.pages:
        registry.register(page)
    return registry


@asynccontextmanager
async def tool_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AsyncGenerator[ToolRuntime[DepsT]]:
    """The Agent channel's window: one ToolRuntime over one acquired resource."""
    registry = tool_registry_for(definition)
    async with lifespan() as dependencies:
        yield ToolRuntime(
            plugin_id=definition.plugin_id, registry=registry, dependencies=dependencies
        )


@asynccontextmanager
async def page_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AsyncGenerator[PageRuntime]:
    """The Web channel's window: one PageRuntime over that same invocation path.

    A Page reaches Tools through ToolInvoker, which ToolRuntime satisfies, so the
    Web channel gets the canonical invocation path without seeing the runtime.
    """
    registry = page_registry_for(definition)
    async with tool_runtime_for(definition, lifespan) as tools:
        yield PageRuntime(registry=registry, tools=tools)
