"""The Todo sample app from docs/roadmap.md, used as a test fixture.

It stays a fixture rather than a package: an importable sample app presumes the
App Package layer, which is M9.
"""

from dataclasses import dataclass

from nicegui import ui
from pydantic import BaseModel

from vibepy.page import Page, PageContext, PageDefinition, PageRegistry, PageRuntime
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime

APP_ID = "todo-app"


class CreateTodoInput(BaseModel):
    title: str


class EmptyInput(BaseModel):
    pass


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoList(BaseModel):
    todos: list[Todo]


class TodoStore:
    """The app's domain internals. Not a Tool, and no channel reaches it."""

    def __init__(self) -> None:
        self._todos: list[Todo] = []

    def create(self, title: str) -> Todo:
        todo = Todo(id=len(self._todos) + 1, title=title, done=False)
        self._todos.append(todo)
        return todo

    def list_all(self) -> list[Todo]:
        return list(self._todos)


async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return ctx.dependencies.create(payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=ctx.dependencies.list_all())


async def todos_page(ctx: PageContext) -> None:
    """The human workflow. It reaches the domain only through Tools."""
    listing = await ctx.tools.call("list_todos", {})

    @ui.refreshable
    def rendered(todos: TodoList) -> None:
        for todo in todos.todos:
            ui.label(f"todo: {todo.title}")

    title = ui.input("title")

    async def add() -> None:
        await ctx.tools.call("create_todo", {"title": title.value})
        refreshed = await ctx.tools.call("list_todos", {})
        assert isinstance(refreshed, TodoList)
        rendered.refresh(refreshed)

    ui.button("Add", on_click=add)
    assert isinstance(listing, TodoList)
    rendered(listing)


@dataclass(frozen=True)
class TodoApp:
    """One App's registries and runtimes. AppRuntime, which owns these, is M5A."""

    tool_registry: ToolRegistry[TodoStore]
    tool_runtime: ToolRuntime[TodoStore]
    page_registry: PageRegistry
    page_runtime: PageRuntime


def build_todo_app() -> TodoApp:
    store = TodoStore()
    tool_registry: ToolRegistry[TodoStore] = ToolRegistry()
    tool_registry.register(
        Tool(
            definition=ToolDefinition(
                name="create_todo",
                description="Create a todo",
                input_model=CreateTodoInput,
                output_model=Todo,
            ),
            handler=create_todo,
        )
    )
    tool_registry.register(
        Tool(
            definition=ToolDefinition(
                name="list_todos",
                description="List every todo",
                input_model=EmptyInput,
                output_model=TodoList,
            ),
            handler=list_todos,
        )
    )

    tool_runtime = ToolRuntime(app_id=APP_ID, registry=tool_registry, dependencies=store)

    page_registry = PageRegistry()
    page_registry.register(
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=todos_page,
        )
    )

    return TodoApp(
        tool_registry=tool_registry,
        tool_runtime=tool_runtime,
        page_registry=page_registry,
        page_runtime=PageRuntime(registry=page_registry, tool_runtime=tool_runtime),
    )
