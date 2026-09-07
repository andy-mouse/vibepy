import json

from mcp.client import Client
from mcp.server import Server
from mcp.types import TextContent
from pydantic import BaseModel

from vibepy.adapters.mcp import build_mcp_server, to_mcp_tool
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime


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


def create_todo_definition() -> ToolDefinition[CreateTodoInput, Todo]:
    return ToolDefinition(
        name="create_todo",
        description="Create a todo",
        input_model=CreateTodoInput,
        output_model=Todo,
    )


def list_todos_definition() -> ToolDefinition[EmptyInput, TodoList]:
    return ToolDefinition(
        name="list_todos",
        description="List every todo",
        input_model=EmptyInput,
        output_model=TodoList,
    )


def test_projection_carries_the_declaration_over() -> None:
    projected = to_mcp_tool(create_todo_definition())

    assert projected.name == "create_todo"
    assert projected.description == "Create a todo"


def test_projected_schemas_are_derived_from_the_models() -> None:
    projected = to_mcp_tool(create_todo_definition())

    assert projected.input_schema == CreateTodoInput.model_json_schema()
    assert projected.output_schema == Todo.model_json_schema()


def test_a_nested_output_model_keeps_its_definitions() -> None:
    projected = to_mcp_tool(list_todos_definition())

    assert projected.output_schema == TodoList.model_json_schema()
    assert projected.output_schema is not None
    assert "$defs" in projected.output_schema


APP_ID = "test-app"


class TodoFixture:
    """The Todo sample from docs/roadmap.md, plus the ToolContexts its handlers saw."""

    def __init__(self) -> None:
        self.todos: list[Todo] = []
        self.contexts: list[ToolContext] = []

    async def create_todo(self, ctx: ToolContext, payload: CreateTodoInput) -> Todo:
        self.contexts.append(ctx)
        todo = Todo(id=len(self.todos) + 1, title=payload.title, done=False)
        self.todos.append(todo)
        return todo

    async def list_todos(self, ctx: ToolContext, payload: EmptyInput) -> TodoList:
        self.contexts.append(ctx)
        return TodoList(todos=list(self.todos))

    def registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(Tool(definition=create_todo_definition(), handler=self.create_todo))
        registry.register(Tool(definition=list_todos_definition(), handler=self.list_todos))
        return registry


def build_server(registry: ToolRegistry) -> Server[None]:
    return build_mcp_server(
        name="test-app",
        version="0.0.0",
        registry=registry,
        runtime=ToolRuntime(app_id=APP_ID, registry=registry),
    )


async def test_framework_tools_appear_in_mcp_discovery() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        listed = await client.list_tools()

    assert [tool.name for tool in listed.tools] == ["create_todo", "list_todos"]
    assert [tool.description for tool in listed.tools] == ["Create a todo", "List every todo"]


async def test_discovered_schemas_are_the_projected_schemas() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        listed = await client.list_tools()

    assert listed.tools[0].input_schema == CreateTodoInput.model_json_schema()
    assert listed.tools[0].output_schema == Todo.model_json_schema()
    assert listed.tools[1].output_schema == TodoList.model_json_schema()


async def test_a_call_reaches_the_tool_and_changes_app_state() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})

    assert [todo.title for todo in fixture.todos] == ["milk"]


async def test_the_invocation_context_is_created_by_the_tool_runtime() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        await client.call_tool("create_todo", {"title": "eggs"})

    first, second = fixture.contexts
    assert first.app_id == APP_ID
    assert second.app_id == APP_ID
    assert first.invocation_id != ""
    assert first.invocation_id != second.invocation_id


async def test_a_result_is_the_validated_output_model() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        result = await client.call_tool("create_todo", {"title": "milk"})

    expected = Todo(id=1, title="milk", done=False).model_dump(by_alias=True, mode="json")
    assert result.is_error is False
    assert result.structured_content == expected
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text) == expected


async def test_a_nested_result_survives_the_round_trip() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        result = await client.call_tool("list_todos", {})

    assert result.structured_content == {"todos": [{"id": 1, "title": "milk", "done": False}]}
