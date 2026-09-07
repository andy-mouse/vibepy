"""The Web routes a human reaches, and the single render path behind them.

``docs/architecture/adapters.md`` gives this adapter four jobs: project
PageDefinitions into routes, construct PageContext, run PageHandlers in the
NiceGUI lifecycle, and connect Page interaction to ToolRuntime. Only the first
is work this module does itself: ``docs/architecture/page-model.md`` gives
PageContext creation to PageRuntime, and the ToolInvoker a Page receives is
already backed by ToolRuntime.

Registering routes is not running a server. Startup belongs to the runtime
lifecycle; see docs/decisions/ADR-012-nicegui-adapter-registers-routes.md.
"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from vibepy.errors import PageRouteConflictError, PageRouteInvalidError
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime


def register_pages(*, registry: PageRegistry, runtime: PageRuntime) -> None:
    """Project every declared Page onto a NiceGUI route.

    Every declaration is validated before any route is registered, so a
    rejected registry leaves no half-registered application behind.
    """
    definitions = registry.definitions()
    claimed: dict[str, str] = {}
    for definition in definitions:
        if not definition.route.startswith("/"):
            raise PageRouteInvalidError(definition.name, definition.route)
        owner = claimed.get(definition.route)
        if owner is not None:
            raise PageRouteConflictError(definition.route, owner, definition.name)
        claimed[definition.route] = definition.name

    for definition in definitions:
        ui.page(definition.route, title=definition.title)(_builder(runtime, definition.name))


def _builder(runtime: PageRuntime, name: str) -> Callable[[], Awaitable[None]]:
    """The page builder NiceGUI calls per visitor.

    Addressed by name rather than by route, so a route change never reaches
    PageRuntime.
    """

    async def build() -> None:
        await runtime.render(name)

    return build
