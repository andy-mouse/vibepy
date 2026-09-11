"""The ASGI application that serves one App's Pages.

Registering routes is not running a server, and neither is this: the application
is built and handed back, and whoever owns the process runs it. The MCP adapter
builds an SDK server object the same way.

The window a channel runs in is the application's own lifespan, so a window that
will not open fails the server's startup rather than leaving it answering: ASGI
defines that a server seeing `lifespan.startup.failed` logs the message and exits
(<https://asgi.readthedocs.io/en/latest/specs/lifespan.html>). The Web
technology's own startup hook carries no such meaning: its documentation says
when the hook runs and nothing about a hook that raises.
"""

import json
import logging
from collections.abc import AsyncGenerator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from nicegui import ui

from vibepy_core.adapters.nicegui.web import register_pages
from vibepy_core.app.composition import Lifespan, page_runtime_for
from vibepy_core.app.config import AppConfig
from vibepy_core.app.model import AppDefinition
from vibepy_core.errors import to_error_info

logger = logging.getLogger(__name__)


def build_web_app[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> FastAPI:
    """Build the Web projection of one App's Pages.

    NiceGUI documents mounting into an application of one's own as
    `ui.run_with(app)`, which is what lets the window be that application's
    lifespan. A builder closes over the PageRuntime the window yielded, so a
    render outside the window is unreachable; the routes themselves are
    registered on the process-global table and are not removed when the window
    closes.
    """

    @asynccontextmanager
    async def window(_served: FastAPI) -> AsyncGenerator[None]:
        async with AsyncExitStack() as opening:
            try:
                pages = await opening.enter_async_context(
                    page_runtime_for(definition, lifespan, config=config)
                )
                register_pages(definition, pages)
            except Exception as failure:
                _report(failure)
                raise
            yield

    served = FastAPI(lifespan=window)
    ui.run_with(served)  # pyright: ignore[reportUnknownMemberType]
    return served


def _report(failure: Exception, /) -> None:
    """Describe a window that will not open, where its host can read it.

    ASGI's answer for a window that fails is that the server logs the message
    and exits, which is legible to a person and not to a caller. So the window
    describes itself in the framework's own shape first. Nothing is translated
    and nothing is swallowed: the exception propagates as raised, and this is a
    log record beside it.
    """
    info = to_error_info(failure)
    logger.error(
        json.dumps(
            {
                "code": info.code,
                "category": info.category,
                "message": info.message,
                "details": dict(info.details),
            }
        )
    )
