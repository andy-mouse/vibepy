"""The path that runs a Page's human-facing implementation.

A Page reaches a Tool through PageContext and ToolInvoker, so PageRuntime owns
PageContext creation and hands the Page an invoker backed by ToolRuntime.
"""

from collections.abc import Awaitable, Mapping

from pydantic import BaseModel

from vibepy.page.model import PageContext
from vibepy.page.registry import PageRegistry
from vibepy.tool.runtime import ToolRuntime


class _ToolRuntimeInvoker:
    """The ToolInvoker a Page receives. Forwards to ToolRuntime and adds nothing.

    Not async itself: ``ToolRuntime.invoke`` already returns the awaitable the
    ToolInvoker Protocol declares.
    """

    def __init__(self, tool_runtime: ToolRuntime) -> None:
        self._tool_runtime = tool_runtime

    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        return self._tool_runtime.invoke(name, raw_input)


class PageRuntime:
    """Resolves a Page by name, creates its PageContext, and runs its handler.

    Holds no per-Page state and does not serialize renders.
    """

    def __init__(self, *, registry: PageRegistry, tool_runtime: ToolRuntime) -> None:
        self._registry = registry
        self._tools = _ToolRuntimeInvoker(tool_runtime)

    async def render(self, name: str) -> None:
        page = self._registry.resolve(name)
        ctx = PageContext(tools=self._tools)
        await page.handler(ctx)
