"""Declarations of the Page model. These types carry no invocation behaviour."""

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class ToolInvoker(Protocol):
    """The narrow interface a Page invokes Tools through.

    The signature is ``ToolRuntime.invoke``'s: a raw mapping in, a validated output
    model out. Validation stays inside ToolRuntime, so no second validation path
    exists, and a Page sees nothing of the runtime beyond this one operation.

    Name included. ToolRuntime satisfies this Protocol structurally, so nothing
    stands between a Page and the canonical invocation path, and the Page package
    still imports no Tool runtime.
    """

    def invoke(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]: ...


@dataclass(frozen=True)
class PageContext:
    """Page-scoped context. Created by PageRuntime, never by a Page or a channel."""

    tools: ToolInvoker


@dataclass(frozen=True)
class PageDefinition:
    """Static declaration of a Page.

    ``name`` is the identifier the framework addresses the Page by. ``route`` and
    ``title`` are consumed by the Web channel adapter, which does not exist yet.
    """

    name: str
    route: str
    title: str


class PageHandler(Protocol):
    """The human-facing implementation behind a Page.

    Returns ``None``: a Page builds its interface by side effect, as NiceGUI page
    builders do. Parameters are positional-only so that an app author may name them
    freely.
    """

    def __call__(self, ctx: PageContext, /) -> Awaitable[None]: ...


@dataclass(frozen=True)
class Page:
    """A PageDefinition paired with the handler that implements it.

    Not generic: a PageHandler declares no input or output model, so every Page
    already shares one static type and needs no binding step before storage.
    """

    definition: PageDefinition
    handler: PageHandler
