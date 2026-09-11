"""The Studio App: one declaration, one lifespan, one composition root.

Studio is a platform-tier App. It is built with the framework and depends on it,
and the framework never depends on Studio.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel, Field

from vibepy_core import AppDefinition, AppEntrypoint
from vibepy_studio.consumption.internals import Processes, StudioDeps, write_install_config
from vibepy_studio.consumption.pages.board import BOARD
from vibepy_studio.consumption.tools import HUB_TOOLS

logger = logging.getLogger(__name__)


class StudioConfig(BaseModel):
    """What the Hub requires of its host.

    The root is declared rather than assumed, so a test supplies a temporary
    directory and two Hubs never share one. `proxy_port` is declared for the
    same reason and one more: it is part of every address the Hub answers with,
    and a Hub that assumed it would publish addresses reaching nothing, or
    something else, without ever being told.
    """

    root: Path
    proxy_port: int = Field(default=8080, ge=1, le=65535)
    """Bounded because the Hub never learns that the proxy failed to bind: it
    owns no proxy, so a port that cannot be one has to be refused here."""


@asynccontextmanager
async def studio_lifespan(config: StudioConfig) -> AsyncGenerator[StudioDeps]:
    """Acquire the Hub's resource for the life of one window."""
    await asyncio.to_thread(config.root.mkdir, parents=True, exist_ok=True)
    await write_install_config(config.root, proxy_port=config.proxy_port)
    processes = Processes(logs=config.root / "logs")
    try:
        yield StudioDeps(root=config.root, processes=processes, proxy_port=config.proxy_port)
    finally:
        await processes.aclose()


STUDIO_APP: AppDefinition[StudioDeps, StudioConfig] = AppDefinition(
    app_id="vibepy-studio",
    name="Studio",
    version="0.1.0",
    config=StudioConfig,
    tools=HUB_TOOLS,
    pages=[BOARD],
)

APP: AppEntrypoint[StudioDeps, StudioConfig] = AppEntrypoint(
    definition=STUDIO_APP, lifespan=studio_lifespan
)
