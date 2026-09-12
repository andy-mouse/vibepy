"""The path that runs a Page's human-facing implementation.

A Page reaches a Tool through PageContext and ToolInvoker, so PageRuntime owns
PageContext creation and hands the Page the canonical invocation path itself.

Who a render is for is the render's, not the Page's: PageRuntime is given a
principal per render and binds it into the invoker the Page receives, so a Page
cannot choose whom it invokes as.
"""

from collections.abc import Awaitable, Mapping

from pydantic import BaseModel

from vibepy_core.page.model import PageContext, PrincipalToolInvoker, ToolInvoker
from vibepy_core.page.registry import PageRegistry
from vibepy_core.principal import Principal


class _BoundInvoker:
    """A ToolInvoker that invokes as one principal. Built per render, never by a Page."""

    def __init__(self, tools: PrincipalToolInvoker, principal: Principal) -> None:
        """Hold the invoker to reach and the `principal` every call will carry."""
        self._tools = tools
        self._principal = principal

    def invoke(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        """Invoke `name` with `raw_input` as the principal this was bound to."""
        return self._tools.invoke(name, raw_input, principal=self._principal)


class PageRuntime:
    """Resolves a Page by name, creates its PageContext, and runs its handler.

    ``tools`` is typed by the PrincipalToolInvoker Protocol, which ToolRuntime
    satisfies. The Page package therefore depends on the shape of Tool invocation
    and not on the Tool runtime, which is why that Protocol exists.

    Holds no per-Page state and does not serialize renders.
    """

    def __init__(self, *, registry: PageRegistry, tools: PrincipalToolInvoker) -> None:
        """Hold `registry` and the invoker every render binds its principal into."""
        self._registry = registry
        self._tools = tools

    async def render(self, name: str, /, *, principal: Principal) -> None:
        """Resolve `name`, build its PageContext for `principal`, and run its handler.

        Raises:
            PageNotFoundError: no Page is registered under `name`.
        """
        page = self._registry.resolve(name)
        bound: ToolInvoker = _BoundInvoker(self._tools, principal)
        ctx = PageContext(tools=bound)
        await page.handler(ctx)
