"""The Web routes a human reaches, and the single render path behind them.

Route validation reads the declaration; the builders close over the PageRuntime
the caller's window yielded. Registration therefore happens inside that window,
and a builder can only render while its runtime lives. Registration itself is not
undone: it mutates the Web technology's process-global route table, which one
process holds for one App.

NiceGUI documents no lifespan and mounts as a sub-application, and Starlette does
not document lifespan state reaching one, so nothing here reads request state. A
closure is a language guarantee rather than a library one. See
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`.

Registering routes is not running a server.
"""

from collections.abc import Awaitable, Callable

from nicegui import ui
from pydantic import BaseModel

from vibepy_core.app.model import AppDefinition
from vibepy_core.errors import PageRouteConflictError, PageRouteInvalidError
from vibepy_core.page.runtime import PageRuntime


def register_pages[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], pages: PageRuntime, /
) -> None:
    """Project every declared Page of one App onto a NiceGUI route.

    Every declaration is validated before any route is registered, so a rejected
    App leaves no half-registered application behind.
    """
    claimed: dict[str, str] = {}
    for page in definition.pages:
        declared = page.definition
        if not declared.route.startswith("/"):
            raise PageRouteInvalidError(declared.name, declared.route)
        owner = claimed.get(declared.route)
        if owner is not None:
            raise PageRouteConflictError(declared.route, owner, declared.name)
        claimed[declared.route] = declared.name

    for page in definition.pages:
        declared = page.definition
        ui.page(declared.route, title=declared.title)(_builder(pages, declared.name))


def _builder(runtime: PageRuntime, name: str) -> Callable[[], Awaitable[None]]:
    """The page builder NiceGUI calls per visitor.

    Addressed by name rather than by route, so a route change never reaches
    PageRuntime.
    """

    async def build() -> None:
        await runtime.render(name)

    return build
