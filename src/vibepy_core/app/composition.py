"""The window in which one channel of one App is running.

A declaration is paired with a lifespan here and nowhere else.

`tool_runtime_for` is the invocation window, and it belongs to no channel: every
channel reaches Tools through it. `page_runtime_for` is the Web channel's window,
and it is that window with a PageRegistry over it. Registries are built from
declarations alone, so they are made once, before the resource is acquired.
"""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from pydantic import BaseModel, ValidationError

from vibepy_core.app.model import AppDefinition
from vibepy_core.errors import (
    AppConfigInvalidError,
    PageNameConflictError,
    ToolNameConflictError,
)
from vibepy_core.page.registry import PageRegistry
from vibepy_core.page.runtime import PageRuntime
from vibepy_core.tool.registry import ToolRegistry
from vibepy_core.tool.runtime import ToolRuntime

type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]
"""A factory returning the app's resource for the life of one window.

It receives the App's validated configuration and nothing else.
"""


def tool_registry_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], /
) -> ToolRegistry[DepsT]:
    """Fill a ToolRegistry from declarations. Reads no resource."""
    registry: ToolRegistry[DepsT] = ToolRegistry()
    claimed: set[str] = set()
    for tool in definition.tools:
        name = tool.definition.name
        if name in claimed:
            raise ToolNameConflictError(name)
        claimed.add(name)
        registry.register(tool)
    return registry


def page_registry_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], /
) -> PageRegistry:
    """Fill a PageRegistry from declarations. Reads no resource."""
    registry = PageRegistry()
    claimed: dict[str, str] = {}
    for page in definition.pages:
        declared = page.definition
        owner = claimed.get(declared.name)
        if owner is not None:
            raise PageNameConflictError(declared.name, owner, declared.route)
        claimed[declared.name] = declared.route
        registry.register(page)
    return registry


def _validated[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], raw: Mapping[str, object], /
) -> ConfigT:
    """Validate raw configuration against what the App declared.

    Raised before a lifespan is entered, so a window that cannot run acquires
    nothing.
    """
    try:
        return definition.config.model_validate(dict(raw))
    except ValidationError as error:
        fields = [".".join(str(part) for part in entry["loc"]) for entry in error.errors()]
        raise AppConfigInvalidError(definition.app_id, fields) from error


@asynccontextmanager
async def tool_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AsyncGenerator[ToolRuntime[DepsT]]:
    """Open the invocation window: one ToolRuntime over one acquired resource.

    Channel-neutral, and named so. The Agent channel adds nothing to it and
    hands it straight to its server's lifespan; the Web channel composes over
    it. Calling this one channel's would give a channel-neutral concern a
    channel's name, and then the other channel reaches Tools by borrowing from
    a peer -- which is how it read before, and which left the framework no
    neutral place to put what both channels need.
    """
    registry = tool_registry_for(definition)
    validated = _validated(definition, config)
    async with lifespan(validated) as dependencies:
        yield ToolRuntime(app_id=definition.app_id, registry=registry, dependencies=dependencies)


@asynccontextmanager
async def page_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AsyncGenerator[PageRuntime]:
    """Open the Web channel's window: the invocation window, with Pages over it.

    It opens `tool_runtime_for` rather than repeating it, so configuration is
    validated once and a resource acquired once. A Page reaches Tools through
    ToolInvoker, which ToolRuntime satisfies, so the Web channel gets the
    canonical invocation path without seeing the runtime.
    """
    registry = page_registry_for(definition)
    async with tool_runtime_for(definition, lifespan, config=config) as tools:
        yield PageRuntime(registry=registry, tools=tools)
