"""The Web routes a human reaches, and the single render path behind them.

The builders close over the PageRuntime the caller's window yielded.
Registration therefore happens inside that window, and a builder can only
render while its runtime lives. A declaration reaching here already conforms
-- the definition refused any other as it was constructed -- so nothing is
validated before registration.

NiceGUI documents no lifespan and mounts as a sub-application, and Starlette does
not document lifespan state reaching one, so nothing here reads request state. A
closure is a language guarantee rather than a library one.

Registering routes is not running a server.
"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from vibepy_core.app.config import AppConfig
from vibepy_core.app.model import AppDefinition
from vibepy_core.page.runtime import PageRuntime
from vibepy_core.principal import Principal


def register_pages[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], pages: PageRuntime, /, *, principal: Principal
) -> None:
    """Project every declared Page of one App onto a NiceGUI route."""
    for page in definition.pages:
        declared = page.definition
        ui.page(declared.route, title=declared.title)(_builder(pages, declared.name, principal))


def _builder(
    runtime: PageRuntime, name: str, principal: Principal
) -> Callable[[], Awaitable[None]]:
    """Build the page builder NiceGUI calls per visitor.

    Addressed by name rather than by route, so a route change never reaches
    PageRuntime.
    """

    async def build() -> None:
        await runtime.render(name, principal=principal)

    return build
