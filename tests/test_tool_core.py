from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel, Field, computed_field

from vibepy_core import Channel, Principal
from vibepy_core.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
)
from vibepy_core.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime


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


async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return ctx.dependencies.create(payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=ctx.dependencies.list())


async def complete_todo(ctx: ToolContext[TodoStore], payload: CompleteTodoInput) -> Todo:
    return ctx.dependencies.complete(payload.id)


def create_todo_tool() -> Tool[TodoStore]:
    return Tool(
        definition=ToolDefinition(
            name="create_todo",
            description="Create a todo item",
            input_model=CreateTodoInput,
            output_model=Todo,
            read_only=False,
        ),
        handler=create_todo,
    )


def list_todos_tool() -> Tool[TodoStore]:
    return Tool(
        definition=ToolDefinition(
            name="list_todos",
            description="List every todo item",
            input_model=EmptyInput,
            output_model=TodoList,
            read_only=True,
        ),
        handler=list_todos,
    )


def complete_todo_tool() -> Tool[TodoStore]:
    return Tool(
        definition=ToolDefinition(
            name="complete_todo",
            description="Mark a todo item as done",
            input_model=CompleteTodoInput,
            output_model=Todo,
            read_only=False,
        ),
        handler=complete_todo,
    )


def test_tool_definition_declares_its_models() -> None:
    tool = create_todo_tool()

    assert tool.definition.name == "create_todo"
    assert tool.definition.description == "Create a todo item"
    assert tool.definition.input_model is CreateTodoInput
    assert tool.definition.output_model is Todo


def test_tool_context_is_immutable() -> None:
    ctx = ToolContext(
        app_id="todo",
        invocation_id="inv-1",
        dependencies=None,
        principal=Principal(id="test"),
        channel=Channel.AGENT,
    )

    with pytest.raises(FrozenInstanceError):
        ctx.app_id = "other"  # pyright: ignore[reportAttributeAccessIssue]


async def test_handler_protocol_accepts_a_plain_async_function() -> None:
    store = TodoStore()
    ctx = ToolContext(
        app_id="todo",
        invocation_id="inv-1",
        dependencies=store,
        principal=Principal(id="test"),
        channel=Channel.AGENT,
    )

    todo = await create_todo(ctx, CreateTodoInput(title="buy milk"))

    assert todo == Todo(id=1, title="buy milk", done=False)


def build_registry() -> ToolRegistry[TodoStore]:
    registry: ToolRegistry[TodoStore] = ToolRegistry()
    registry.register(create_todo_tool())
    registry.register(list_todos_tool())
    registry.register(complete_todo_tool())
    return registry


def test_resolving_an_unregistered_name_raises() -> None:
    registry: ToolRegistry[None] = ToolRegistry()

    with pytest.raises(ToolNotFoundError) as raised:
        registry.resolve("create_todo")

    assert raised.value.tool_name == "create_todo"


class ProbeOutput(BaseModel):
    app_id: str
    invocation_id: str


def probe_tool() -> Tool[None]:
    async def handler(ctx: ToolContext[None], _payload: EmptyInput) -> ProbeOutput:
        return ProbeOutput(app_id=ctx.app_id, invocation_id=ctx.invocation_id)

    return Tool(
        definition=ToolDefinition(
            name="probe",
            description="Report the context of this invocation",
            input_model=EmptyInput,
            output_model=ProbeOutput,
            read_only=True,
        ),
        handler=handler,
    )


def broken_output_tool() -> Tool[None]:
    async def handler(_ctx: ToolContext[None], _payload: EmptyInput) -> Todo:
        return Todo.model_construct(id="not-an-integer", title="broken", done=False)

    return Tool(
        definition=ToolDefinition(
            name="broken_output",
            description="Return a value that violates its own output model",
            input_model=EmptyInput,
            output_model=Todo,
            read_only=True,
        ),
        handler=handler,
    )


async def test_raw_input_round_trips_into_a_validated_output_model() -> None:
    runtime = ToolRuntime(
        app_id="todo", registry=build_registry(), dependencies=TodoStore(), channel=Channel.AGENT
    )

    result = await runtime.invoke(
        "create_todo", {"title": "buy milk"}, principal=Principal(id="test")
    )

    assert result == Todo(id=1, title="buy milk", done=False)


async def test_tools_share_the_dependencies_they_were_invoked_with() -> None:
    runtime = ToolRuntime(
        app_id="todo", registry=build_registry(), dependencies=TodoStore(), channel=Channel.AGENT
    )
    await runtime.invoke("create_todo", {"title": "buy milk"}, principal=Principal(id="test"))
    await runtime.invoke("create_todo", {"title": "walk the dog"}, principal=Principal(id="test"))

    result = await runtime.invoke("list_todos", {}, principal=Principal(id="test"))

    assert result == TodoList(
        todos=[
            Todo(id=1, title="buy milk", done=False),
            Todo(id=2, title="walk the dog", done=False),
        ]
    )


async def test_invoking_an_unknown_name_raises() -> None:
    registry: ToolRegistry[None] = ToolRegistry()
    runtime = ToolRuntime(
        app_id="todo", registry=registry, dependencies=None, channel=Channel.AGENT
    )

    with pytest.raises(ToolNotFoundError) as raised:
        await runtime.invoke("create_todo", {}, principal=Principal(id="test"))

    assert raised.value.tool_name == "create_todo"


async def test_malformed_raw_input_raises_input_validation_error() -> None:
    runtime = ToolRuntime(
        app_id="todo", registry=build_registry(), dependencies=TodoStore(), channel=Channel.AGENT
    )

    with pytest.raises(ToolInputValidationError) as raised:
        await runtime.invoke("create_todo", {}, principal=Principal(id="test"))

    assert raised.value.tool_name == "create_todo"


async def test_a_result_violating_the_output_model_raises_output_validation_error() -> None:
    registry: ToolRegistry[None] = ToolRegistry()
    registry.register(broken_output_tool())
    runtime = ToolRuntime(
        app_id="todo", registry=registry, dependencies=None, channel=Channel.AGENT
    )

    with pytest.raises(ToolOutputValidationError) as raised:
        await runtime.invoke("broken_output", {}, principal=Principal(id="test"))

    assert raised.value.tool_name == "broken_output"


async def test_a_domain_exception_reaches_the_caller_unchanged() -> None:
    runtime = ToolRuntime(
        app_id="todo", registry=build_registry(), dependencies=TodoStore(), channel=Channel.AGENT
    )

    with pytest.raises(TodoNotFound) as raised:
        await runtime.invoke("complete_todo", {"id": 999}, principal=Principal(id="test"))

    assert raised.value.todo_id == 999


async def test_the_handler_receives_the_runtime_app_id() -> None:
    registry: ToolRegistry[None] = ToolRegistry()
    registry.register(probe_tool())
    runtime = ToolRuntime(
        app_id="todo-app", registry=registry, dependencies=None, channel=Channel.AGENT
    )

    result = await runtime.invoke("probe", {}, principal=Principal(id="test"))

    assert isinstance(result, ProbeOutput)
    assert result.app_id == "todo-app"


async def test_each_invocation_receives_its_own_invocation_id() -> None:
    registry: ToolRegistry[None] = ToolRegistry()
    registry.register(probe_tool())
    runtime = ToolRuntime(
        app_id="todo-app", registry=registry, dependencies=None, channel=Channel.AGENT
    )

    first = await runtime.invoke("probe", {}, principal=Principal(id="test"))
    second = await runtime.invoke("probe", {}, principal=Principal(id="test"))

    assert isinstance(first, ProbeOutput)
    assert isinstance(second, ProbeOutput)
    assert first.invocation_id != second.invocation_id


def test_registering_a_name_twice_replaces_the_earlier_tool() -> None:
    """The registry's own contract, which no framework path reaches: ADR-027 has
    a window refuse a declaration carrying one name twice."""
    registry: ToolRegistry[TodoStore] = ToolRegistry()
    registry.register(create_todo_tool())
    replacement = Tool(
        definition=ToolDefinition(
            name="create_todo",
            description="Replaced",
            input_model=CreateTodoInput,
            output_model=Todo,
            read_only=False,
        ),
        handler=create_todo,
    )
    registry.register(replacement)

    assert registry.resolve("create_todo") is replacement


async def test_the_handler_receives_the_runtime_dependencies() -> None:
    store = TodoStore()
    runtime = ToolRuntime(
        app_id="todo", registry=build_registry(), dependencies=store, channel=Channel.AGENT
    )

    await runtime.invoke("create_todo", {"title": "buy milk"}, principal=Principal(id="test"))

    assert [todo.title for todo in store.list()] == ["buy milk"]


class Sized(BaseModel):
    """A model whose serialized shape is not its validated shape."""

    width: int = Field(serialization_alias="widthPx")

    @computed_field
    @property
    def doubled(self) -> int:
        return self.width * 2


def test_a_declaration_answers_with_the_schema_its_input_is_validated_against() -> None:
    definition = ToolDefinition(
        name="measure", description="d", input_model=Sized, output_model=Sized, read_only=True
    )

    properties = definition.input_schema()["properties"]

    assert isinstance(properties, dict)
    assert set(properties) == {"width"}


def test_a_declaration_answers_with_the_schema_its_output_is_serialized_to() -> None:
    """ADR-007: the published schema and the returned value cannot diverge."""
    definition = ToolDefinition(
        name="measure", description="d", input_model=Sized, output_model=Sized, read_only=True
    )

    properties = definition.output_schema()["properties"]

    assert isinstance(properties, dict)
    assert set(properties) == set(Sized(width=2).model_dump(by_alias=True, mode="json"))


def test_a_principal_is_an_id_and_a_set_of_roles() -> None:
    alice = Principal(id="alice", roles=frozenset({"manager"}))
    nobody = Principal(id="nobody")

    assert alice.roles == {"manager"}
    assert nobody.roles == frozenset()
    with pytest.raises(FrozenInstanceError):
        alice.id = "bob"  # pyright: ignore[reportAttributeAccessIssue]


def test_the_channels_are_a_closed_set() -> None:
    assert [channel.value for channel in Channel] == ["web", "agent"]


def test_a_tool_declares_its_side_effects_exposure_and_roles() -> None:
    definition = ToolDefinition(
        name="approve",
        description="Approve",
        input_model=EmptyInput,
        output_model=TodoList,
        read_only=False,
        channels=frozenset({Channel.WEB}),
        required_roles=frozenset({"manager"}),
    )

    assert definition.read_only is False
    assert definition.channels == {Channel.WEB}
    assert definition.required_roles == {"manager"}


def test_a_tool_is_exposed_on_both_channels_to_anyone_unless_it_says_otherwise() -> None:
    definition = list_todos_tool().definition

    assert definition.channels == frozenset(Channel)
    assert definition.required_roles == frozenset()


def test_read_only_has_no_default() -> None:
    with pytest.raises(TypeError):
        ToolDefinition(  # pyright: ignore[reportCallIssue]
            name="x", description="x", input_model=EmptyInput, output_model=TodoList
        )
