"""The Hub App: one declaration, one lifespan, one composition root.

The Hub is a platform-tier App. It is built with the framework and depends on it,
and the framework never depends on the Hub.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel

from vibepy_core.app import AppDefinition, AppEntrypoint
from vibepy_hub.internals import HubDeps, Processes
from vibepy_hub.tools import HUB_TOOLS

logger = logging.getLogger(__name__)


class HubConfig(BaseModel):
    """What the Hub requires of its host.

    The root is declared rather than assumed, so a test supplies a temporary
    directory and two Hubs never share one.
    """

    root: Path


@asynccontextmanager
async def hub_lifespan(config: HubConfig) -> AsyncGenerator[HubDeps]:
    """The Hub's resource for the life of one window.

    Acquisition is bound to release, so a window that closes leaves no child
    behind. See `docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md`.
    """
    await asyncio.to_thread(config.root.mkdir, parents=True, exist_ok=True)
    processes = Processes(logs=config.root / "logs")
    try:
        yield HubDeps(root=config.root, processes=processes)
    finally:
        await processes.aclose()


HUB_APP: AppDefinition[HubDeps, HubConfig] = AppDefinition(
    app_id="vibepy-hub",
    name="Hub",
    version="0.1.0",
    config=HubConfig,
    tools=HUB_TOOLS,
    pages=[],
)

APP: AppEntrypoint[HubDeps, HubConfig] = AppEntrypoint(definition=HUB_APP, lifespan=hub_lifespan)
