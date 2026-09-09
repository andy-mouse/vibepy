"""The path that runs a Page's human-facing implementation.

A Page reaches a Tool through PageContext and ToolInvoker, so PageRuntime owns
PageContext creation and hands the Page the canonical invocation path itself.
"""

from vibepy_core.page.model import PageContext, ToolInvoker
from vibepy_core.page.registry import PageRegistry


class PageRuntime:
    """Resolves a Page by name, creates its PageContext, and runs its handler.

    ``tools`` is typed by the ToolInvoker Protocol, which ToolRuntime satisfies.
    The Page package therefore depends on the shape of Tool invocation and not on
    the Tool runtime, which is why that Protocol exists.

    Holds no per-Page state and does not serialize renders.
    """

    def __init__(self, *, registry: PageRegistry, tools: ToolInvoker) -> None:
        self._registry = registry
        self._tools = tools

    async def render(self, name: str) -> None:
        page = self._registry.resolve(name)
        ctx = PageContext(tools=self._tools)
        await page.handler(ctx)
