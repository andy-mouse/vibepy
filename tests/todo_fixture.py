"""The Todo sample app from docs/roadmap.md, used as a test fixture.

It stays a fixture rather than a package: an importable sample app presumes the
App Package layer, which is M9.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from nicegui import ui
from pydantic import BaseModel

from vibepy.app import AppDefinition, AppEntrypoint
from vibepy.page import Page, PageContext, PageDefinition
from vibepy.tool import Tool, ToolContext, ToolDefinition

APP_ID = "todo-app"


class TodoConfig(BaseModel):
    """What the Todo App requires of its host."""

    db_path: Path


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

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._todos: list[Todo] = []

    def create(self, title: str) -> Todo:
        todo = Todo(id=len(self._todos) + 1, title=title, done=False)
        self._todos.append(todo)
        return todo

    def list_all(self) -> list[Todo]:
        return list(self._todos)


@asynccontextmanager
async def todo_lifespan(config: TodoConfig) -> AsyncGenerator[TodoStore]:
    """The Todo App's resource, acquired at startup and dropped at shutdown."""
    yield TodoStore(config.db_path)


async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return ctx.dependencies.create(payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=ctx.dependencies.list_all())


async def todos_page(ctx: PageContext) -> None:
    """The human workflow. It reaches the domain only through Tools."""
    listing = await ctx.tools.invoke("list_todos", {})

    @ui.refreshable
    def rendered(todos: TodoList) -> None:
        for todo in todos.todos:
            ui.label(f"todo: {todo.title}")

    title = ui.input("title")

    async def add() -> None:
        await ctx.tools.invoke("create_todo", {"title": title.value})
        refreshed = await ctx.tools.invoke("list_todos", {})
        assert isinstance(refreshed, TodoList)
        rendered.refresh(refreshed)

    ui.button("Add", on_click=add)
    assert isinstance(listing, TodoList)
    rendered(listing)


TODO_APP: AppDefinition[TodoStore, TodoConfig] = AppDefinition(
    app_id=APP_ID,
    name="Todo",
    version="0.0.0",
    config=TodoConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="create_todo",
                description="Create a todo",
                input_model=CreateTodoInput,
                output_model=Todo,
            ),
            handler=create_todo,
        ),
        Tool(
            definition=ToolDefinition(
                name="list_todos",
                description="List every todo",
                input_model=EmptyInput,
                output_model=TodoList,
            ),
            handler=list_todos,
        ),
    ],
    pages=[
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=todos_page,
        )
    ],
)

TODO_CONFIG: dict[str, object] = {"db_path": "/tmp/vibepy-todo.db"}

TODO_ENTRYPOINT: AppEntrypoint[TodoStore, TodoConfig] = AppEntrypoint(
    definition=TODO_APP, lifespan=todo_lifespan
)
