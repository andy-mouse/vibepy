from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel

from vibepy.errors import ToolNotFoundError
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry


class CreateTodoInput(BaseModel):
    title: str


class CompleteTodoInput(BaseModel):
    id: int


class EmptyInput(BaseModel):
    pass


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoList(BaseModel):
    todos: list[Todo]


class TodoNotFound(Exception):
    """Domain exception owned by the Todo fixture, not by the framework."""

    def __init__(self, todo_id: int) -> None:
        super().__init__(f"No todo with id {todo_id}")
        self.todo_id = todo_id


class TodoStore:
    def __init__(self) -> None:
        self._todos: dict[int, Todo] = {}
        self._next_id = 1

    def create(self, title: str) -> Todo:
        todo = Todo(id=self._next_id, title=title, done=False)
        self._todos[todo.id] = todo
        self._next_id += 1
        return todo

    def list(self) -> list[Todo]:
        return list(self._todos.values())

    def complete(self, todo_id: int) -> Todo:
        todo = self._todos.get(todo_id)
        if todo is None:
            raise TodoNotFound(todo_id)
        completed = todo.model_copy(update={"done": True})
        self._todos[todo_id] = completed
        return completed


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


def list_todos_tool(store: TodoStore) -> Tool[EmptyInput, TodoList]:
    async def handler(_ctx: ToolContext, _payload: EmptyInput) -> TodoList:
        return TodoList(todos=store.list())

    return Tool(
        definition=ToolDefinition(
            name="list_todos",
            description="List every todo item",
            input_model=EmptyInput,
            output_model=TodoList,
        ),
        handler=handler,
    )


def complete_todo_tool(store: TodoStore) -> Tool[CompleteTodoInput, Todo]:
    async def handler(_ctx: ToolContext, payload: CompleteTodoInput) -> Todo:
        return store.complete(payload.id)

    return Tool(
        definition=ToolDefinition(
            name="complete_todo",
            description="Mark a todo item as done",
            input_model=CompleteTodoInput,
            output_model=Todo,
        ),
        handler=handler,
    )


def test_tool_definition_declares_its_models() -> None:
    tool = create_todo_tool(TodoStore())

    assert tool.definition.name == "create_todo"
    assert tool.definition.description == "Create a todo item"
    assert tool.definition.input_model is CreateTodoInput
    assert tool.definition.output_model is Todo


def test_tool_context_is_immutable() -> None:
    ctx = ToolContext(app_id="todo", invocation_id="inv-1")

    with pytest.raises(FrozenInstanceError):
        ctx.app_id = "other"  # type: ignore[misc]


async def test_handler_protocol_accepts_a_plain_async_function() -> None:
    store = TodoStore()
    tool = create_todo_tool(store)
    ctx = ToolContext(app_id="todo", invocation_id="inv-1")

    todo = await tool.handler(ctx, CreateTodoInput(title="buy milk"))

    assert todo == Todo(id=1, title="buy milk", done=False)


def build_registry(store: TodoStore) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(create_todo_tool(store))
    registry.register(list_todos_tool(store))
    registry.register(complete_todo_tool(store))
    return registry


def test_resolving_an_unregistered_name_raises() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolNotFoundError) as raised:
        registry.resolve("create_todo")

    assert raised.value.tool_name == "create_todo"
