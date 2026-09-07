from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel

from vibepy.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
)
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime


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


class ProbeOutput(BaseModel):
    app_id: str
    invocation_id: str


def probe_tool() -> Tool[EmptyInput, ProbeOutput]:
    async def handler(ctx: ToolContext, _payload: EmptyInput) -> ProbeOutput:
        return ProbeOutput(app_id=ctx.app_id, invocation_id=ctx.invocation_id)

    return Tool(
        definition=ToolDefinition(
            name="probe",
            description="Report the context of this invocation",
            input_model=EmptyInput,
            output_model=ProbeOutput,
        ),
        handler=handler,
    )


def broken_output_tool() -> Tool[EmptyInput, Todo]:
    async def handler(_ctx: ToolContext, _payload: EmptyInput) -> Todo:
        return Todo.model_construct(id="not-an-integer", title="broken", done=False)

    return Tool(
        definition=ToolDefinition(
            name="broken_output",
            description="Return a value that violates its own output model",
            input_model=EmptyInput,
            output_model=Todo,
        ),
        handler=handler,
    )


async def test_raw_input_round_trips_into_a_validated_output_model() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))

    result = await runtime.invoke("create_todo", {"title": "buy milk"})

    assert result == Todo(id=1, title="buy milk", done=False)


async def test_tools_share_the_state_they_were_built_over() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))
    await runtime.invoke("create_todo", {"title": "buy milk"})
    await runtime.invoke("create_todo", {"title": "walk the dog"})

    result = await runtime.invoke("list_todos", {})

    assert result == TodoList(
        todos=[
            Todo(id=1, title="buy milk", done=False),
            Todo(id=2, title="walk the dog", done=False),
        ]
    )


async def test_invoking_an_unknown_name_raises() -> None:
    runtime = ToolRuntime(app_id="todo", registry=ToolRegistry())

    with pytest.raises(ToolNotFoundError) as raised:
        await runtime.invoke("create_todo", {})

    assert raised.value.tool_name == "create_todo"


async def test_malformed_raw_input_raises_input_validation_error() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))

    with pytest.raises(ToolInputValidationError) as raised:
        await runtime.invoke("create_todo", {})

    assert raised.value.tool_name == "create_todo"


async def test_a_result_violating_the_output_model_raises_output_validation_error() -> None:
    registry = ToolRegistry()
    registry.register(broken_output_tool())
    runtime = ToolRuntime(app_id="todo", registry=registry)

    with pytest.raises(ToolOutputValidationError) as raised:
        await runtime.invoke("broken_output", {})

    assert raised.value.tool_name == "broken_output"


async def test_a_domain_exception_reaches_the_caller_unchanged() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))

    with pytest.raises(TodoNotFound) as raised:
        await runtime.invoke("complete_todo", {"id": 999})

    assert raised.value.todo_id == 999


async def test_the_handler_receives_the_runtime_app_id() -> None:
    registry = ToolRegistry()
    registry.register(probe_tool())
    runtime = ToolRuntime(app_id="todo-app", registry=registry)

    result = await runtime.invoke("probe", {})

    assert isinstance(result, ProbeOutput)
    assert result.app_id == "todo-app"


async def test_each_invocation_receives_its_own_invocation_id() -> None:
    registry = ToolRegistry()
    registry.register(probe_tool())
    runtime = ToolRuntime(app_id="todo-app", registry=registry)

    first = await runtime.invoke("probe", {})
    second = await runtime.invoke("probe", {})

    assert isinstance(first, ProbeOutput)
    assert isinstance(second, ProbeOutput)
    assert first.invocation_id != second.invocation_id
