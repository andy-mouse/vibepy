"""The ASGI application that serves one App's Pages.

Registering routes is not running a server, and neither is this: the application
is built and handed back, and whoever owns the process runs it. The MCP adapter
builds an SDK server object the same way. See
`docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`.

The window a channel runs in is the application's own lifespan, so a window that
will not open fails the server's startup rather than leaving it answering: ASGI
defines that a server seeing `lifespan.startup.failed` logs the message and exits
(<https://asgi.readthedocs.io/en/latest/specs/lifespan.html>). The Web
technology's own startup hook carries no such meaning: its documentation says
when the hook runs and nothing about a hook that raises.
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI
from nicegui import ui
from pydantic import BaseModel

from vibepy_core.adapters.nicegui.web import register_pages
from vibepy_core.app.composition import Lifespan, page_runtime_for
from vibepy_core.app.model import AppDefinition


def build_web_app[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> FastAPI:
    """Build the Web projection of one App's Pages.

    NiceGUI documents mounting into an application of one's own as
    `ui.run_with(app)`, which is what lets the window be that application's
    lifespan. Routes are registered inside the window and left with it, so a
    builder holds its PageRuntime for exactly as long as the window lasts.
    """

    @asynccontextmanager
    async def window(_served: FastAPI) -> AsyncGenerator[None]:
        async with page_runtime_for(definition, lifespan, config=config) as pages:
            register_pages(definition, pages)
            yield

    served = FastAPI(lifespan=window)
    ui.run_with(served)  # pyright: ignore[reportUnknownMemberType]
    return served
