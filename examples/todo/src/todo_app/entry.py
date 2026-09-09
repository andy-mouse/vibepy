"""The Todo sample App from docs/roadmap.md.

The App the Hub installs and starts. Its store keeps todos in the file it was
configured with, so what a channel writes is there for the next window and for
the other channel -- which is what `docs/architecture/app-model.md` requires of
an App that must agree across its channels.
"""

import asyncio
import hashlib
import hmac
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from nicegui import ui
from pydantic import BaseModel, SecretStr, TypeAdapter

from vibepy_core.app import AppDefinition, AppEntrypoint
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition

APP_ID = "todo-app"


class TodoConfig(BaseModel):
    """What the Todo App requires of its host.

    `db_key` is a secret by type, so a Host can tell it from an ordinary string
    without importing this App (ADR-022). The store stamps its file with it, so
    the secret is one this App uses rather than one it merely declares.
    """

    db_path: Path
    db_key: SecretStr


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


class _Stored(BaseModel):
    """The file the store keeps, and the digest that says who wrote it."""

    todos: list[Todo]
    stamp: str


_TODOS = TypeAdapter(list[Todo])


class TodoStoreUnreadable(Exception):
    """The stored file was not written by a holder of this key.

    Raised rather than answered as data:
    `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md` gives
    data to an App's *expected* failures, and a store whose file does not match
    its key is a broken resource rather than a step in this App's workflow. The
    framework describes it as `app.unhandled`.
    """


class TodoStore:
    """The app's domain internals. Not a Tool, and no channel reaches it."""

    def __init__(self, db_path: Path, db_key: SecretStr) -> None:
        self.db_path = db_path
        self._key = db_key.get_secret_value().encode()

    def create(self, title: str) -> Todo:
        todos = self.list_all()
        todo = Todo(id=len(todos) + 1, title=title, done=False)
        self._write([*todos, todo])
        return todo

    def list_all(self) -> list[Todo]:
        if not self.db_path.is_file():
            return []
        stored = _Stored.model_validate_json(self.db_path.read_text(encoding="utf-8"))
        body = _TODOS.dump_json(stored.todos)
        if not hmac.compare_digest(stored.stamp, self._stamp(body)):
            raise TodoStoreUnreadable(f"{self.db_path} was not written under this key")
        return list(stored.todos)

    def _write(self, todos: list[Todo], /) -> None:
        body = _TODOS.dump_json(todos)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(
            _Stored(todos=todos, stamp=self._stamp(body)).model_dump_json(indent=1),
            encoding="utf-8",
        )

    def _stamp(self, body: bytes, /) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()


@asynccontextmanager
async def todo_lifespan(config: TodoConfig) -> AsyncGenerator[TodoStore]:
    """The Todo App's resource, acquired at startup and dropped at shutdown."""
    yield TodoStore(config.db_path, config.db_key)


async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return await asyncio.to_thread(ctx.dependencies.create, payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=await asyncio.to_thread(ctx.dependencies.list_all))


async def todos_page(ctx: PageContext) -> None:
    """The human workflow. It reaches the domain only through Tools.

    A Tool's output model is the contract, so a result is narrowed by validating
    it against that model rather than by `assert`, which `python -O` removes.
    """
    listing = TodoList.model_validate(await ctx.tools.invoke("list_todos", {}))

    @ui.refreshable
    def rendered(todos: TodoList) -> None:
        for todo in todos.todos:
            ui.label(f"todo: {todo.title}")

    title = ui.input("title")

    async def add() -> None:
        await ctx.tools.invoke("create_todo", {"title": title.value})
        rendered.refresh(TodoList.model_validate(await ctx.tools.invoke("list_todos", {})))

    ui.button("Add", on_click=add)
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

APP: AppEntrypoint[TodoStore, TodoConfig] = AppEntrypoint(
    definition=TODO_APP, lifespan=todo_lifespan
)
