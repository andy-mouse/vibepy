from collections.abc import Awaitable, Mapping
from dataclasses import FrozenInstanceError, fields

import pytest
from pydantic import BaseModel

from vibepy.errors import (
    PageNotFoundError,
    ToolInputValidationError,
    ToolNotFoundError,
    VibepyError,
)
from vibepy.page import Page, PageContext, PageDefinition, PageRegistry, PageRuntime
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime


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


async def noop_handler(_ctx: PageContext) -> None:
    return None


def test_resolving_an_unregistered_name_raises() -> None:
    registry = PageRegistry()

    with pytest.raises(PageNotFoundError) as raised:
        registry.resolve("todos")

    assert raised.value.page_name == "todos"


def test_a_registered_page_resolves_by_name() -> None:
    registry = PageRegistry()
    page = Page(definition=todos_definition(), handler=noop_handler)
    registry.register(page)

    assert registry.resolve("todos") is page


def test_registering_a_name_twice_replaces_the_earlier_page() -> None:
    registry = PageRegistry()
    registry.register(Page(definition=todos_definition(), handler=noop_handler))
    replacement = Page(
        definition=PageDefinition(name="todos", route="/todo-list", title="Todo list"),
        handler=noop_handler,
    )
    registry.register(replacement)

    assert registry.resolve("todos") is replacement
    assert registry.definitions() == (replacement.definition,)


def test_definitions_enumerates_every_registered_page() -> None:
    registry = PageRegistry()
    todos = Page(definition=todos_definition(), handler=noop_handler)
    archive = Page(
        definition=PageDefinition(name="archive", route="/archive", title="Archive"),
        handler=noop_handler,
    )
    registry.register(todos)
    registry.register(archive)

    assert registry.definitions() == (todos.definition, archive.definition)


class CreateTodoInput(BaseModel):
    title: str


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoStore:
    def __init__(self) -> None:
        self._todos: list[Todo] = []

    def create(self, title: str) -> Todo:
        todo = Todo(id=len(self._todos) + 1, title=title, done=False)
        self._todos.append(todo)
        return todo

    def list(self) -> list[Todo]:
        return list(self._todos)


def create_todo_tool(store: TodoStore) -> Tool[CreateTodoInput, Todo]:
    async def handler(_ctx: ToolContext, payload: CreateTodoInput) -> Todo:
        return store.create(payload.title)

    return Tool(
        definition=ToolDefinition(
            name="create_todo",
            description="Create a todo item",
            input_model=CreateTodoInput,
            output_model=Todo,
        ),
        handler=handler,
    )


def build_page_runtime(registry: PageRegistry, store: TodoStore) -> PageRuntime:
    tool_registry = ToolRegistry()
    tool_registry.register(create_todo_tool(store))
    return PageRuntime(
        registry=registry,
        tool_runtime=ToolRuntime(app_id="todo", registry=tool_registry),
    )


class PageFailed(Exception):
    """Exception owned by the fixture, not by the framework."""


async def test_a_page_reaches_a_tool_through_the_tool_invoker() -> None:
    store = TodoStore()
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.call("create_todo", {"title": "buy milk"})

    registry.register(Page(definition=todos_definition(), handler=handler))

    await build_page_runtime(registry, store).render("todos")

    assert store.list() == [Todo(id=1, title="buy milk", done=False)]


async def test_a_page_receives_the_validated_output_model() -> None:
    store = TodoStore()
    registry = PageRegistry()
    received: list[BaseModel] = []

    async def handler(ctx: PageContext) -> None:
        received.append(await ctx.tools.call("create_todo", {"title": "buy milk"}))

    registry.register(Page(definition=todos_definition(), handler=handler))

    await build_page_runtime(registry, store).render("todos")

    assert received == [Todo(id=1, title="buy milk", done=False)]


async def test_rendering_an_unregistered_page_raises() -> None:
    runtime = build_page_runtime(PageRegistry(), TodoStore())

    with pytest.raises(PageNotFoundError) as raised:
        await runtime.render("todos")

    assert raised.value.page_name == "todos"


async def test_calling_an_unknown_tool_name_reaches_the_caller_unchanged() -> None:
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.call("delete_todo", {})

    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = build_page_runtime(registry, TodoStore())

    with pytest.raises(ToolNotFoundError) as raised:
        await runtime.render("todos")

    assert raised.value.tool_name == "delete_todo"


async def test_malformed_tool_input_reaches_the_caller_unchanged() -> None:
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.call("create_todo", {})

    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = build_page_runtime(registry, TodoStore())

    with pytest.raises(ToolInputValidationError) as raised:
        await runtime.render("todos")

    assert raised.value.tool_name == "create_todo"


async def test_an_exception_from_a_page_handler_reaches_the_caller_unchanged() -> None:
    registry = PageRegistry()

    async def handler(_ctx: PageContext) -> None:
        raise PageFailed

    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = build_page_runtime(registry, TodoStore())

    with pytest.raises(PageFailed):
        await runtime.render("todos")
