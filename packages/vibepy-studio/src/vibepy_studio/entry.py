"""The Studio App: one declaration, one lifespan, one composition root.

Studio is a platform-tier App. It is built with the framework and depends on it,
and the framework never depends on Studio.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import Field

from vibepy_core import AppConfig, AppDefinition, AppEntrypoint
from vibepy_studio.authoring.tools import AUTHORING_TOOLS
from vibepy_studio.operating.internals import Processes, StudioDeps, StudioRoot
from vibepy_studio.operating.pages.board import BOARD
from vibepy_studio.operating.tools import OPERATING_TOOLS

logger = logging.getLogger(__name__)


class StudioConfig(AppConfig):
    """What Studio requires of its host.

    The root is declared rather than assumed, so a test supplies a temporary
    directory and two Studios never share one. `proxy_port` is declared for the
    same reason and one more: it is part of every address Studio answers with,
    and a Studio that assumed it would publish addresses reaching nothing, or
    something else, without ever being told.
    """

    root: Path
    proxy_port: int = Field(default=8080, ge=1, le=65535)
    """Bounded because Studio never learns that the proxy failed to bind: it
    owns no proxy, so a port that cannot be one has to be refused here."""


@asynccontextmanager
async def studio_lifespan(config: StudioConfig) -> AsyncGenerator[StudioDeps]:
    """Acquire Studio's resource for the life of one window."""
    root = StudioRoot(path=config.root)
    await root.prepare(proxy_port=config.proxy_port)
    processes = Processes(logs=config.root / "logs")
    try:
        yield StudioDeps(root=root, processes=processes, proxy_port=config.proxy_port)
    finally:
        await processes.aclose()


STUDIO_APP: AppDefinition[StudioDeps, StudioConfig] = AppDefinition(
    app_id="vibepy-studio",
    name="Studio",
    version="0.1.0",
    config=StudioConfig,
    tools=[*OPERATING_TOOLS, *AUTHORING_TOOLS],
    pages=[BOARD],
)

APP: AppEntrypoint[StudioDeps, StudioConfig] = AppEntrypoint(
    definition=STUDIO_APP, lifespan=studio_lifespan
)
