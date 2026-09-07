from collections.abc import Awaitable, Mapping
from dataclasses import FrozenInstanceError, fields

import pytest
from pydantic import BaseModel

from vibepy.errors import PageNotFoundError, VibepyError
from vibepy.page import Page, PageContext, PageDefinition


class RecordingInvoker:
    """A ToolInvoker that records calls instead of reaching a ToolRuntime."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        self.calls.append((name, raw_input))
        raise AssertionError("this fixture records calls and never returns a result")


def todos_definition() -> PageDefinition:
    return PageDefinition(name="todos", route="/todos", title="Todos")


def test_page_definition_declares_its_metadata() -> None:
    definition = todos_definition()

    assert definition.name == "todos"
    assert definition.route == "/todos"
    assert definition.title == "Todos"


def test_page_context_is_immutable() -> None:
    ctx = PageContext(tools=RecordingInvoker())

    with pytest.raises(FrozenInstanceError):
        ctx.tools = RecordingInvoker()  # type: ignore[misc]


def test_page_context_exposes_nothing_but_its_tool_invoker() -> None:
    assert [field.name for field in fields(PageContext)] == ["tools"]


async def test_handler_protocol_accepts_a_plain_async_function() -> None:
    seen: list[PageContext] = []

    async def handler(ctx: PageContext) -> None:
        seen.append(ctx)

    page = Page(definition=todos_definition(), handler=handler)
    ctx = PageContext(tools=RecordingInvoker())

    await page.handler(ctx)

    assert seen == [ctx]


def test_page_not_found_error_carries_the_page_name() -> None:
    error = PageNotFoundError("todos")

    assert error.page_name == "todos"
    assert isinstance(error, VibepyError)
