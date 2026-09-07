"""The path that runs a Page's human-facing implementation.

A Page reaches a Tool through PageContext and ToolInvoker, so PageRuntime owns
PageContext creation and hands the Page an invoker backed by the Tool runtime.
"""

from collections.abc import Awaitable, Mapping
from typing import Protocol

from pydantic import BaseModel

from vibepy.page.model import PageContext
from vibepy.page.registry import PageRegistry


class ToolInvocation(Protocol):
    """The shape of the canonical Tool invocation path, as ToolRuntime implements it.

    PageRuntime depends on the shape rather than on ToolRuntime itself, for the
    reason ToolInvoker exists: the Page package describes what it needs of Tool
    invocation and does not import the Tool runtime. It also keeps the
    application-scoped dependency type out of the Page package, which has no use
    for it.
    """

    def invoke(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]: ...


class _ToolRuntimeInvoker:
    """The ToolInvoker a Page receives. Forwards to the Tool runtime and adds nothing.

    Not async itself: ``ToolRuntime.invoke`` already returns the awaitable the
    ToolInvoker Protocol declares.
    """

    def __init__(self, tool_runtime: ToolInvocation) -> None:
        self._tool_runtime = tool_runtime

    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        return self._tool_runtime.invoke(name, raw_input)


class PageRuntime:
    """Resolves a Page by name, creates its PageContext, and runs its handler.

    Holds no per-Page state and does not serialize renders.
    """

    def __init__(self, *, registry: PageRegistry, tool_runtime: ToolInvocation) -> None:
        self._registry = registry
        self._tools = _ToolRuntimeInvoker(tool_runtime)

    async def render(self, name: str) -> None:
        page = self._registry.resolve(name)
        ctx = PageContext(tools=self._tools)
        await page.handler(ctx)
