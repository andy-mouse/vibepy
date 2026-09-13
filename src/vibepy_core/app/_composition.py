"""The window in which one channel of one App is running.

A declaration is paired with a lifespan here and nowhere else.

`tool_runtime_for` is the invocation window, and it belongs to no channel: every
channel reaches Tools through it. `page_runtime_for` is the Web channel's window,
and it is that window with a PageRegistry over it. Registries are built from
declarations alone, so they are made once, before the resource is acquired.
"""

import logging
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime

from pydantic import ValidationError

from vibepy_core.app._model import AppDefinition
from vibepy_core.app._record import WindowRecord
from vibepy_core.app.config import AppConfig
from vibepy_core.channel import Channel
from vibepy_core.errors import AppConfigInvalidError
from vibepy_core.page._registry import PageRegistry
from vibepy_core.page._runtime import PageRuntime
from vibepy_core.tool._registry import ToolRegistry
from vibepy_core.tool._runtime import ToolRuntime

logger = logging.getLogger(__name__)

type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]
"""A factory returning the app's resource for the life of one window.

It receives the App's configuration, as the window instantiated it, and nothing else.
"""


def tool_registry_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], /
) -> ToolRegistry[DepsT]:
    """Fill a ToolRegistry from declarations. Reads no resource.

    Names are unique: the definition refused any other declaration as it was
    constructed, so this registers and checks nothing.
    """
    registry: ToolRegistry[DepsT] = ToolRegistry()
    for tool in definition.tools:
        registry.register(tool)
    return registry


def page_registry_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], /
) -> PageRegistry:
    """Fill a PageRegistry from declarations. Reads no resource; the definition already conforms."""
    registry = PageRegistry()
    for page in definition.pages:
        registry.register(page)
    return registry


def _validated[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], raw: Mapping[str, object], /
) -> ConfigT:
    """Instantiate the App's configuration from explicit values and the environment.

    Explicit values stand above the environment field by field, in the
    library's documented order. Raised before a lifespan is entered, so a
    window that cannot run acquires nothing.
    """
    try:
        return definition.config(**raw)
    except ValidationError as error:
        fields = [".".join(str(part) for part in entry["loc"]) for entry in error.errors()]
        raise AppConfigInvalidError(definition.app_id, fields) from error


@asynccontextmanager
async def tool_runtime_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
    channel: Channel,
) -> AsyncGenerator[ToolRuntime[DepsT]]:
    """Open the invocation window for one channel: one ToolRuntime over one acquired resource.

    Channel-neutral in what it composes, and named so. `channel` says which
    channel opened the window, and the runtime authorizes against it; it is not
    a branch in a Tool. The Agent channel adds nothing to it and
    hands it straight to its server's lifespan; the Web channel composes over
    it. Calling this one channel's would give a channel-neutral concern a
    channel's name, and then the other channel reaches Tools by borrowing from
    a peer -- which is how it read before, and which left the framework no
    neutral place to put what both channels need.

    Closing writes one `WindowRecord`, after the lifespan has exited, so the line
    witnesses the resource being released rather than the runtime being done
    with. It is written on a clean exit only: a window that ends by raising
    already crosses as one report, and stating the ending twice would give a
    reader two shapes for one fact. Both channels open this window, so both are
    observed by the one writer.
    """
    registry = tool_registry_for(definition)
    validated = _validated(definition, config)
    async with lifespan(validated) as dependencies:
        yield ToolRuntime(
            app_id=definition.app_id,
            registry=registry,
            dependencies=dependencies,
            channel=channel,
            policy=definition.policy,
        )
    closed = WindowRecord(app_id=definition.app_id, channel=channel, closed_at=datetime.now(UTC))
    logger.info(closed.model_dump_json())


@asynccontextmanager
async def page_runtime_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AsyncGenerator[PageRuntime]:
    """Open the Web channel's window: the invocation window, with Pages over it.

    It opens `tool_runtime_for` rather than repeating it, so the configuration
    is instantiated once and a resource acquired once. The window is the Web
    channel's, so it is opened as `Channel.WEB`. A Page reaches Tools through
    PrincipalToolInvoker, which ToolRuntime satisfies, so the Web channel gets the
    canonical invocation path without seeing the runtime.
    """
    registry = page_registry_for(definition)
    async with tool_runtime_for(definition, lifespan, config=config, channel=Channel.WEB) as tools:
        yield PageRuntime(registry=registry, tools=tools)
